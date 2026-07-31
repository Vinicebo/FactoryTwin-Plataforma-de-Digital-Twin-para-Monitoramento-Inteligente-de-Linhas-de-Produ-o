"""Schemas de leitura de sensores."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import MachineStatus
from app.schemas.common import ORMModel


class SensorReadingCreate(BaseModel):
    """Ingestão manual de telemetria (útil para testes e integrações externas)."""

    machine_id: int
    temperature: float
    speed: float
    efficiency: float = Field(..., ge=0, le=100)
    energy: float = Field(..., ge=0)
    vibration: float = Field(..., ge=0)
    pressure: float = Field(..., ge=0)
    status: MachineStatus = MachineStatus.RUNNING
    ts: datetime | None = None


class SensorReadingRead(ORMModel):
    id: int
    machine_id: int
    ts: datetime
    temperature: float
    speed: float
    efficiency: float
    energy: float
    vibration: float
    pressure: float
    status: MachineStatus
    anomaly_score: float | None = None
    is_anomaly: bool = False


class SeriesPoint(BaseModel):
    """Ponto de uma série temporal já reamostrada para o gráfico."""

    ts: datetime
    value: float


class MetricSeries(BaseModel):
    machine_id: int
    metric: str
    unit: str
    points: list[SeriesPoint]
