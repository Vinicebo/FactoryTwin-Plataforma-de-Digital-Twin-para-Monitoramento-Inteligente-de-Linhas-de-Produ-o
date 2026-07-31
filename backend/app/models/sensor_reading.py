"""Tabela `sensor_readings` — série temporal das grandezas medidas."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.enums import MachineStatus

if TYPE_CHECKING:  # pragma: no cover
    from app.models.machine import Machine


class SensorReading(Base):
    """Uma amostra consolidada de todos os sensores de uma máquina."""

    __tablename__ = "sensor_readings"
    __table_args__ = (
        # Índice composto: praticamente toda consulta é "leituras da máquina X
        # nas últimas N horas, mais recentes primeiro".
        Index("ix_sensor_readings_machine_ts", "machine_id", "ts"),
    )

    # BIGINT porque a série temporal cresce rápido; no SQLite cai para INTEGER,
    # que é o único tipo com AUTOINCREMENT nesse dialeto.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    machine_id: Mapped[int] = mapped_column(
        ForeignKey("machines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    # --- Grandezas medidas ------------------------------------------------
    temperature: Mapped[float] = mapped_column(Float, nullable=False)  # °C
    speed: Mapped[float] = mapped_column(Float, nullable=False)  # rpm | m/min
    efficiency: Mapped[float] = mapped_column(Float, nullable=False)  # %
    energy: Mapped[float] = mapped_column(Float, nullable=False)  # kW
    vibration: Mapped[float] = mapped_column(Float, nullable=False)  # mm/s RMS
    pressure: Mapped[float] = mapped_column(Float, nullable=False)  # bar

    #: Estado da máquina no instante da amostra (desnormalizado de propósito:
    #: evita join para reconstruir a linha do tempo de disponibilidade).
    status: Mapped[MachineStatus] = mapped_column(
        SAEnum(MachineStatus, native_enum=False, length=20), nullable=False
    )

    # --- Saída do modelo de anomalias (Fase 8) ---------------------------
    anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    machine: Mapped[Machine] = relationship(back_populates="readings")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SensorReading machine={self.machine_id} ts={self.ts:%H:%M:%S}>"
