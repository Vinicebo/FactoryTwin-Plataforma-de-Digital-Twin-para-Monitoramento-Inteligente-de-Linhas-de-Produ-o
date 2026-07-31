"""Tabela `production_records` — contagem de produção agregada por janela."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow

if TYPE_CHECKING:  # pragma: no cover
    from app.models.machine import Machine


class ProductionRecord(Base):
    """Bucket de produção de uma máquina numa janela de tempo (padrão: 1 h).

    Guardar tempos acumulados aqui torna o cálculo de OEE uma agregação simples,
    sem precisar varrer a série temporal inteira de `sensor_readings`.
    """

    __tablename__ = "production_records"
    __table_args__ = (
        Index("ix_production_records_machine_bucket", "machine_id", "bucket_start"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    machine_id: Mapped[int] = mapped_column(
        ForeignKey("machines.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: Início da janela agregada (truncado na hora cheia).
    bucket_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    shift: Mapped[str] = mapped_column(String(10), default="A", nullable=False)

    good_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scrap_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    #: Segundos de tempo planejado, produzindo e parado dentro da janela.
    planned_time_s: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    runtime_s: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    downtime_s: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    #: Energia consumida na janela (kWh).
    energy_kwh: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    fault_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    machine: Mapped[Machine] = relationship(back_populates="production_records")

    # --- KPIs derivados ---------------------------------------------------
    # Os `or 0` cobrem o objeto transiente: os defaults das colunas só são
    # aplicados no INSERT, então antes do commit os atributos ainda são None.
    @property
    def total_count(self) -> int:
        return (self.good_count or 0) + (self.scrap_count or 0)

    @property
    def availability(self) -> float:
        planned = self.planned_time_s or 0.0
        if planned <= 0:
            return 0.0
        return min((self.runtime_s or 0.0) / planned, 1.0)

    @property
    def quality(self) -> float:
        if self.total_count <= 0:
            return 0.0
        return (self.good_count or 0) / self.total_count

    def performance(self, ideal_cycle_time_s: float) -> float:
        runtime = self.runtime_s or 0.0
        if runtime <= 0 or ideal_cycle_time_s <= 0:
            return 0.0
        return min((self.total_count * ideal_cycle_time_s) / runtime, 1.0)

    def oee(self, ideal_cycle_time_s: float) -> float:
        return self.availability * self.performance(ideal_cycle_time_s) * self.quality

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ProductionRecord machine={self.machine_id} "
            f"bucket={self.bucket_start:%Y-%m-%d %H:00} good={self.good_count}>"
        )
