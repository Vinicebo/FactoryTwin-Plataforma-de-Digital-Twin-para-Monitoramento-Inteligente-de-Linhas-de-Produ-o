"""Detecção de anomalias (Fase 8)."""

from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.ml.train import generate_synthetic, train
from app.models import Machine, SensorReading
from app.models.enums import MachineStatus
from app.services.anomaly import FEATURE_NAMES, AnomalyDetector, extract_features


def make_reading(machine: Machine, **overrides) -> SensorReading:
    defaults = {
        "machine_id": machine.id,
        "ts": utcnow(),
        "temperature": machine.temp_nominal,
        "speed": machine.speed_nominal,
        "efficiency": 88.0,
        "energy": machine.energy_nominal,
        "vibration": machine.vib_warning * 0.55,
        "pressure": machine.pressure_nominal,
        "status": MachineStatus.RUNNING,
    }
    return SensorReading(**{**defaults, **overrides})


class TestFeatures:
    def test_features_normalizadas_pelo_nominal(self, sample_machine: Machine) -> None:
        features = extract_features(sample_machine, make_reading(sample_machine))
        assert len(features) == len(FEATURE_NAMES)
        # Operando no nominal, as razões ficam em 1.0.
        assert features[0] == 1.0  # temp_ratio
        assert features[1] == 1.0  # speed_ratio
        assert features[2] == 0.88  # efficiency

    def test_nominal_zero_nao_divide_por_zero(self, db: Session) -> None:
        """A esteira tem pressão nominal 0 — não pode estourar."""
        esteira = db.query(Machine).filter(Machine.code == "CNV-01").one()
        esteira.pressure_nominal = 0.0
        features = extract_features(esteira, make_reading(esteira, pressure=1.0))
        assert features[-1] == 0.0

    def test_maquinas_diferentes_geram_features_comparaveis(self, db: Session) -> None:
        """É o que permite um único modelo servir a injetora e a esteira."""
        injetora = db.query(Machine).filter(Machine.code == "INJ-01").one()
        esteira = db.query(Machine).filter(Machine.code == "CNV-01").one()

        f_inj = extract_features(injetora, make_reading(injetora))
        f_cnv = extract_features(esteira, make_reading(esteira))
        assert f_inj[0] == f_cnv[0] == 1.0


class TestTreinoEInferencia:
    def test_modelo_treinado_marca_outlier_e_ignora_normal(
        self, tmp_path, sample_machine: Machine
    ) -> None:
        modelo = tmp_path / "modelo.joblib"
        dataset = generate_synthetic(n_samples=2000, seed=1)
        metadata = train(dataset, contamination=0.03, output_path=modelo, source="test")

        assert modelo.exists()
        assert metadata["n_samples"] == 2000
        assert metadata["features"] == FEATURE_NAMES

        detector = AnomalyDetector(model_path=modelo)
        assert detector.is_ready

        normal = detector.score(sample_machine, make_reading(sample_machine))
        assert normal is not None
        assert normal.is_anomaly is False

        # Temperatura 60% acima do nominal com vibração alta: fora da distribuição.
        anomala = detector.score(
            sample_machine,
            make_reading(
                sample_machine,
                temperature=sample_machine.temp_nominal * 1.6,
                vibration=sample_machine.vib_warning * 3.0,
                efficiency=25.0,
            ),
        )
        assert anomala is not None
        assert anomala.is_anomaly is True
        # Score negativo = outlier no IsolationForest.
        assert anomala.score < normal.score

    def test_contaminacao_bate_com_o_esperado(self, tmp_path) -> None:
        dataset = generate_synthetic(n_samples=3000, seed=2)
        metadata = train(
            dataset, contamination=0.05, output_path=tmp_path / "m.joblib", source="test"
        )
        assert 0.03 < metadata["flagged_ratio"] < 0.07

    def test_pontuacao_em_lote(self, tmp_path, sample_machine: Machine) -> None:
        modelo = tmp_path / "modelo.joblib"
        train(generate_synthetic(1500, seed=3), output_path=modelo, source="test")
        detector = AnomalyDetector(model_path=modelo)

        pares = [(sample_machine, make_reading(sample_machine)) for _ in range(5)]
        resultados = detector.score_batch(pares)
        assert resultados is not None and len(resultados) == 5

    def test_dataset_sintetico_e_reprodutivel(self) -> None:
        a = generate_synthetic(500, seed=42)
        b = generate_synthetic(500, seed=42)
        assert np.allclose(a.to_numpy(), b.to_numpy())


class TestDegradacaoElegante:
    def test_sem_artefato_o_detector_fica_inativo(self, tmp_path, sample_machine: Machine) -> None:
        """A plataforma precisa rodar mesmo sem a Fase 8 treinada."""
        detector = AnomalyDetector(model_path=tmp_path / "nao-existe.joblib")
        assert detector.is_ready is False
        assert detector.score(sample_machine, make_reading(sample_machine)) is None
        assert detector.score_batch([]) is None
