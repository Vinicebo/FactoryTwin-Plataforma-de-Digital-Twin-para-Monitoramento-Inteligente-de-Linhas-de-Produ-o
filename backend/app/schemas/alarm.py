"""Schemas de alarme."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import AlarmCode, AlarmSeverity, AlarmStatus
from app.schemas.common import ORMModel


class AlarmCreate(BaseModel):
    machine_id: int
    code: AlarmCode
    severity: AlarmSeverity
    message: str = Field(..., max_length=255)
    measured_value: float | None = None
    threshold: float | None = None


class AlarmRead(ORMModel):
    id: int
    machine_id: int
    code: AlarmCode
    severity: AlarmSeverity
    status: AlarmStatus
    message: str
    measured_value: float | None
    threshold: float | None
    triggered_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    acknowledged_by_id: int | None


class AlarmWithMachine(AlarmRead):
    machine_code: str
    machine_name: str


class AlarmAcknowledge(BaseModel):
    note: str | None = Field(default=None, max_length=255)


class AlarmStats(BaseModel):
    total_active: int
    by_severity: dict[str, int]
    by_code: dict[str, int]
    by_machine: dict[str, int]
