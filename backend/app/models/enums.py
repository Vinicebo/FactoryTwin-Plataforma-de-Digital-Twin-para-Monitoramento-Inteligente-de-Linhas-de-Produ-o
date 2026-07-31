"""Enumerações do domínio industrial (ver `docs/01-planejamento.md`)."""

from __future__ import annotations

from enum import Enum


class MachineStatus(str, Enum):
    """Estados da máquina de estados finita de cada equipamento."""

    RUNNING = "RUNNING"
    IDLE = "IDLE"
    SETUP = "SETUP"
    MAINTENANCE = "MAINTENANCE"
    FAULT = "FAULT"
    OFFLINE = "OFFLINE"

    @property
    def is_available(self) -> bool:
        """Só `RUNNING` conta como tempo disponível no cálculo de OEE."""
        return self is MachineStatus.RUNNING

    @property
    def is_stopped_unplanned(self) -> bool:
        return self is MachineStatus.FAULT


class MachineType(str, Enum):
    INJECTOR = "INJECTOR"
    CONVEYOR = "CONVEYOR"
    ROBOT = "ROBOT"
    PAINT_BOOTH = "PAINT_BOOTH"
    OVEN = "OVEN"
    INSPECTION = "INSPECTION"
    PACKAGER = "PACKAGER"
    PALLETIZER = "PALLETIZER"


class AlarmCode(str, Enum):
    HIGH_TEMPERATURE = "HIGH_TEMPERATURE"
    LOW_EFFICIENCY = "LOW_EFFICIENCY"
    OVERSPEED = "OVERSPEED"
    UNDERSPEED = "UNDERSPEED"
    HIGH_VIBRATION = "HIGH_VIBRATION"
    HIGH_PRESSURE = "HIGH_PRESSURE"
    MACHINE_FAULT = "MACHINE_FAULT"
    ANOMALY_DETECTED = "ANOMALY_DETECTED"


class AlarmSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        return {"INFO": 0, "WARNING": 1, "CRITICAL": 2}[self.value]


class AlarmStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class UserRole(str, Enum):
    """Perfis de acesso. A ordem em `level` define a hierarquia de permissão."""

    VIEWER = "VIEWER"
    OPERATOR = "OPERATOR"
    ADMIN = "ADMIN"

    @property
    def level(self) -> int:
        return {"VIEWER": 0, "OPERATOR": 1, "ADMIN": 2}[self.value]

    def satisfies(self, required: UserRole) -> bool:
        return self.level >= required.level
