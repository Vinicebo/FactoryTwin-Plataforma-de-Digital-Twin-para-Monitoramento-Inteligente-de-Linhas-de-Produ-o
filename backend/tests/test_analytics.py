"""Cálculo de KPIs e OEE."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models import Machine, ProductionRecord
from app.services.analytics import compute_line_summary, compute_oee


class TestFormulaDeOEE:
    """Valida a fórmula sobre o modelo, sem depender do simulador."""

    def test_registro_perfeito_da_oee_100(self) -> None:
        registro = ProductionRecord(
            machine_id=1,
            good_count=600,
            scrap_count=0,
            planned_time_s=3600,
            runtime_s=3600,
            downtime_s=0,
        )
        assert registro.availability == 1.0
        assert registro.quality == 1.0
        # 600 peças × 6 s = 3600 s de trabalho útil em 3600 s produzindo.
        assert registro.performance(ideal_cycle_time_s=6.0) == 1.0
        assert registro.oee(ideal_cycle_time_s=6.0) == 1.0

    def test_decomposicao_dos_tres_fatores(self) -> None:
        registro = ProductionRecord(
            machine_id=1,
            good_count=270,
            scrap_count=30,
            planned_time_s=3600,
            runtime_s=1800,  # metade do tempo parada
            downtime_s=1800,
        )
        assert registro.availability == pytest.approx(0.5)
        assert registro.quality == pytest.approx(0.9)
        assert registro.performance(ideal_cycle_time_s=6.0) == pytest.approx(1.0)
        assert registro.oee(ideal_cycle_time_s=6.0) == pytest.approx(0.45)

    def test_divisao_por_zero_nao_quebra(self) -> None:
        vazio = ProductionRecord(machine_id=1)
        assert vazio.availability == 0.0
        assert vazio.quality == 0.0
        assert vazio.performance(6.0) == 0.0
        assert vazio.oee(6.0) == 0.0

    def test_fatores_sao_limitados_a_um(self) -> None:
        """Contagem inconsistente não pode produzir OEE acima de 100%."""
        registro = ProductionRecord(
            machine_id=1,
            good_count=10_000,
            scrap_count=0,
            planned_time_s=100,
            runtime_s=200,  # runtime > planejado (dado inconsistente)
        )
        assert registro.availability == 1.0
        assert registro.performance(6.0) == 1.0
        assert registro.oee(6.0) <= 1.0


class TestAgregacaoNoBanco:
    def test_oee_da_linha_fica_no_intervalo_valido(self, db: Session) -> None:
        metrics = compute_oee(db, machine_id=None, hours=8)
        assert 0.0 <= metrics.oee <= 1.0
        assert 0.0 <= metrics.availability <= 1.0
        assert 0.0 <= metrics.performance <= 1.0
        assert 0.0 <= metrics.quality <= 1.0
        assert metrics.total_count == metrics.good_count + metrics.scrap_count

    def test_oee_por_maquina_traz_o_codigo(self, db: Session) -> None:
        maquina = db.query(Machine).filter(Machine.code == "INJ-01").one()
        metrics = compute_oee(db, machine_id=maquina.id, hours=8)
        assert metrics.machine_code == "INJ-01"

    def test_resumo_da_linha_soma_os_estados(self, db: Session) -> None:
        resumo = compute_line_summary(db, line="LINE-01", hours=8)
        assert resumo.machines_total >= 8
        soma_parcial = (
            resumo.machines_running + resumo.machines_faulted + resumo.machines_idle
        )
        assert soma_parcial <= resumo.machines_total
        assert resumo.active_alarms >= 0
        assert 0.0 <= resumo.scrap_rate <= 1.0

    def test_mtbf_e_none_sem_falhas_na_janela(self, db: Session) -> None:
        metrics = compute_oee(db, machine_id=None, hours=1)
        if metrics.fault_count == 0:
            assert metrics.mtbf_minutes is None
            assert metrics.mttr_minutes is None
