"""Treino do modelo de detecção de anomalias (Fase 8).

Uso:

    python -m app.ml.train                 # usa as leituras já gravadas no banco
    python -m app.ml.train --synthetic     # gera dados sintéticos (sem histórico)
    python -m app.ml.train --min-samples 500

O modelo é um pipeline `StandardScaler → IsolationForest`, salvo em joblib
junto de metadados (data do treino, nº de amostras, contaminação).
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Machine, SensorReading
from app.models.enums import MachineStatus
from app.services.anomaly import FEATURE_NAMES, extract_features

logger = logging.getLogger(__name__)

#: Amostras mínimas para que o treino seja estatisticamente defensável.
MIN_SAMPLES = 300


def load_from_db(min_samples: int = MIN_SAMPLES) -> pd.DataFrame | None:
    """Monta o dataset a partir das leituras históricas.

    Treinamos apenas com amostras de máquinas em `RUNNING`: o objetivo é
    aprender a *operação normal*, e paradas planejadas distorceriam essa noção.
    """
    with SessionLocal() as db:
        machines = {m.id: m for m in db.scalars(select(Machine)).all()}
        if not machines:
            return None

        stmt = select(SensorReading).where(SensorReading.status == MachineStatus.RUNNING)
        rows: list[list[float]] = []
        for reading in db.scalars(stmt).yield_per(1000):
            machine = machines.get(reading.machine_id)
            if machine is None:
                continue
            rows.append(extract_features(machine, reading))

    if len(rows) < min_samples:
        logger.warning(
            "Apenas %d amostras no banco (mínimo %d). Use --synthetic ou deixe "
            "o simulador rodar mais tempo.",
            len(rows),
            min_samples,
        )
        return None
    return pd.DataFrame(rows, columns=FEATURE_NAMES)


def generate_synthetic(n_samples: int = 4000, seed: int = 42) -> pd.DataFrame:
    """Dataset sintético de operação normal, com ruído gaussiano em torno do nominal.

    As razões são centradas em 1.0 (valor nominal); a eficiência gira em torno
    de 0.88 e a vibração fica bem abaixo do limite de aviso.
    """
    rng = np.random.default_rng(seed)
    data = {
        "temp_ratio": rng.normal(1.0, 0.045, n_samples),
        "speed_ratio": rng.normal(1.0, 0.06, n_samples),
        "efficiency": np.clip(rng.normal(0.88, 0.05, n_samples), 0.0, 1.0),
        "energy_ratio": rng.normal(1.0, 0.08, n_samples),
        "vibration_ratio": np.clip(rng.normal(0.55, 0.12, n_samples), 0.0, None),
        "pressure_ratio": rng.normal(1.0, 0.05, n_samples),
    }
    return pd.DataFrame(data, columns=FEATURE_NAMES)


def train(
    dataset: pd.DataFrame,
    *,
    contamination: float | None = None,
    output_path: Path | None = None,
    source: str = "unknown",
) -> dict[str, Any]:
    contamination = contamination if contamination is not None else settings.ML_CONTAMINATION
    output_path = Path(output_path or settings.ML_MODEL_PATH)

    pipeline = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "forest",
                IsolationForest(
                    n_estimators=200,
                    contamination=contamination,
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    pipeline.fit(dataset[FEATURE_NAMES].to_numpy())

    scores = pipeline.decision_function(dataset[FEATURE_NAMES].to_numpy())
    predictions = pipeline.predict(dataset[FEATURE_NAMES].to_numpy())
    flagged = int((predictions == -1).sum())

    metadata = {
        "trained_at": datetime.now(UTC).isoformat(),
        "n_samples": int(len(dataset)),
        "features": FEATURE_NAMES,
        "contamination": contamination,
        "source": source,
        "score_mean": float(np.mean(scores)),
        "score_std": float(np.std(scores)),
        "flagged_in_training": flagged,
        "flagged_ratio": flagged / len(dataset),
    }

    import joblib

    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": pipeline, "metadata": metadata}, output_path)
    logger.info("Modelo salvo em %s", output_path)
    return metadata


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(description="Treina o detector de anomalias do FactoryTwin")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Treina com dados sintéticos em vez do histórico do banco",
    )
    parser.add_argument("--samples", type=int, default=4000, help="Amostras sintéticas")
    parser.add_argument("--min-samples", type=int, default=MIN_SAMPLES)
    parser.add_argument("--contamination", type=float, default=None)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.synthetic:
        dataset, source = generate_synthetic(args.samples), "synthetic"
    else:
        dataset = load_from_db(args.min_samples)
        source = "database"
        if dataset is None:
            logger.info("Histórico insuficiente — caindo para dados sintéticos.")
            dataset, source = generate_synthetic(args.samples), "synthetic-fallback"

    metadata = train(
        dataset,
        contamination=args.contamination,
        output_path=Path(args.output) if args.output else None,
        source=source,
    )
    print("Treino concluído:")
    for key, value in metadata.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":  # pragma: no cover
    main()
