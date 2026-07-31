"""Operações de banco para alarmes."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models import Alarm, Machine
from app.models.enums import AlarmCode, AlarmSeverity, AlarmStatus


class CRUDAlarm:
    def get(self, db: Session, alarm_id: int) -> Alarm | None:
        return db.get(Alarm, alarm_id)

    def get_open_by_code(self, db: Session, machine_id: int, code: AlarmCode) -> Alarm | None:
        """Alarme aberto para o par (máquina, código) — base da deduplicação."""
        stmt = select(Alarm).where(
            Alarm.machine_id == machine_id,
            Alarm.code == code,
            Alarm.status != AlarmStatus.RESOLVED,
        )
        return db.scalars(stmt).first()

    def list_filtered(
        self,
        db: Session,
        *,
        machine_id: int | None = None,
        status: AlarmStatus | None = None,
        severity: AlarmSeverity | None = None,
        code: AlarmCode | None = None,
        since: datetime | None = None,
        only_open: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Alarm], int]:
        conditions = []
        if machine_id is not None:
            conditions.append(Alarm.machine_id == machine_id)
        if status is not None:
            conditions.append(Alarm.status == status)
        if only_open:
            conditions.append(Alarm.status != AlarmStatus.RESOLVED)
        if severity is not None:
            conditions.append(Alarm.severity == severity)
        if code is not None:
            conditions.append(Alarm.code == code)
        if since is not None:
            conditions.append(Alarm.triggered_at >= since)

        stmt = (
            select(Alarm)
            .where(*conditions)
            .order_by(Alarm.triggered_at.desc())
            .limit(limit)
            .offset(offset)
        )
        count_stmt = select(func.count()).select_from(Alarm).where(*conditions)
        return list(db.scalars(stmt).all()), (db.scalar(count_stmt) or 0)

    def list_with_machine(
        self, db: Session, *, only_open: bool = True, limit: int = 100, offset: int = 0
    ) -> tuple[list[tuple[Alarm, str, str]], int]:
        """Alarmes já com código e nome da máquina — evita N+1 na listagem."""
        conditions = [Alarm.status != AlarmStatus.RESOLVED] if only_open else []
        stmt = (
            select(Alarm, Machine.code, Machine.name)
            .join(Machine, Machine.id == Alarm.machine_id)
            .where(*conditions)
            .order_by(Alarm.triggered_at.desc())
            .limit(limit)
            .offset(offset)
        )
        count_stmt = select(func.count()).select_from(Alarm).where(*conditions)
        rows = [(row[0], row[1], row[2]) for row in db.execute(stmt).all()]
        return rows, (db.scalar(count_stmt) or 0)

    def acknowledge(self, db: Session, alarm: Alarm, user_id: int | None) -> Alarm:
        if alarm.status is AlarmStatus.ACTIVE:
            alarm.status = AlarmStatus.ACKNOWLEDGED
            alarm.acknowledged_at = utcnow()
            alarm.acknowledged_by_id = user_id
            db.add(alarm)
            db.commit()
            db.refresh(alarm)
        return alarm

    def resolve(self, db: Session, alarm: Alarm) -> Alarm:
        if alarm.status is not AlarmStatus.RESOLVED:
            alarm.status = AlarmStatus.RESOLVED
            alarm.resolved_at = utcnow()
            db.add(alarm)
            db.commit()
            db.refresh(alarm)
        return alarm

    def stats(self, db: Session) -> dict:
        open_filter = Alarm.status != AlarmStatus.RESOLVED

        total = db.scalar(select(func.count()).select_from(Alarm).where(open_filter)) or 0

        by_severity = {
            severity.value: count
            for severity, count in db.execute(
                select(Alarm.severity, func.count()).where(open_filter).group_by(Alarm.severity)
            ).all()
        }
        by_code = {
            code.value: count
            for code, count in db.execute(
                select(Alarm.code, func.count()).where(open_filter).group_by(Alarm.code)
            ).all()
        }
        by_machine = dict(
            db.execute(
                select(Machine.code, func.count())
                .join(Alarm, Alarm.machine_id == Machine.id)
                .where(open_filter)
                .group_by(Machine.code)
            ).all()
        )
        return {
            "total_active": total,
            "by_severity": by_severity,
            "by_code": by_code,
            "by_machine": by_machine,
        }


alarm_crud = CRUDAlarm()
