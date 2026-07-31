"""Operações de banco para leituras de sensores."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models import SensorReading

#: Métricas que podem ser consultadas como série temporal.
METRIC_COLUMNS = {
    "temperature": (SensorReading.temperature, "°C"),
    "speed": (SensorReading.speed, "rpm"),
    "efficiency": (SensorReading.efficiency, "%"),
    "energy": (SensorReading.energy, "kW"),
    "vibration": (SensorReading.vibration, "mm/s"),
    "pressure": (SensorReading.pressure, "bar"),
}


class CRUDReading:
    def create_many(self, db: Session, readings: list[SensorReading]) -> None:
        db.add_all(readings)
        db.commit()

    def get_latest(self, db: Session, machine_id: int) -> SensorReading | None:
        stmt = (
            select(SensorReading)
            .where(SensorReading.machine_id == machine_id)
            .order_by(SensorReading.id.desc())
            .limit(1)
        )
        return db.scalar(stmt)

    def list_for_machine(
        self,
        db: Session,
        machine_id: int,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[SensorReading], int]:
        conditions = [SensorReading.machine_id == machine_id]
        if since:
            conditions.append(SensorReading.ts >= since)
        if until:
            conditions.append(SensorReading.ts <= until)

        stmt = (
            select(SensorReading)
            .where(*conditions)
            .order_by(SensorReading.ts.desc())
            .limit(limit)
            .offset(offset)
        )
        count_stmt = select(func.count()).select_from(SensorReading).where(*conditions)
        return list(db.scalars(stmt).all()), (db.scalar(count_stmt) or 0)

    def series(
        self,
        db: Session,
        machine_id: int,
        metric: str,
        *,
        minutes: int = 60,
        max_points: int = 240,
    ) -> tuple[list[tuple[datetime, float]], str]:
        """Série temporal de uma métrica, decimada para no máximo `max_points`.

        A decimação é feita em Python porque a agregação por bucket de tempo
        difere entre SQLite e Postgres; o volume aqui é pequeno o bastante.
        """
        if metric not in METRIC_COLUMNS:
            raise ValueError(f"Métrica desconhecida: {metric}")
        column, unit = METRIC_COLUMNS[metric]

        since = utcnow() - timedelta(minutes=minutes)
        stmt = (
            select(SensorReading.ts, column)
            .where(SensorReading.machine_id == machine_id, SensorReading.ts >= since)
            .order_by(SensorReading.ts.asc())
        )
        rows = [(ts, float(value)) for ts, value in db.execute(stmt).all()]

        if len(rows) > max_points:
            step = len(rows) / max_points
            rows = [rows[int(i * step)] for i in range(max_points)]
        return rows, unit

    def purge_older_than(self, db: Session, *, days: int) -> int:
        """Retenção da série temporal — evita crescimento indefinido em demo."""
        cutoff = utcnow() - timedelta(days=days)
        stmt = select(SensorReading.id).where(SensorReading.ts < cutoff)
        ids = list(db.scalars(stmt).all())
        if not ids:
            return 0
        for chunk_start in range(0, len(ids), 500):
            chunk = ids[chunk_start : chunk_start + 500]
            db.query(SensorReading).filter(SensorReading.id.in_(chunk)).delete(
                synchronize_session=False
            )
        db.commit()
        return len(ids)


reading_crud = CRUDReading()
