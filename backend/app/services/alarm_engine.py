"""Motor de regras de alarme (Fase 7).

Avalia cada leitura contra os limites cadastrados na própria máquina e mantém
o ciclo de vida dos alarmes:

* **Deduplicação** — existe no máximo um alarme aberto por `(máquina, código)`.
* **Escalonamento** — se a condição piora (WARNING → CRITICAL), o alarme aberto
  é promovido em vez de um novo ser criado.
* **Histerese** — o alarme só é resolvido quando a grandeza volta com uma folga
  (`DEADBAND`) além do limite, evitando alarmes piscando no entorno do gatilho.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.crud import alarm_crud
from app.db.base import utcnow
from app.models import Alarm, Machine, SensorReading
from app.models.enums import AlarmCode, AlarmSeverity, AlarmStatus, MachineStatus

logger = logging.getLogger(__name__)

#: Folga relativa para resolver um alarme (5% do limite).
DEADBAND = 0.05


@dataclass(frozen=True)
class Violation:
    code: AlarmCode
    severity: AlarmSeverity
    message: str
    measured_value: float | None
    threshold: float | None


@dataclass
class EngineResult:
    raised: list[Alarm]
    escalated: list[Alarm]
    resolved: list[Alarm]

    @property
    def changed(self) -> bool:
        return bool(self.raised or self.escalated or self.resolved)


def evaluate_reading(machine: Machine, reading: SensorReading) -> list[Violation]:
    """Aplica todas as regras e devolve as violações ativas nesta amostra."""
    violations: list[Violation] = []

    # --- Temperatura ------------------------------------------------------
    if reading.temperature > machine.temp_critical:
        violations.append(
            Violation(
                AlarmCode.HIGH_TEMPERATURE,
                AlarmSeverity.CRITICAL,
                f"Temperatura crítica: {reading.temperature:.1f} °C "
                f"(limite {machine.temp_critical:.1f} °C)",
                reading.temperature,
                machine.temp_critical,
            )
        )
    elif reading.temperature > machine.temp_warning:
        violations.append(
            Violation(
                AlarmCode.HIGH_TEMPERATURE,
                AlarmSeverity.WARNING,
                f"Temperatura acima do normal: {reading.temperature:.1f} °C "
                f"(limite {machine.temp_warning:.1f} °C)",
                reading.temperature,
                machine.temp_warning,
            )
        )

    # --- Eficiência (só faz sentido com a máquina produzindo) -------------
    if reading.status is MachineStatus.RUNNING:
        if reading.efficiency < machine.eff_critical:
            violations.append(
                Violation(
                    AlarmCode.LOW_EFFICIENCY,
                    AlarmSeverity.CRITICAL,
                    f"Eficiência crítica: {reading.efficiency:.1f}% "
                    f"(mínimo {machine.eff_critical:.1f}%)",
                    reading.efficiency,
                    machine.eff_critical,
                )
            )
        elif reading.efficiency < machine.eff_warning:
            violations.append(
                Violation(
                    AlarmCode.LOW_EFFICIENCY,
                    AlarmSeverity.WARNING,
                    f"Eficiência abaixo da meta: {reading.efficiency:.1f}% "
                    f"(mínimo {machine.eff_warning:.1f}%)",
                    reading.efficiency,
                    machine.eff_warning,
                )
            )

    # --- Velocidade -------------------------------------------------------
    if reading.speed > machine.speed_max:
        violations.append(
            Violation(
                AlarmCode.OVERSPEED,
                AlarmSeverity.WARNING,
                f"Velocidade acima do máximo: {reading.speed:.1f} "
                f"(máx {machine.speed_max:.1f})",
                reading.speed,
                machine.speed_max,
            )
        )
    elif reading.status is MachineStatus.RUNNING and reading.speed < machine.speed_min:
        violations.append(
            Violation(
                AlarmCode.UNDERSPEED,
                AlarmSeverity.WARNING,
                f"Velocidade abaixo do mínimo: {reading.speed:.1f} "
                f"(mín {machine.speed_min:.1f})",
                reading.speed,
                machine.speed_min,
            )
        )

    # --- Vibração ---------------------------------------------------------
    if reading.vibration > machine.vib_critical:
        violations.append(
            Violation(
                AlarmCode.HIGH_VIBRATION,
                AlarmSeverity.CRITICAL,
                f"Vibração crítica: {reading.vibration:.2f} mm/s "
                f"(limite {machine.vib_critical:.2f})",
                reading.vibration,
                machine.vib_critical,
            )
        )
    elif reading.vibration > machine.vib_warning:
        violations.append(
            Violation(
                AlarmCode.HIGH_VIBRATION,
                AlarmSeverity.WARNING,
                f"Vibração elevada: {reading.vibration:.2f} mm/s "
                f"(limite {machine.vib_warning:.2f})",
                reading.vibration,
                machine.vib_warning,
            )
        )

    # --- Pressão ----------------------------------------------------------
    if machine.pressure_max > 0 and reading.pressure > machine.pressure_max:
        violations.append(
            Violation(
                AlarmCode.HIGH_PRESSURE,
                AlarmSeverity.WARNING,
                f"Pressão acima do máximo: {reading.pressure:.1f} bar "
                f"(máx {machine.pressure_max:.1f})",
                reading.pressure,
                machine.pressure_max,
            )
        )

    # --- Falha de máquina -------------------------------------------------
    if reading.status is MachineStatus.FAULT:
        violations.append(
            Violation(
                AlarmCode.MACHINE_FAULT,
                AlarmSeverity.CRITICAL,
                f"{machine.name} em falha — parada não planejada",
                None,
                None,
            )
        )

    # --- Anomalia detectada pelo modelo de ML (Fase 8) --------------------
    if reading.is_anomaly:
        score = reading.anomaly_score
        violations.append(
            Violation(
                AlarmCode.ANOMALY_DETECTED,
                AlarmSeverity.WARNING,
                "Padrão anômalo detectado pelo modelo de IA"
                + (f" (score {score:.3f})" if score is not None else ""),
                score,
                None,
            )
        )

    return violations


def _condition_cleared(alarm: Alarm, reading: SensorReading, machine: Machine) -> bool:
    """A grandeza voltou ao normal *com folga*? (histerese)."""
    match alarm.code:
        case AlarmCode.HIGH_TEMPERATURE:
            return reading.temperature < machine.temp_warning * (1 - DEADBAND)
        case AlarmCode.LOW_EFFICIENCY:
            return reading.efficiency > machine.eff_warning * (1 + DEADBAND)
        case AlarmCode.OVERSPEED:
            return reading.speed < machine.speed_max * (1 - DEADBAND)
        case AlarmCode.UNDERSPEED:
            return reading.speed > machine.speed_min * (1 + DEADBAND)
        case AlarmCode.HIGH_VIBRATION:
            return reading.vibration < machine.vib_warning * (1 - DEADBAND)
        case AlarmCode.HIGH_PRESSURE:
            return reading.pressure < machine.pressure_max * (1 - DEADBAND)
        case AlarmCode.MACHINE_FAULT:
            return reading.status is not MachineStatus.FAULT
        case AlarmCode.ANOMALY_DETECTED:
            return not reading.is_anomaly
    return False


def process(db: Session, machine: Machine, reading: SensorReading) -> EngineResult:
    """Reconcilia os alarmes abertos da máquina com a leitura recém-chegada.

    Não faz commit — quem chama controla a transação (o simulador agrupa o
    commit de várias máquinas num só).
    """
    violations = evaluate_reading(machine, reading)
    by_code = {v.code: v for v in violations}

    result = EngineResult(raised=[], escalated=[], resolved=[])

    open_alarms, _ = alarm_crud.list_filtered(db, machine_id=machine.id, only_open=True, limit=100)
    open_by_code = {alarm.code: alarm for alarm in open_alarms}

    # 1) Novas violações e escalonamentos.
    for code, violation in by_code.items():
        existing = open_by_code.get(code)
        if existing is None:
            alarm = Alarm(
                machine_id=machine.id,
                code=violation.code,
                severity=violation.severity,
                status=AlarmStatus.ACTIVE,
                message=violation.message,
                measured_value=violation.measured_value,
                threshold=violation.threshold,
                triggered_at=reading.ts,
            )
            db.add(alarm)
            result.raised.append(alarm)
        elif violation.severity.rank > existing.severity.rank:
            existing.severity = violation.severity
            existing.message = violation.message
            existing.measured_value = violation.measured_value
            existing.threshold = violation.threshold
            # Uma escalada reabre o alarme: um WARNING já reconhecido que virou
            # CRITICAL precisa de nova atenção do operador.
            existing.status = AlarmStatus.ACTIVE
            existing.acknowledged_at = None
            db.add(existing)
            result.escalated.append(existing)

    # 2) Alarmes cuja condição já passou.
    for code, alarm in open_by_code.items():
        if code in by_code:
            continue
        if _condition_cleared(alarm, reading, machine):
            alarm.status = AlarmStatus.RESOLVED
            alarm.resolved_at = utcnow()
            db.add(alarm)
            result.resolved.append(alarm)

    return result
