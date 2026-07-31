"""Consulta e ingestão de leituras de sensores."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbSession, RequireOperator, RequireViewer
from app.crud import machine_crud, reading_crud
from app.crud.reading import METRIC_COLUMNS
from app.db.base import utcnow
from app.models import SensorReading
from app.schemas.common import Page
from app.schemas.sensor import MetricSeries, SensorReadingCreate, SensorReadingRead, SeriesPoint
from app.services import alarm_engine
from app.services.anomaly import detector

router = APIRouter()


@router.get(
    "/machines/{machine_id}",
    response_model=Page[SensorReadingRead],
    summary="Histórico de leituras de uma máquina",
)
def list_readings(
    db: DbSession,
    _: RequireViewer,
    machine_id: int,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> Page[SensorReadingRead]:
    if machine_crud.get(db, machine_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Máquina não encontrada")

    readings, total = reading_crud.list_for_machine(
        db, machine_id, since=since, until=until, limit=limit, offset=offset
    )
    return Page(
        items=[SensorReadingRead.model_validate(r) for r in readings],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/machines/{machine_id}/latest",
    response_model=SensorReadingRead,
    summary="Última leitura de uma máquina",
)
def latest_reading(db: DbSession, _: RequireViewer, machine_id: int) -> SensorReadingRead:
    reading = reading_crud.get_latest(db, machine_id)
    if reading is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nenhuma leitura para esta máquina")
    return SensorReadingRead.model_validate(reading)


@router.get(
    "/machines/{machine_id}/series",
    response_model=MetricSeries,
    summary="Série temporal de uma métrica (para os gráficos)",
)
def metric_series(
    db: DbSession,
    _: RequireViewer,
    machine_id: int,
    metric: str = Query(default="temperature", description=f"Uma de: {', '.join(METRIC_COLUMNS)}"),
    minutes: int = Query(default=60, ge=1, le=1440),
    max_points: int = Query(default=240, ge=10, le=1000),
) -> MetricSeries:
    if machine_crud.get(db, machine_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Máquina não encontrada")
    try:
        rows, unit = reading_crud.series(
            db, machine_id, metric, minutes=minutes, max_points=max_points
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    return MetricSeries(
        machine_id=machine_id,
        metric=metric,
        unit=unit,
        points=[SeriesPoint(ts=ts, value=value) for ts, value in rows],
    )


@router.post(
    "",
    response_model=SensorReadingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Ingere uma leitura externa",
)
def ingest_reading(
    db: DbSession, _: RequireOperator, payload: SensorReadingCreate
) -> SensorReadingRead:
    """Porta de entrada para telemetria de fora do simulador (CLP, gateway IoT).

    A leitura passa pelo mesmo caminho do simulador: pontuação de anomalia e
    avaliação do motor de alarmes.
    """
    machine = machine_crud.get(db, payload.machine_id)
    if machine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Máquina não encontrada")

    reading = SensorReading(
        machine_id=payload.machine_id,
        ts=payload.ts or utcnow(),
        temperature=payload.temperature,
        speed=payload.speed,
        efficiency=payload.efficiency,
        energy=payload.energy,
        vibration=payload.vibration,
        pressure=payload.pressure,
        status=payload.status,
    )

    if (score := detector.score(machine, reading)) is not None:
        reading.anomaly_score = score.score
        reading.is_anomaly = score.is_anomaly

    db.add(reading)
    db.flush()
    alarm_engine.process(db, machine, reading)
    db.commit()
    db.refresh(reading)
    return SensorReadingRead.model_validate(reading)
