"""Schemas Pydantic (contratos da API)."""

from app.schemas.alarm import (
    AlarmAcknowledge,
    AlarmCreate,
    AlarmRead,
    AlarmStats,
    AlarmWithMachine,
)
from app.schemas.common import Message, ORMModel, Page
from app.schemas.machine import (
    MachineCreate,
    MachineLive,
    MachineRead,
    MachineStatusUpdate,
    MachineUpdate,
)
from app.schemas.production import (
    LineSummary,
    OEEMetrics,
    ProductionRecordCreate,
    ProductionRecordRead,
    ProductionRecordUpdate,
)
from app.schemas.sensor import MetricSeries, SensorReadingCreate, SensorReadingRead, SeriesPoint
from app.schemas.user import LoginRequest, Token, UserCreate, UserRead, UserUpdate

__all__ = [
    "AlarmAcknowledge",
    "AlarmCreate",
    "AlarmRead",
    "AlarmStats",
    "AlarmWithMachine",
    "LineSummary",
    "LoginRequest",
    "MachineCreate",
    "MachineLive",
    "MachineRead",
    "MachineStatusUpdate",
    "MachineUpdate",
    "Message",
    "MetricSeries",
    "OEEMetrics",
    "ORMModel",
    "Page",
    "ProductionRecordCreate",
    "ProductionRecordRead",
    "ProductionRecordUpdate",
    "SensorReadingCreate",
    "SensorReadingRead",
    "SeriesPoint",
    "Token",
    "UserCreate",
    "UserRead",
    "UserUpdate",
]
