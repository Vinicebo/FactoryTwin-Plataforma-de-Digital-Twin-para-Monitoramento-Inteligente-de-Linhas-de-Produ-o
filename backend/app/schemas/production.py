"""Schemas de produção e KPIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ProductionRecordCreate(BaseModel):
    machine_id: int
    bucket_start: datetime | None = None
    shift: str = Field(default="A", max_length=10)
    good_count: int = Field(default=0, ge=0)
    scrap_count: int = Field(default=0, ge=0)
    planned_time_s: float = Field(default=0.0, ge=0)
    runtime_s: float = Field(default=0.0, ge=0)
    downtime_s: float = Field(default=0.0, ge=0)
    energy_kwh: float = Field(default=0.0, ge=0)


class ProductionRecordUpdate(BaseModel):
    good_count: int | None = Field(default=None, ge=0)
    scrap_count: int | None = Field(default=None, ge=0)
    planned_time_s: float | None = Field(default=None, ge=0)
    runtime_s: float | None = Field(default=None, ge=0)
    downtime_s: float | None = Field(default=None, ge=0)
    energy_kwh: float | None = Field(default=None, ge=0)
    shift: str | None = Field(default=None, max_length=10)


class ProductionRecordRead(ORMModel):
    id: int
    machine_id: int
    bucket_start: datetime
    shift: str
    good_count: int
    scrap_count: int
    planned_time_s: float
    runtime_s: float
    downtime_s: float
    energy_kwh: float
    fault_count: int


class OEEMetrics(BaseModel):
    """OEE decomposto nos três fatores, em fração 0–1."""

    machine_id: int | None = None
    machine_code: str | None = None
    availability: float = Field(..., ge=0, le=1)
    performance: float = Field(..., ge=0, le=1)
    quality: float = Field(..., ge=0, le=1)
    oee: float = Field(..., ge=0, le=1)
    good_count: int
    scrap_count: int
    total_count: int
    scrap_rate: float
    energy_kwh: float
    energy_per_part: float | None = None
    fault_count: int
    mtbf_minutes: float | None = None
    mttr_minutes: float | None = None
    window_start: datetime
    window_end: datetime


class LineSummary(BaseModel):
    """Visão agregada da linha inteira — cabeçalho do dashboard."""

    line: str
    machines_total: int
    machines_running: int
    machines_faulted: int
    machines_idle: int
    active_alarms: int
    critical_alarms: int
    oee: float
    good_count: int
    scrap_count: int
    scrap_rate: float
    energy_kwh: float
    avg_efficiency: float
    window_start: datetime
    window_end: datetime
