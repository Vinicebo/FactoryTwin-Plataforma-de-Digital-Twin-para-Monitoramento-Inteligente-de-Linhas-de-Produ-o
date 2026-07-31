"""Simulador da linha (Fase 4)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models import Machine, ProductionRecord, SensorReading
from app.models.enums import MachineStatus
from app.services.simulator import AMBIENT_TEMPERATURE, LineSimulator, MachineState


class TestTick:
    def test_um_tick_gera_uma_leitura_por_maquina(self, db: Session) -> None:
        antes = db.scalar(select(func.count()).select_from(SensorReading)) or 0
        maquinas_ativas = 8

        simulador = LineSimulator(tick_seconds=1.0, seed=1)
        outcome = simulador.tick()

        depois = db.scalar(select(func.count()).select_from(SensorReading)) or 0
        assert len(outcome.telemetry) >= maquinas_ativas
        assert depois - antes == len(outcome.telemetry)

    def test_determinismo_com_a_mesma_semente(self, sample_machine: Machine) -> None:
        """Mesma semente + mesmo estado ⇒ mesma telemetria.

        A comparação é feita sobre `_generate_reading` porque `tick()` também
        depende do estado persistido no banco, que muda entre execuções.
        """
        agora = utcnow()

        def gerar() -> tuple[float, ...]:
            simulador = LineSimulator(tick_seconds=1.0, seed=99)
            state = MachineState(
                machine_id=sample_machine.id,
                status=MachineStatus.RUNNING,
                temperature=100.0,
            )
            leitura = simulador._generate_reading(sample_machine, state, agora)
            return (
                leitura.temperature,
                leitura.speed,
                leitura.efficiency,
                leitura.energy,
                leitura.vibration,
                leitura.pressure,
            )

        assert gerar() == gerar()

    def test_sementes_diferentes_geram_ruidos_diferentes(
        self, sample_machine: Machine
    ) -> None:
        agora = utcnow()

        def gerar(seed: int) -> float:
            simulador = LineSimulator(tick_seconds=1.0, seed=seed)
            state = MachineState(
                machine_id=sample_machine.id,
                status=MachineStatus.RUNNING,
                temperature=100.0,
            )
            return simulador._generate_reading(sample_machine, state, agora).speed

        assert gerar(1) != gerar(2)

    def test_telemetria_respeita_limites_fisicos(self) -> None:
        simulador = LineSimulator(tick_seconds=1.0, seed=3)
        for _ in range(40):
            for leitura in simulador.tick().telemetry:
                assert leitura["temperature"] >= 0
                assert leitura["speed"] >= 0
                assert 0 <= leitura["efficiency"] <= 100
                assert leitura["energy"] >= 0
                assert leitura["vibration"] >= 0
                assert leitura["pressure"] >= 0


class TestComportamentoDoProcesso:
    def test_maquina_parada_resfria_e_zera_producao(self) -> None:
        simulador = LineSimulator(tick_seconds=2.0, seed=5)
        simulador.tick()  # popula o estado interno

        for state in simulador._states.values():
            state.status = MachineStatus.OFFLINE
            state.temperature = 200.0

        for _ in range(40):
            outcome = simulador.tick()

        for leitura in outcome.telemetry:
            assert leitura["efficiency"] == 0.0
            # Com 40 ticks de resfriamento a temperatura converge ao ambiente.
            assert leitura["temperature"] < AMBIENT_TEMPERATURE + 5

    def test_maquina_rodando_aquece_ate_o_nominal(self, db: Session) -> None:
        """Modelo térmico isolado: partindo do ambiente, converge ao nominal.

        Exercita `_generate_reading` diretamente para que transições de estado
        (falha, estrangulamento) não interfiram na medição da convergência.
        """
        simulador = LineSimulator(tick_seconds=2.0, seed=11)
        agora = utcnow()

        for maquina in db.scalars(select(Machine)).all():
            state = MachineState(
                machine_id=maquina.id,
                status=MachineStatus.RUNNING,
                temperature=AMBIENT_TEMPERATURE,
            )
            for _ in range(60):
                leitura = simulador._generate_reading(maquina, state, agora)

            assert abs(leitura.temperature - maquina.temp_nominal) < maquina.temp_nominal * 0.15, (
                f"{maquina.code} não convergiu: {leitura.temperature:.1f} °C "
                f"(nominal {maquina.temp_nominal:.1f} °C)"
            )

    def test_aquecimento_e_gradual_e_nao_instantaneo(self, sample_machine: Machine) -> None:
        """Inércia térmica: a temperatura sobe aos poucos, não salta ao nominal."""
        simulador = LineSimulator(tick_seconds=2.0, seed=12)
        agora = utcnow()
        state = MachineState(
            machine_id=sample_machine.id,
            status=MachineStatus.RUNNING,
            temperature=AMBIENT_TEMPERATURE,
        )

        primeira = simulador._generate_reading(sample_machine, state, agora)
        # A injetora opera a ~195 °C; um tick não pode chegar nem perto disso.
        assert primeira.temperature < sample_machine.temp_nominal * 0.5

    def test_manutencao_zera_o_desgaste(self) -> None:
        simulador = LineSimulator(tick_seconds=2.0, seed=13)
        simulador.tick()

        state = next(iter(simulador._states.values()))
        state.wear = 0.9
        simulador._enter(state, MachineStatus.MAINTENANCE, (1, 1))

        for _ in range(4):
            simulador.tick()

        assert state.wear == 0.0

    def test_falha_leva_a_manutencao_e_volta_a_produzir(self) -> None:
        """Ciclo completo FAULT → MAINTENANCE → SETUP → RUNNING."""
        simulador = LineSimulator(tick_seconds=2.0, seed=17)
        simulador.tick()

        state = next(iter(simulador._states.values()))
        simulador._enter(state, MachineStatus.FAULT, (2, 2))

        vistos = {state.status}
        for _ in range(60):
            simulador.tick()
            vistos.add(state.status)

        assert MachineStatus.MAINTENANCE in vistos
        assert MachineStatus.RUNNING in vistos


class TestContabilidadeDeProducao:
    def test_tempo_planejado_acumula_em_todos_os_estados(self, db: Session) -> None:
        simulador = LineSimulator(tick_seconds=2.0, seed=23)
        for _ in range(10):
            simulador.tick()

        registros = list(db.scalars(select(ProductionRecord)).all())
        assert registros
        for registro in registros:
            assert registro.planned_time_s > 0
            # Runtime e downtime são subconjuntos do tempo planejado.
            assert registro.runtime_s + registro.downtime_s <= registro.planned_time_s + 1e-6

    def test_producao_gera_pecas_boas(self, db: Session) -> None:
        simulador = LineSimulator(tick_seconds=2.0, seed=29)
        for _ in range(120):
            simulador.tick()

        total = db.scalar(select(func.sum(ProductionRecord.good_count))) or 0
        assert total > 0

    def test_energia_acumulada_e_positiva(self, db: Session) -> None:
        simulador = LineSimulator(tick_seconds=2.0, seed=31)
        for _ in range(10):
            simulador.tick()

        energia = db.scalar(select(func.sum(ProductionRecord.energy_kwh))) or 0.0
        assert energia > 0
