"""Modelos ORM. Importar este pacote registra tudo no metadata do `Base`."""

from app.models.alarm import Alarm
from app.models.enums import (
    AlarmCode,
    AlarmSeverity,
    AlarmStatus,
    MachineStatus,
    MachineType,
    UserRole,
)
from app.models.machine import Machine
from app.models.production import ProductionRecord
from app.models.sensor_reading import SensorReading
from app.models.user import User

__all__ = [
    "Alarm",
    "AlarmCode",
    "AlarmSeverity",
    "AlarmStatus",
    "Machine",
    "MachineStatus",
    "MachineType",
    "ProductionRecord",
    "SensorReading",
    "User",
    "UserRole",
]
