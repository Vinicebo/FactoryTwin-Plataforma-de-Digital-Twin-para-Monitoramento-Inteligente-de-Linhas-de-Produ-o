"""Operações de banco para máquinas."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models import Alarm, Machine, SensorReading
from app.models.enums import AlarmSeverity, AlarmStatus, MachineStatus
from app.schemas.machine import MachineCreate, MachineUpdate


class CRUDMachine(CRUDBase[Machine, MachineCreate, MachineUpdate]):
    def get_by_code(self, db: Session, code: str) -> Machine | None:
        return db.scalar(select(Machine).where(Machine.code == code))

    def list_filtered(
        self,
        db: Session,
        *,
        line: str | None = None,
        status: MachineStatus | None = None,
        only_active: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Machine], int]:
        stmt = select(Machine)
        count_stmt = select(func.count()).select_from(Machine)

        for condition in self._conditions(line, status, only_active):
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        stmt = stmt.order_by(Machine.line, Machine.sequence).limit(limit).offset(offset)
        return list(db.scalars(stmt).all()), (db.scalar(count_stmt) or 0)

    @staticmethod
    def _conditions(line: str | None, status: MachineStatus | None, only_active: bool) -> list:
        conditions = []
        if line:
            conditions.append(Machine.line == line)
        if status:
            conditions.append(Machine.status == status)
        if only_active:
            conditions.append(Machine.is_active.is_(True))
        return conditions

    def set_status(self, db: Session, machine: Machine, status: MachineStatus) -> Machine:
        machine.status = status
        db.add(machine)
        db.commit()
        db.refresh(machine)
        return machine

    def latest_readings_map(self, db: Session) -> dict[int, SensorReading]:
        """Última leitura de cada máquina, em uma única query.

        Usa `DISTINCT ON` no Postgres não seria portável para SQLite, então
        resolvemos com uma subquery de `MAX(id)` por máquina — o id é
        monotônico, logo equivale a "a leitura mais recente".
        """
        latest_ids = (
            select(func.max(SensorReading.id))
            .group_by(SensorReading.machine_id)
            .scalar_subquery()
        )
        stmt = select(SensorReading).where(SensorReading.id.in_(latest_ids))
        return {reading.machine_id: reading for reading in db.scalars(stmt).all()}

    def active_alarm_summary(self, db: Session) -> dict[int, tuple[int, str]]:
        """`{machine_id: (qtd_alarmes_abertos, maior_severidade)}`."""
        stmt = (
            select(Alarm.machine_id, Alarm.severity, func.count())
            .where(Alarm.status != AlarmStatus.RESOLVED)
            .group_by(Alarm.machine_id, Alarm.severity)
        )
        summary: dict[int, tuple[int, str]] = {}
        for machine_id, severity, count in db.execute(stmt).all():
            current_count, current_sev = summary.get(machine_id, (0, None))
            total = current_count + count
            worst = severity.value
            if current_sev and AlarmSeverity(current_sev).rank >= severity.rank:
                worst = current_sev
            summary[machine_id] = (total, worst)
        return summary


machine_crud = CRUDMachine(Machine)
