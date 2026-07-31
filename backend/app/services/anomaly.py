"""Detecção de anomalias com Scikit-learn (Fase 8).

O modelo é um `IsolationForest` treinado sobre **features normalizadas pelos
valores nominais de cada máquina**. Isso é o que permite um único modelo servir
a injetora (195 °C) e a esteira (38 °C): o que entra no modelo não é a
temperatura absoluta, e sim o quanto ela se desvia do nominal daquele
equipamento.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import settings
from app.models import Machine, SensorReading

logger = logging.getLogger(__name__)

#: Ordem das features — precisa bater entre treino e inferência.
FEATURE_NAMES = [
    "temp_ratio",
    "speed_ratio",
    "efficiency",
    "energy_ratio",
    "vibration_ratio",
    "pressure_ratio",
]


def _safe_ratio(value: float, nominal: float) -> float:
    """Razão valor/nominal, tolerante a nominal zero (ex.: pressão da esteira)."""
    if nominal <= 0:
        return 0.0
    return value / nominal


def extract_features(machine: Machine, reading: SensorReading) -> list[float]:
    return [
        _safe_ratio(reading.temperature, machine.temp_nominal),
        _safe_ratio(reading.speed, machine.speed_nominal),
        reading.efficiency / 100.0,
        _safe_ratio(reading.energy, machine.energy_nominal),
        _safe_ratio(reading.vibration, machine.vib_warning),
        _safe_ratio(reading.pressure, machine.pressure_nominal),
    ]


@dataclass
class ScoreResult:
    score: float
    is_anomaly: bool


class AnomalyDetector:
    """Carrega o modelo sob demanda e pontua leituras.

    Se o artefato não existir, o detector fica inativo em vez de quebrar a
    aplicação — a plataforma roda normalmente sem a Fase 8 treinada.
    """

    def __init__(self, model_path: str | Path | None = None) -> None:
        self._model_path = Path(model_path or settings.ML_MODEL_PATH)
        self._pipeline: Any | None = None
        self._metadata: dict[str, Any] = {}
        self._loaded = False
        self._lock = threading.Lock()

    @property
    def is_ready(self) -> bool:
        self._ensure_loaded()
        return self._pipeline is not None

    @property
    def metadata(self) -> dict[str, Any]:
        self._ensure_loaded()
        return dict(self._metadata)

    @property
    def model_path(self) -> Path:
        return self._model_path

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:  # outra thread carregou enquanto esperávamos
                return
            self._loaded = True
            if not self._model_path.exists():
                logger.info(
                    "Modelo de anomalias ausente em %s — detecção desativada "
                    "(rode `python -m app.ml.train`)",
                    self._model_path,
                )
                return
            try:
                import joblib

                bundle = joblib.load(self._model_path)
                self._pipeline = bundle["pipeline"]
                self._metadata = bundle.get("metadata", {})
                logger.info("Modelo de anomalias carregado de %s", self._model_path)
            except Exception:
                logger.exception("Falha ao carregar o modelo de anomalias")
                self._pipeline = None

    def reload(self) -> bool:
        """Força recarregar o artefato — usado após um retreino."""
        with self._lock:
            self._loaded = False
            self._pipeline = None
            self._metadata = {}
        return self.is_ready

    def score(self, machine: Machine, reading: SensorReading) -> ScoreResult | None:
        results = self.score_batch([(machine, reading)])
        return results[0] if results else None

    def score_batch(
        self, pairs: list[tuple[Machine, SensorReading]]
    ) -> list[ScoreResult] | None:
        """Pontua várias leituras de uma vez (uma chamada por tick do simulador)."""
        self._ensure_loaded()
        if self._pipeline is None or not pairs:
            return None

        features = np.array(
            [extract_features(machine, reading) for machine, reading in pairs], dtype=float
        )
        try:
            # `decision_function` < 0 => o IsolationForest considera outlier.
            scores = self._pipeline.decision_function(features)
            predictions = self._pipeline.predict(features)
        except Exception:
            logger.exception("Falha ao pontuar anomalias; detecção será ignorada neste tick")
            return None

        return [
            ScoreResult(score=float(score), is_anomaly=bool(pred == -1))
            for score, pred in zip(scores, predictions, strict=False)
        ]


#: Instância global compartilhada pela API e pelo simulador.
detector = AnomalyDetector()
