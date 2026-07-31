"""Operações de banco para produção e cálculo de OEE."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models import Machine, ProductionRecord
from app.schemas.production import ProductionRecordCreate, ProductionRecordUpdate


def hour_bucket(moment: datetime | None = None) -> datetime:
    """Trunca o instante na hora cheia — chave da janela de agregação."""
    moment = moment or utcnow()
    return moment.replace(minute=0, second=0, microsecond=0)


class CRUDProduction:
    def get(self, db: Session, record_id: int) -> ProductionRecord | None:
        return db.get(ProductionRecord, record_id)

    def get_or_create_bucket(
        self, db: Session, machine_id: int, bucket_start: datetime | None = None
    ) -> ProductionRecord:
        """Bucket da hora corrente da máquina, criado sob demanda."""
        bucket_start = bucket_start or hour_bucket()
        stmt = select(ProductionRecord).where(
            ProductionRecord.machine_id == machine_id,
            ProductionRecord.bucket_start == bucket_start,
        )
        record = db.scalar(stmt)
        if record is None:
            record = ProductionRecord(machine_id=machine_id, bucket_start=bucket_start)
            db.add(record)
            db.flush()
        return record

    def create(self, db: Session, payload: ProductionRecordCreate) -> ProductionRecord:
        data = payload.model_dump()
        data["bucket_start"] = data.get("bucket_start") or hour_bucket()
        record = ProductionRecord(**data)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def update(
        self, db: Session, record: ProductionRecord, payload: ProductionRecordUpdate
    ) -> ProductionRecord:
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(record, field, value)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def delete(self, db: Session, record: ProductionRecord) -> None:
        db.delete(record)
        db.commit()

    def list_filtered(
        self,
        db: Session,
        *,
        machine_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[ProductionRecord], int]:
        conditions = []
        if machine_id is not None:
            conditions.append(ProductionRecord.machine_id == machine_id)
        if since is not None:
            conditions.append(ProductionRecord.bucket_start >= since)
        if until is not None:
            conditions.append(ProductionRecord.bucket_start <= until)

        stmt = (
            select(ProductionRecord)
            .where(*conditions)
            .order_by(ProductionRecord.bucket_start.desc())
            .limit(limit)
            .offset(offset)
        )
        count_stmt = select(func.count()).select_from(ProductionRecord).where(*conditions)
        return list(db.scalars(stmt).all()), (db.scalar(count_stmt) or 0)

    def aggregate(
        self,
        db: Session,
        *,
        machine_id: int | None = None,
        hours: int = 8,
    ) -> dict:
        """Soma os buckets da janela — insumo do cálculo de OEE."""
        window_start = hour_bucket(utcnow() - timedelta(hours=hours))
        conditions = [ProductionRecord.bucket_start >= window_start]
        if machine_id is not None:
            conditions.append(ProductionRecord.machine_id == machine_id)

        stmt = select(
            func.coalesce(func.sum(ProductionRecord.good_count), 0),
            func.coalesce(func.sum(ProductionRecord.scrap_count), 0),
            func.coalesce(func.sum(ProductionRecord.planned_time_s), 0.0),
            func.coalesce(func.sum(ProductionRecord.runtime_s), 0.0),
            func.coalesce(func.sum(ProductionRecord.downtime_s), 0.0),
            func.coalesce(func.sum(ProductionRecord.energy_kwh), 0.0),
            func.coalesce(func.sum(ProductionRecord.fault_count), 0),
        ).where(*conditions)

        good, scrap, planned, runtime, downtime, energy, faults = db.execute(stmt).one()
        return {
            "good_count": int(good),
            "scrap_count": int(scrap),
            "planned_time_s": float(planned),
            "runtime_s": float(runtime),
            "downtime_s": float(downtime),
            "energy_kwh": float(energy),
            "fault_count": int(faults),
            "window_start": window_start,
            "window_end": utcnow(),
        }

    def weighted_ideal_cycle_time(self, db: Session, *, hours: int = 8) -> float:
        """Tempo de ciclo ideal médio, ponderado pela produção de cada máquina.

        Necessário para calcular a Performance da linha inteira, já que cada
        estação tem um tempo de ciclo diferente.
        """
        window_start = hour_bucket(utcnow() - timedelta(hours=hours))
        stmt = (
            select(
                Machine.ideal_cycle_time_s,
                func.sum(ProductionRecord.good_count + ProductionRecord.scrap_count),
            )
            .join(ProductionRecord, ProductionRecord.machine_id == Machine.id)
            .where(ProductionRecord.bucket_start >= window_start)
            .group_by(Machine.id, Machine.ideal_cycle_time_s)
        )
        rows = db.execute(stmt).all()
        total_parts = sum(int(parts or 0) for _, parts in rows)
        if total_parts == 0:
            return 0.0
        weighted = sum(float(cycle) * int(parts or 0) for cycle, parts in rows)
        return weighted / total_parts


production_crud = CRUDProduction()
