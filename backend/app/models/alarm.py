"""Tabela `alarms` — eventos disparados pelo motor de regras (Fase 7)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.enums import AlarmCode, AlarmSeverity, AlarmStatus

if TYPE_CHECKING:  # pragma: no cover
    from app.models.machine import Machine
    from app.models.user import User


class Alarm(Base):
    __tablename__ = "alarms"
    __table_args__ = (
        # Consulta mais quente do sistema: alarmes ativos de uma máquina.
        Index("ix_alarms_machine_status", "machine_id", "status"),
        Index("ix_alarms_status_triggered", "status", "triggered_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    machine_id: Mapped[int] = mapped_column(
        ForeignKey("machines.id", ondelete="CASCADE"), nullable=False, index=True
    )

    code: Mapped[AlarmCode] = mapped_column(
        SAEnum(AlarmCode, native_enum=False, length=30), nullable=False, index=True
    )
    severity: Mapped[AlarmSeverity] = mapped_column(
        SAEnum(AlarmSeverity, native_enum=False, length=10), nullable=False, index=True
    )
    status: Mapped[AlarmStatus] = mapped_column(
        SAEnum(AlarmStatus, native_enum=False, length=15),
        default=AlarmStatus.ACTIVE,
        nullable=False,
    )

    message: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Valor medido e limite violado — preservados para auditoria.
    measured_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)

    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    acknowledged_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    machine: Mapped[Machine] = relationship(back_populates="alarms")
    acknowledged_by: Mapped[User | None] = relationship(back_populates="acknowledged_alarms")

    @property
    def is_open(self) -> bool:
        return self.status is not AlarmStatus.RESOLVED

    @property
    def duration_s(self) -> float | None:
        if self.resolved_at is None:
            return None
        return (self.resolved_at - self.triggered_at).total_seconds()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Alarm {self.code.value} machine={self.machine_id} {self.status.value}>"
