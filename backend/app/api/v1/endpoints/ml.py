"""Endpoints do modelo de detecção de anomalias (Fase 8)."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DbSession, RequireAdmin, RequireViewer
from app.db.base import utcnow
from app.models import Machine, SensorReading
from app.schemas.sensor import SensorReadingRead
from app.services.anomaly import FEATURE_NAMES, detector

router = APIRouter()


class ModelInfo(BaseModel):
    is_ready: bool
    model_path: str
    features: list[str]
    metadata: dict


class TrainRequest(BaseModel):
    synthetic: bool = False
    samples: int = 4000
    contamination: float | None = None


class TrainResponse(BaseModel):
    detail: str
    metadata: dict


@router.get("/model", response_model=ModelInfo, summary="Status do modelo de anomalias")
def model_info(_: RequireViewer) -> ModelInfo:
    return ModelInfo(
        is_ready=detector.is_ready,
        model_path=str(detector.model_path),
        features=FEATURE_NAMES,
        metadata=detector.metadata,
    )


@router.post("/model/train", response_model=TrainResponse, summary="Retreina o modelo")
def train_model(_: RequireAdmin, payload: TrainRequest) -> TrainResponse:
    """Retreina e recarrega o detector.

    Síncrono de propósito: o dataset da demonstração treina em poucos segundos,
    e o retorno já traz as métricas do treino.
    """
    from app.ml.train import generate_synthetic, load_from_db, train

    if payload.synthetic:
        dataset, source = generate_synthetic(payload.samples), "synthetic"
    else:
        dataset = load_from_db()
        source = "database"
        if dataset is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Histórico insuficiente no banco. Deixe o simulador rodar mais "
                "tempo ou use synthetic=true.",
            )

    metadata = train(dataset, contamination=payload.contamination, source=source)
    detector.reload()
    return TrainResponse(detail="Modelo treinado e recarregado", metadata=metadata)


@router.post("/model/reload", response_model=ModelInfo, summary="Recarrega o artefato do disco")
def reload_model(_: RequireAdmin) -> ModelInfo:
    detector.reload()
    return ModelInfo(
        is_ready=detector.is_ready,
        model_path=str(detector.model_path),
        features=FEATURE_NAMES,
        metadata=detector.metadata,
    )


@router.get(
    "/anomalies",
    response_model=list[SensorReadingRead],
    summary="Leituras marcadas como anômalas",
)
def list_anomalies(
    db: DbSession,
    _: RequireViewer,
    hours: int = Query(default=8, ge=1, le=168),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[SensorReadingRead]:
    since = utcnow() - timedelta(hours=hours)
    stmt = (
        select(SensorReading)
        .where(SensorReading.is_anomaly.is_(True), SensorReading.ts >= since)
        .order_by(SensorReading.ts.desc())
        .limit(limit)
    )
    return [SensorReadingRead.model_validate(r) for r in db.scalars(stmt).all()]


@router.post(
    "/score/{machine_id}",
    summary="Pontua a última leitura de uma máquina sob demanda",
)
def score_latest(db: DbSession, _: RequireViewer, machine_id: int) -> dict:
    machine = db.get(Machine, machine_id)
    if machine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Máquina não encontrada")
    if not detector.is_ready:
        raise HTTPException(status.HTTP_409_CONFLICT, "Modelo de anomalias não treinado")

    reading = db.scalar(
        select(SensorReading)
        .where(SensorReading.machine_id == machine_id)
        .order_by(SensorReading.id.desc())
        .limit(1)
    )
    if reading is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nenhuma leitura para esta máquina")

    result = detector.score(machine, reading)
    if result is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Não foi possível pontuar a leitura")

    return {
        "machine_id": machine_id,
        "machine_code": machine.code,
        "reading_id": reading.id,
        "score": result.score,
        "is_anomaly": result.is_anomaly,
    }
