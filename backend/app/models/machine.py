"""Tabela `machines` — o gêmeo digital de cada equipamento da linha."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import MachineStatus, MachineType

if TYPE_CHECKING:  # pragma: no cover
    from app.models.alarm import Alarm
    from app.models.production import ProductionRecord
    from app.models.sensor_reading import SensorReading


def _status_enum() -> SAEnum:
    # `native_enum=False` gera VARCHAR + CHECK, portável entre SQLite e Postgres.
    return SAEnum(MachineStatus, native_enum=False, length=20, validate_strings=True)


class Machine(TimestampMixin, Base):
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    machine_type: Mapped[MachineType] = mapped_column(
        SAEnum(MachineType, native_enum=False, length=20), nullable=False
    )
    line: Mapped[str] = mapped_column(String(40), default="LINE-01", nullable=False, index=True)
    #: Posição no fluxo produtivo (1 = primeira estação).
    sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    status: Mapped[MachineStatus] = mapped_column(
        _status_enum(), default=MachineStatus.IDLE, nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Posição no mapa da fábrica (plano normalizado 0–100) ------------
    pos_x: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)
    pos_y: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)

    # --- Parâmetros de processo -----------------------------------------
    #: Tempo de ciclo ideal em segundos por peça — base do cálculo de Performance.
    ideal_cycle_time_s: Mapped[float] = mapped_column(Float, default=6.0, nullable=False)

    temp_nominal: Mapped[float] = mapped_column(Float, default=70.0, nullable=False)
    temp_warning: Mapped[float] = mapped_column(Float, default=85.0, nullable=False)
    temp_critical: Mapped[float] = mapped_column(Float, default=95.0, nullable=False)

    speed_nominal: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    speed_min: Mapped[float] = mapped_column(Float, default=60.0, nullable=False)
    speed_max: Mapped[float] = mapped_column(Float, default=140.0, nullable=False)

    eff_warning: Mapped[float] = mapped_column(Float, default=75.0, nullable=False)
    eff_critical: Mapped[float] = mapped_column(Float, default=60.0, nullable=False)

    vib_warning: Mapped[float] = mapped_column(Float, default=4.5, nullable=False)
    vib_critical: Mapped[float] = mapped_column(Float, default=7.1, nullable=False)

    pressure_nominal: Mapped[float] = mapped_column(Float, default=6.0, nullable=False)
    pressure_max: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)

    energy_nominal: Mapped[float] = mapped_column(Float, default=15.0, nullable=False)

    # --- Relacionamentos --------------------------------------------------
    readings: Mapped[list[SensorReading]] = relationship(
        back_populates="machine", cascade="all, delete-orphan", passive_deletes=True
    )
    production_records: Mapped[list[ProductionRecord]] = relationship(
        back_populates="machine", cascade="all, delete-orphan", passive_deletes=True
    )
    alarms: Mapped[list[Alarm]] = relationship(
        back_populates="machine", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Machine {self.code} status={self.status.value}>"
