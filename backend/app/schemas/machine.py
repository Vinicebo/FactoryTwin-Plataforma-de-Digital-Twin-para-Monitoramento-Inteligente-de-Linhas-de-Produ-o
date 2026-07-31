"""Schemas de máquina."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import MachineStatus, MachineType
from app.schemas.common import ORMModel


class MachineThresholds(BaseModel):
    """Limites de processo. Separados para poderem ser editados em bloco."""

    temp_nominal: float = 70.0
    temp_warning: float = 85.0
    temp_critical: float = 95.0
    speed_nominal: float = 100.0
    speed_min: float = 60.0
    speed_max: float = 140.0
    eff_warning: float = Field(default=75.0, ge=0, le=100)
    eff_critical: float = Field(default=60.0, ge=0, le=100)
    vib_warning: float = 4.5
    vib_critical: float = 7.1
    pressure_nominal: float = 6.0
    pressure_max: float = 10.0
    energy_nominal: float = 15.0

    @model_validator(mode="after")
    def _check_ordering(self) -> MachineThresholds:
        # Limites invertidos tornariam o motor de alarmes incoerente (um alarme
        # crítico nunca dispararia, ou dispararia antes do de aviso).
        if self.temp_warning >= self.temp_critical:
            raise ValueError("temp_warning deve ser menor que temp_critical")
        if self.eff_critical >= self.eff_warning:
            raise ValueError("eff_critical deve ser menor que eff_warning")
        if self.vib_warning >= self.vib_critical:
            raise ValueError("vib_warning deve ser menor que vib_critical")
        if self.speed_min >= self.speed_max:
            raise ValueError("speed_min deve ser menor que speed_max")
        return self


class MachineCreate(MachineThresholds):
    code: str = Field(..., min_length=2, max_length=20, pattern=r"^[A-Z0-9-]+$")
    name: str = Field(..., min_length=2, max_length=120)
    machine_type: MachineType
    line: str = Field(default="LINE-01", max_length=40)
    sequence: int = Field(default=1, ge=1)
    pos_x: float = Field(default=50.0, ge=0, le=100)
    pos_y: float = Field(default=50.0, ge=0, le=100)
    ideal_cycle_time_s: float = Field(default=6.0, gt=0)


class MachineUpdate(BaseModel):
    """Atualização parcial — todo campo é opcional."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    line: str | None = Field(default=None, max_length=40)
    sequence: int | None = Field(default=None, ge=1)
    pos_x: float | None = Field(default=None, ge=0, le=100)
    pos_y: float | None = Field(default=None, ge=0, le=100)
    ideal_cycle_time_s: float | None = Field(default=None, gt=0)
    is_active: bool | None = None

    temp_nominal: float | None = None
    temp_warning: float | None = None
    temp_critical: float | None = None
    speed_nominal: float | None = None
    speed_min: float | None = None
    speed_max: float | None = None
    eff_warning: float | None = Field(default=None, ge=0, le=100)
    eff_critical: float | None = Field(default=None, ge=0, le=100)
    vib_warning: float | None = None
    vib_critical: float | None = None
    pressure_nominal: float | None = None
    pressure_max: float | None = None
    energy_nominal: float | None = None


class MachineStatusUpdate(BaseModel):
    status: MachineStatus
    reason: str | None = Field(default=None, max_length=255)


class MachineRead(ORMModel):
    id: int
    code: str
    name: str
    machine_type: MachineType
    line: str
    sequence: int
    status: MachineStatus
    is_active: bool
    pos_x: float
    pos_y: float
    ideal_cycle_time_s: float

    temp_nominal: float
    temp_warning: float
    temp_critical: float
    speed_nominal: float
    speed_min: float
    speed_max: float
    eff_warning: float
    eff_critical: float
    vib_warning: float
    vib_critical: float
    pressure_nominal: float
    pressure_max: float
    energy_nominal: float

    created_at: datetime
    updated_at: datetime


class MachineLive(MachineRead):
    """Máquina + última telemetria + contagem de alarmes abertos.

    É o payload que alimenta o mapa da fábrica no dashboard.
    """

    temperature: float | None = None
    speed: float | None = None
    efficiency: float | None = None
    energy: float | None = None
    vibration: float | None = None
    pressure: float | None = None
    last_reading_at: datetime | None = None
    active_alarms: int = 0
    highest_severity: str | None = None
    is_anomaly: bool = False
