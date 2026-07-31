"""Motor de regras de alarme (Fase 7)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.crud import alarm_crud
from app.db.base import utcnow
from app.models import Machine, SensorReading
from app.models.enums import AlarmCode, AlarmSeverity, AlarmStatus, MachineStatus
from app.services import alarm_engine


def make_reading(machine: Machine, **overrides) -> SensorReading:
    """Leitura nominal da máquina — os testes sobrescrevem só o que interessa."""
    defaults = {
        "machine_id": machine.id,
        "ts": utcnow(),
        "temperature": machine.temp_nominal,
        "speed": machine.speed_nominal,
        "efficiency": 90.0,
        "energy": machine.energy_nominal,
        "vibration": machine.vib_warning * 0.5,
        "pressure": machine.pressure_nominal,
        "status": MachineStatus.RUNNING,
    }
    return SensorReading(**{**defaults, **overrides})


class TestAvaliacaoDeRegras:
    def test_leitura_nominal_nao_gera_violacao(self, sample_machine: Machine) -> None:
        assert alarm_engine.evaluate_reading(sample_machine, make_reading(sample_machine)) == []

    def test_temperatura_acima_do_aviso_gera_warning(self, sample_machine: Machine) -> None:
        reading = make_reading(sample_machine, temperature=sample_machine.temp_warning + 1)
        violations = alarm_engine.evaluate_reading(sample_machine, reading)
        assert len(violations) == 1
        assert violations[0].code is AlarmCode.HIGH_TEMPERATURE
        assert violations[0].severity is AlarmSeverity.WARNING

    def test_temperatura_acima_do_critico_gera_critical(self, sample_machine: Machine) -> None:
        reading = make_reading(sample_machine, temperature=sample_machine.temp_critical + 1)
        violations = alarm_engine.evaluate_reading(sample_machine, reading)
        assert violations[0].severity is AlarmSeverity.CRITICAL
        assert violations[0].threshold == sample_machine.temp_critical

    def test_temperatura_gera_um_unico_alarme_por_leitura(self, sample_machine: Machine) -> None:
        """CRITICAL não pode coexistir com WARNING do mesmo código."""
        reading = make_reading(sample_machine, temperature=sample_machine.temp_critical + 50)
        codes = [v.code for v in alarm_engine.evaluate_reading(sample_machine, reading)]
        assert codes.count(AlarmCode.HIGH_TEMPERATURE) == 1

    def test_eficiencia_baixa_so_conta_com_a_maquina_rodando(
        self, sample_machine: Machine
    ) -> None:
        parada = make_reading(sample_machine, efficiency=0.0, status=MachineStatus.IDLE)
        codes = [v.code for v in alarm_engine.evaluate_reading(sample_machine, parada)]
        assert AlarmCode.LOW_EFFICIENCY not in codes

        rodando = make_reading(sample_machine, efficiency=sample_machine.eff_critical - 5)
        codes = [v.code for v in alarm_engine.evaluate_reading(sample_machine, rodando)]
        assert AlarmCode.LOW_EFFICIENCY in codes

    def test_velocidade_acima_e_abaixo_dos_limites(self, sample_machine: Machine) -> None:
        acima = make_reading(sample_machine, speed=sample_machine.speed_max + 10)
        assert AlarmCode.OVERSPEED in [
            v.code for v in alarm_engine.evaluate_reading(sample_machine, acima)
        ]

        abaixo = make_reading(sample_machine, speed=sample_machine.speed_min - 10)
        assert AlarmCode.UNDERSPEED in [
            v.code for v in alarm_engine.evaluate_reading(sample_machine, abaixo)
        ]

    def test_vibracao_critica(self, sample_machine: Machine) -> None:
        reading = make_reading(sample_machine, vibration=sample_machine.vib_critical + 1)
        violation = next(
            v
            for v in alarm_engine.evaluate_reading(sample_machine, reading)
            if v.code is AlarmCode.HIGH_VIBRATION
        )
        assert violation.severity is AlarmSeverity.CRITICAL

    def test_estado_de_falha_gera_alarme_critico(self, sample_machine: Machine) -> None:
        reading = make_reading(sample_machine, status=MachineStatus.FAULT)
        codes = [v.code for v in alarm_engine.evaluate_reading(sample_machine, reading)]
        assert AlarmCode.MACHINE_FAULT in codes

    def test_anomalia_do_modelo_gera_alarme(self, sample_machine: Machine) -> None:
        reading = make_reading(sample_machine)
        reading.is_anomaly = True
        reading.anomaly_score = -0.42
        codes = [v.code for v in alarm_engine.evaluate_reading(sample_machine, reading)]
        assert AlarmCode.ANOMALY_DETECTED in codes


class TestCicloDeVida:
    @pytest.fixture
    def machine(self, db: Session) -> Machine:
        """Máquina isolada, para os alarmes de um teste não vazarem para outro."""
        machine = Machine(
            code="TST-ENG",
            name="Máquina de Teste do Motor",
            machine_type="ROBOT",
            line="LINE-TEST",
            temp_nominal=50.0,
            temp_warning=80.0,
            temp_critical=100.0,
            speed_nominal=100.0,
            speed_min=60.0,
            speed_max=140.0,
            eff_warning=75.0,
            eff_critical=60.0,
            vib_warning=4.0,
            vib_critical=7.0,
            pressure_nominal=5.0,
            pressure_max=8.0,
            energy_nominal=10.0,
        )
        db.add(machine)
        db.commit()
        db.refresh(machine)
        yield machine
        # Remoção via ORM para o cascade levar junto alarmes e leituras.
        db.delete(machine)
        db.commit()

    def test_abre_alarme_novo(self, db: Session, machine: Machine) -> None:
        reading = make_reading(machine, temperature=85.0)
        result = alarm_engine.process(db, machine, reading)
        db.commit()

        assert len(result.raised) == 1
        assert result.raised[0].severity is AlarmSeverity.WARNING

    def test_condicao_persistente_nao_duplica_alarme(
        self, db: Session, machine: Machine
    ) -> None:
        for _ in range(3):
            alarm_engine.process(db, machine, make_reading(machine, temperature=85.0))
            db.commit()

        abertos, _ = alarm_crud.list_filtered(db, machine_id=machine.id, only_open=True)
        temperatura = [a for a in abertos if a.code is AlarmCode.HIGH_TEMPERATURE]
        assert len(temperatura) == 1

    def test_escalonamento_promove_alarme_existente(
        self, db: Session, machine: Machine
    ) -> None:
        alarm_engine.process(db, machine, make_reading(machine, temperature=85.0))
        db.commit()

        result = alarm_engine.process(db, machine, make_reading(machine, temperature=105.0))
        db.commit()

        assert len(result.raised) == 0
        assert len(result.escalated) == 1
        assert result.escalated[0].severity is AlarmSeverity.CRITICAL

    def test_escalonamento_reabre_alarme_reconhecido(
        self, db: Session, machine: Machine
    ) -> None:
        """Um WARNING já tratado que vira CRITICAL precisa de nova atenção."""
        alarm_engine.process(db, machine, make_reading(machine, temperature=85.0))
        db.commit()
        alarme = alarm_crud.get_open_by_code(db, machine.id, AlarmCode.HIGH_TEMPERATURE)
        alarm_crud.acknowledge(db, alarme, None)
        assert alarme.status is AlarmStatus.ACKNOWLEDGED

        alarm_engine.process(db, machine, make_reading(machine, temperature=105.0))
        db.commit()
        db.refresh(alarme)
        assert alarme.status is AlarmStatus.ACTIVE
        assert alarme.acknowledged_at is None

    def test_histerese_impede_resolucao_prematura(
        self, db: Session, machine: Machine
    ) -> None:
        alarm_engine.process(db, machine, make_reading(machine, temperature=85.0))
        db.commit()

        # 79 °C está abaixo do gatilho (80) mas dentro da banda morta de 5%.
        result = alarm_engine.process(db, machine, make_reading(machine, temperature=79.0))
        db.commit()
        assert result.resolved == []

        # 70 °C já está fora da banda morta.
        result = alarm_engine.process(db, machine, make_reading(machine, temperature=70.0))
        db.commit()
        assert len(result.resolved) == 1
        assert result.resolved[0].status is AlarmStatus.RESOLVED
        assert result.resolved[0].resolved_at is not None
