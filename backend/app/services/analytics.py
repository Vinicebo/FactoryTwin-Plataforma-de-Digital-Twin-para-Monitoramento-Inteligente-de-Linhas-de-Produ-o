"""Cálculo de KPIs: OEE, confiabilidade e o resumo da linha.

Concentrar as fórmulas aqui garante que a API REST, o WebSocket e os testes
vejam exatamente os mesmos números.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crud import alarm_crud, machine_crud, production_crud
from app.models import Machine
from app.models.enums import AlarmSeverity, AlarmStatus, MachineStatus
from app.schemas.machine import MachineLive
from app.schemas.production import LineSummary, OEEMetrics


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def compute_oee(db: Session, *, machine_id: int | None = None, hours: int = 8) -> OEEMetrics:
    """OEE de uma máquina (ou da linha inteira, se `machine_id` for None)."""
    totals = production_crud.aggregate(db, machine_id=machine_id, hours=hours)

    machine_code = None
    if machine_id is not None:
        machine = machine_crud.get(db, machine_id)
        machine_code = machine.code if machine else None
        ideal_cycle = machine.ideal_cycle_time_s if machine else 0.0
    else:
        ideal_cycle = production_crud.weighted_ideal_cycle_time(db, hours=hours)

    good = totals["good_count"]
    scrap = totals["scrap_count"]
    total = good + scrap
    runtime = totals["runtime_s"]
    planned = totals["planned_time_s"]
    faults = totals["fault_count"]

    availability = min(_safe_div(runtime, planned), 1.0)
    performance = min(_safe_div(total * ideal_cycle, runtime), 1.0)
    quality = _safe_div(good, total)

    # MTBF/MTTR só fazem sentido quando houve pelo menos uma falha na janela.
    mtbf = _safe_div(runtime, faults) / 60 if faults else None
    mttr = _safe_div(totals["downtime_s"], faults) / 60 if faults else None

    return OEEMetrics(
        machine_id=machine_id,
        machine_code=machine_code,
        availability=availability,
        performance=performance,
        quality=quality,
        oee=availability * performance * quality,
        good_count=good,
        scrap_count=scrap,
        total_count=total,
        scrap_rate=_safe_div(scrap, total),
        energy_kwh=totals["energy_kwh"],
        energy_per_part=_safe_div(totals["energy_kwh"], total) if total else None,
        fault_count=faults,
        mtbf_minutes=mtbf,
        mttr_minutes=mttr,
        window_start=totals["window_start"],
        window_end=totals["window_end"],
    )


def compute_line_summary(db: Session, *, line: str = "LINE-01", hours: int = 8) -> LineSummary:
    """Cabeçalho do dashboard: estados, alarmes e KPIs agregados da linha."""
    status_counts = dict(
        db.execute(
            select(Machine.status, func.count())
            .where(Machine.line == line, Machine.is_active.is_(True))
            .group_by(Machine.status)
        ).all()
    )
    machines_total = sum(status_counts.values())

    stats = alarm_crud.stats(db)
    active_alarms = stats["total_active"]
    critical_alarms = stats["by_severity"].get(AlarmSeverity.CRITICAL.value, 0)

    oee = compute_oee(db, machine_id=None, hours=hours)

    latest = machine_crud.latest_readings_map(db)
    efficiencies = [
        reading.efficiency
        for reading in latest.values()
        if reading.status is MachineStatus.RUNNING
    ]
    avg_efficiency = sum(efficiencies) / len(efficiencies) if efficiencies else 0.0

    return LineSummary(
        line=line,
        machines_total=machines_total,
        machines_running=status_counts.get(MachineStatus.RUNNING, 0),
        machines_faulted=status_counts.get(MachineStatus.FAULT, 0),
        machines_idle=status_counts.get(MachineStatus.IDLE, 0),
        active_alarms=active_alarms,
        critical_alarms=critical_alarms,
        oee=oee.oee,
        good_count=oee.good_count,
        scrap_count=oee.scrap_count,
        scrap_rate=oee.scrap_rate,
        energy_kwh=oee.energy_kwh,
        avg_efficiency=avg_efficiency,
        window_start=oee.window_start,
        window_end=oee.window_end,
    )


def build_live_machines(db: Session, *, line: str | None = None) -> list[MachineLive]:
    """Máquinas com a última telemetria embutida — payload do mapa da fábrica.

    Resolve tudo em três queries (máquinas, últimas leituras, alarmes abertos),
    sem N+1.
    """
    machines, _ = machine_crud.list_filtered(db, line=line, limit=500)
    latest = machine_crud.latest_readings_map(db)
    alarms = machine_crud.active_alarm_summary(db)

    live: list[MachineLive] = []
    for machine in machines:
        payload = MachineLive.model_validate(machine)
        reading = latest.get(machine.id)
        if reading is not None:
            payload.temperature = reading.temperature
            payload.speed = reading.speed
            payload.efficiency = reading.efficiency
            payload.energy = reading.energy
            payload.vibration = reading.vibration
            payload.pressure = reading.pressure
            payload.last_reading_at = reading.ts
            payload.is_anomaly = reading.is_anomaly

        count, severity = alarms.get(machine.id, (0, None))
        payload.active_alarms = count
        payload.highest_severity = severity
        live.append(payload)

    return live


def machine_oee_ranking(db: Session, *, hours: int = 8) -> list[OEEMetrics]:
    """OEE de cada máquina, da pior para a melhor — identifica o gargalo."""
    machines, _ = machine_crud.list_filtered(db, only_active=True, limit=500)
    metrics = [compute_oee(db, machine_id=m.id, hours=hours) for m in machines]
    return sorted(metrics, key=lambda m: m.oee)


def open_alarm_count(db: Session) -> int:
    from app.models import Alarm

    return (
        db.scalar(
            select(func.count()).select_from(Alarm).where(Alarm.status != AlarmStatus.RESOLVED)
        )
        or 0
    )
