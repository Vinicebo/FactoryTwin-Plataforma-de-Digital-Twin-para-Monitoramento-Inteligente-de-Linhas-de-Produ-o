"""Simulador da linha de produção (Fase 4).

Faz o gêmeo digital "andar": a cada tick avança a máquina de estados de cada
equipamento, gera telemetria plausível, alimenta o motor de alarmes, atualiza
os contadores de produção e publica tudo no WebSocket.

Escolhas de modelagem que dão realismo sem virar um simulador físico:

* **Inércia térmica** — a temperatura persegue um alvo por um filtro de primeira
  ordem, então aquecimento e resfriamento levam vários ticks.
* **Desgaste** — um acumulador por máquina aumenta a vibração e a chance de
  falha ao longo do tempo, e zera na manutenção.
* **Estrangulamento a jusante** — se a estação anterior para, a seguinte perde
  eficiência e acaba entrando em `IDLE` por falta de material.

O trabalho de banco roda em thread separada (`asyncio.to_thread`) para não
bloquear o event loop que serve a API.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud import production_crud
from app.db.base import utcnow
from app.db.session import session_scope
from app.models import Machine, SensorReading
from app.models.enums import MachineStatus
from app.schemas.sensor import SensorReadingRead
from app.services import alarm_engine
from app.services.analytics import compute_line_summary
from app.services.anomaly import detector
from app.services.realtime import EventType, build_event, manager

logger = logging.getLogger(__name__)

#: Temperatura ambiente do galpão (°C) — alvo do resfriamento.
AMBIENT_TEMPERATURE = 24.0
#: Constante do filtro de primeira ordem: fração do erro corrigida por tick.
THERMAL_RESPONSE = 0.18
#: Ticks entre dois envios do resumo consolidado da linha.
SUMMARY_EVERY_TICKS = 5
#: Máquina em falha fica parada entre 15 e 60 ticks (reparo).
FAULT_TICKS = (15, 60)
#: Manutenção pós-reparo.
MAINTENANCE_TICKS = (5, 15)
#: Setup antes de voltar a produzir.
SETUP_TICKS = (2, 6)
#: Ticks sem material a montante antes de a máquina entrar em IDLE.
STARVATION_TICKS = 4


@dataclass
class MachineState:
    """Estado interno do simulador para uma máquina (não vai para o banco)."""

    machine_id: int
    status: MachineStatus = MachineStatus.IDLE
    temperature: float = AMBIENT_TEMPERATURE
    #: Ticks restantes no estado atual (0 = pode transicionar).
    ticks_in_state: int = 0
    state_duration: int = 0
    #: Desgaste acumulado, 0.0–1.0. Sobe produzindo, zera na manutenção.
    wear: float = 0.0
    #: Peças fracionárias acumuladas até fechar uma peça inteira.
    part_accumulator: float = 0.0
    #: Ticks consecutivos sem alimentação da estação anterior.
    starved_ticks: int = 0
    #: Fase da oscilação lenta que dá "vida" aos sinais. Atribuída pelo
    #: simulador a partir do RNG semeado, para o `seed` ser reprodutível.
    phase: float = 0.0


@dataclass
class TickOutcome:
    """O que aconteceu em um tick — vira eventos no WebSocket."""

    telemetry: list[dict[str, Any]] = field(default_factory=list)
    status_changes: list[dict[str, Any]] = field(default_factory=list)
    alarms_raised: list[dict[str, Any]] = field(default_factory=list)
    alarms_resolved: list[dict[str, Any]] = field(default_factory=list)


class LineSimulator:
    def __init__(self, *, tick_seconds: float | None = None, seed: int | None = None) -> None:
        self.tick_seconds = tick_seconds or settings.SIMULATOR_TICK_SECONDS
        self.random = random.Random(seed)
        self._states: dict[int, MachineState] = {}
        self._tick_count = 0
        self._running = False
        self._task: asyncio.Task | None = None

    # --- Controle do laço -------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def tick_count(self) -> int:
        return self._tick_count

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name="factorytwin-simulator")
        logger.info("Simulador iniciado (tick=%.1fs)", self.tick_seconds)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("Simulador parado após %d ticks", self._tick_count)

    async def _run(self) -> None:
        while self._running:
            started = asyncio.get_running_loop().time()
            try:
                outcome = await asyncio.to_thread(self.tick)
                await self._publish(outcome)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Um tick com erro não pode matar o simulador; loga e segue.
                logger.exception("Erro no tick do simulador")

            # Desconta o tempo gasto para manter a cadência estável.
            elapsed = asyncio.get_running_loop().time() - started
            await asyncio.sleep(max(0.0, self.tick_seconds - elapsed))

    async def _publish(self, outcome: TickOutcome) -> None:
        if outcome.telemetry:
            await manager.broadcast(build_event(EventType.TELEMETRY, outcome.telemetry))
        for change in outcome.status_changes:
            await manager.broadcast(build_event(EventType.MACHINE_STATUS, change))
        for alarm in outcome.alarms_raised:
            await manager.broadcast(build_event(EventType.ALARM_RAISED, alarm))
        for alarm in outcome.alarms_resolved:
            await manager.broadcast(build_event(EventType.ALARM_RESOLVED, alarm))

        if self._tick_count % SUMMARY_EVERY_TICKS == 0:
            summary = await asyncio.to_thread(self._line_summary)
            if summary is not None:
                await manager.broadcast(build_event(EventType.LINE_SUMMARY, summary))

    @staticmethod
    def _line_summary() -> dict[str, Any] | None:
        try:
            with session_scope() as db:
                return compute_line_summary(db).model_dump()
        except Exception:
            logger.exception("Falha ao calcular o resumo da linha")
            return None

    # --- Um passo da simulação -------------------------------------------

    def tick(self) -> TickOutcome:
        """Executa um ciclo completo. Síncrono — roda fora do event loop."""
        self._tick_count += 1
        outcome = TickOutcome()

        with session_scope() as db:
            machines = list(
                db.scalars(
                    select(Machine)
                    .where(Machine.is_active.is_(True))
                    .order_by(Machine.line, Machine.sequence)
                ).all()
            )
            if not machines:
                return outcome

            self._sync_states(machines)
            now = utcnow()

            readings: list[tuple[Machine, SensorReading]] = []
            for index, machine in enumerate(machines):
                state = self._states[machine.id]
                upstream = machines[index - 1] if index > 0 else None
                upstream_state = self._states[upstream.id] if upstream else None

                previous_status = state.status
                self._advance_state_machine(machine, state, upstream_state)

                if state.status is not previous_status:
                    machine.status = state.status
                    db.add(machine)
                    outcome.status_changes.append(
                        {
                            "machine_id": machine.id,
                            "machine_code": machine.code,
                            "from": previous_status.value,
                            "to": state.status.value,
                        }
                    )

                reading = self._generate_reading(machine, state, now)
                db.add(reading)
                readings.append((machine, reading))

            # Pontuação de anomalias em lote (uma chamada ao modelo por tick).
            self._score_anomalies(readings)

            # `flush` atribui os ids das leituras antes de serializar/alarmar.
            db.flush()

            for machine, reading in readings:
                state = self._states[machine.id]
                self._update_production(db, machine, state, reading)

                result = alarm_engine.process(db, machine, reading)
                if result.changed:
                    db.flush()
                for alarm in result.raised + result.escalated:
                    outcome.alarms_raised.append(self._alarm_payload(alarm, machine))
                for alarm in result.resolved:
                    outcome.alarms_resolved.append(self._alarm_payload(alarm, machine))

                outcome.telemetry.append(
                    {
                        "machine_id": machine.id,
                        "machine_code": machine.code,
                        **SensorReadingRead.model_validate(reading).model_dump(mode="json"),
                    }
                )

        return outcome

    @staticmethod
    def _alarm_payload(alarm, machine: Machine) -> dict[str, Any]:
        return {
            "id": alarm.id,
            "machine_id": machine.id,
            "machine_code": machine.code,
            "machine_name": machine.name,
            "code": alarm.code.value,
            "severity": alarm.severity.value,
            "status": alarm.status.value,
            "message": alarm.message,
            "measured_value": alarm.measured_value,
            "threshold": alarm.threshold,
            "triggered_at": alarm.triggered_at.isoformat() if alarm.triggered_at else None,
        }

    def _sync_states(self, machines: list[Machine]) -> None:
        """Cria estado para máquinas novas e descarta as que sumiram."""
        known = set(self._states)
        current = {m.id for m in machines}

        for machine in machines:
            if machine.id not in known:
                self._states[machine.id] = MachineState(
                    machine_id=machine.id,
                    status=machine.status,
                    temperature=AMBIENT_TEMPERATURE,
                    phase=self.random.uniform(0, math.tau),
                )
        for stale in known - current:
            del self._states[stale]

    # --- Máquina de estados ----------------------------------------------

    def _advance_state_machine(
        self,
        machine: Machine,
        state: MachineState,
        upstream: MachineState | None,
    ) -> None:
        state.ticks_in_state += 1

        # Estados temporizados: só saem quando a duração se esgota.
        if state.status in (MachineStatus.FAULT, MachineStatus.MAINTENANCE, MachineStatus.SETUP):
            if state.ticks_in_state < state.state_duration:
                return
            match state.status:
                case MachineStatus.FAULT:
                    self._enter(state, MachineStatus.MAINTENANCE, MAINTENANCE_TICKS)
                case MachineStatus.MAINTENANCE:
                    # A manutenção zera o desgaste — é o "reset" do equipamento.
                    state.wear = 0.0
                    self._enter(state, MachineStatus.SETUP, SETUP_TICKS)
                case MachineStatus.SETUP:
                    self._enter(state, MachineStatus.RUNNING, None)
            return

        if state.status is MachineStatus.OFFLINE:
            return

        if state.status is MachineStatus.IDLE:
            # Volta a produzir assim que a estação anterior estiver rodando.
            if upstream is None or upstream.status is MachineStatus.RUNNING:
                self._enter(state, MachineStatus.SETUP, SETUP_TICKS)
            return

        # --- Daqui para baixo: RUNNING ---------------------------------
        # Falha aleatória, com probabilidade crescente conforme o desgaste.
        fault_probability = settings.SIMULATOR_FAULT_PROBABILITY * (1.0 + 4.0 * state.wear)
        if self.random.random() < fault_probability:
            self._enter(state, MachineStatus.FAULT, FAULT_TICKS)
            return

        # Estrangulamento: sem material da estação anterior por tempo suficiente.
        if upstream is not None and upstream.status is not MachineStatus.RUNNING:
            state.starved_ticks += 1
            if state.starved_ticks >= STARVATION_TICKS:
                self._enter(state, MachineStatus.IDLE, None)
                return
        else:
            state.starved_ticks = 0

        # Desgaste acumula ~1% a cada 100 ticks produzindo.
        state.wear = min(1.0, state.wear + 0.0001 * (1.0 + self.random.random()))

    def _enter(
        self, state: MachineState, status: MachineStatus, duration: tuple[int, int] | None
    ) -> None:
        state.status = status
        state.ticks_in_state = 0
        state.state_duration = self.random.randint(*duration) if duration else 0
        if status is not MachineStatus.RUNNING:
            state.starved_ticks = 0

    # --- Geração de telemetria -------------------------------------------

    def _generate_reading(
        self, machine: Machine, state: MachineState, now: datetime
    ) -> SensorReading:
        producing = state.status is MachineStatus.RUNNING
        state.phase += 0.08
        # Oscilação lenta compartilhada por todos os sinais da máquina — é o que
        # faz os gráficos parecerem um processo real, e não ruído branco.
        wave = math.sin(state.phase)

        # Temperatura: persegue o alvo com inércia térmica.
        target = (
            machine.temp_nominal * (1.0 + 0.03 * wave + 0.06 * state.wear)
            if producing
            else AMBIENT_TEMPERATURE
        )
        state.temperature += (target - state.temperature) * THERMAL_RESPONSE
        state.temperature += self.random.gauss(0, 0.4)

        if producing:
            speed = machine.speed_nominal * (1.0 + 0.04 * wave) + self.random.gauss(0, 1.0)
            # Eficiência cai com desgaste e com falta de material a montante.
            starvation_penalty = min(state.starved_ticks * 4.0, 20.0)
            efficiency = (
                92.0
                - 18.0 * state.wear
                - starvation_penalty
                + 3.0 * wave
                + self.random.gauss(0, 1.5)
            )
            load = max(0.0, efficiency / 100.0)
            energy = machine.energy_nominal * (0.55 + 0.5 * load) + self.random.gauss(0, 0.6)
            vibration = (
                machine.vib_warning * (0.45 + 0.55 * state.wear)
                + 0.15 * abs(wave)
                + abs(self.random.gauss(0, 0.12))
            )
            pressure = machine.pressure_nominal * (1.0 + 0.03 * wave) + self.random.gauss(0, 0.15)
        else:
            speed = max(0.0, self.random.gauss(0, 0.3))
            efficiency = 0.0
            # Consumo de espera: motores e controles seguem energizados.
            energy = machine.energy_nominal * 0.12 + self.random.gauss(0, 0.2)
            # Uma falha costuma vir acompanhada de vibração anormal.
            vibration = (
                machine.vib_critical * (1.05 + 0.2 * self.random.random())
                if state.status is MachineStatus.FAULT
                else abs(self.random.gauss(0, 0.15))
            )
            pressure = machine.pressure_nominal * 0.15 + abs(self.random.gauss(0, 0.1))

        return SensorReading(
            machine_id=machine.id,
            ts=now,
            temperature=round(max(0.0, state.temperature), 2),
            speed=round(max(0.0, speed), 2),
            efficiency=round(min(100.0, max(0.0, efficiency)), 2),
            energy=round(max(0.0, energy), 2),
            vibration=round(max(0.0, vibration), 3),
            pressure=round(max(0.0, pressure), 2),
            status=state.status,
        )

    def _score_anomalies(self, readings: list[tuple[Machine, SensorReading]]) -> None:
        if not settings.ML_SCORING_ENABLED:
            return
        scores = detector.score_batch(readings)
        if scores is None:
            return
        for (_, reading), score in zip(readings, scores, strict=False):
            reading.anomaly_score = score.score
            reading.is_anomaly = score.is_anomaly

    # --- Contabilidade de produção ---------------------------------------

    def _update_production(
        self, db: Session, machine: Machine, state: MachineState, reading: SensorReading
    ) -> None:
        record = production_crud.get_or_create_bucket(db, machine.id)

        # Todo tick conta como tempo planejado (a linha está escalada).
        record.planned_time_s += self.tick_seconds

        if state.status is MachineStatus.RUNNING:
            record.runtime_s += self.tick_seconds

            # Peças no tick = tempo / ciclo ideal, ajustado por velocidade e eficiência.
            speed_ratio = (
                reading.speed / machine.speed_nominal if machine.speed_nominal > 0 else 1.0
            )
            produced = (
                self.tick_seconds
                / machine.ideal_cycle_time_s
                * speed_ratio
                * (reading.efficiency / 100.0)
            )
            state.part_accumulator += produced

            whole_parts = int(state.part_accumulator)
            if whole_parts > 0:
                state.part_accumulator -= whole_parts
                # Refugo sobe com o desgaste e quando o processo está anômalo.
                scrap_rate = 0.015 + 0.05 * state.wear + (0.06 if reading.is_anomaly else 0.0)
                scrap = sum(1 for _ in range(whole_parts) if self.random.random() < scrap_rate)
                record.good_count += whole_parts - scrap
                record.scrap_count += scrap
        elif state.status in (MachineStatus.FAULT, MachineStatus.MAINTENANCE):
            record.downtime_s += self.tick_seconds
            # Conta a falha uma única vez, no tick em que ela começa.
            if state.status is MachineStatus.FAULT and state.ticks_in_state == 0:
                record.fault_count += 1

        record.energy_kwh += reading.energy * (self.tick_seconds / 3600.0)
        db.add(record)


#: Instância global controlada pelo ciclo de vida da aplicação.
simulator = LineSimulator()
