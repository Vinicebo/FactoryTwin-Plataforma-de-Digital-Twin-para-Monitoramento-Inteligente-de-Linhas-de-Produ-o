"""CRUD de produção e KPIs derivados."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbSession, RequireAdmin, RequireOperator, RequireViewer
from app.crud import machine_crud, production_crud
from app.schemas.common import Message, Page
from app.schemas.production import (
    LineSummary,
    OEEMetrics,
    ProductionRecordCreate,
    ProductionRecordRead,
    ProductionRecordUpdate,
)
from app.services.analytics import compute_line_summary, compute_oee, machine_oee_ranking

router = APIRouter()


@router.get("", response_model=Page[ProductionRecordRead], summary="Lista registros de produção")
def list_production(
    db: DbSession,
    _: RequireViewer,
    machine_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[ProductionRecordRead]:
    records, total = production_crud.list_filtered(
        db, machine_id=machine_id, since=since, until=until, limit=limit, offset=offset
    )
    return Page(
        items=[ProductionRecordRead.model_validate(r) for r in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/summary", response_model=LineSummary, summary="Resumo consolidado da linha")
def line_summary(
    db: DbSession,
    _: RequireViewer,
    line: str = "LINE-01",
    hours: int = Query(default=8, ge=1, le=168),
) -> LineSummary:
    return compute_line_summary(db, line=line, hours=hours)


@router.get("/oee", response_model=OEEMetrics, summary="OEE da linha ou de uma máquina")
def oee(
    db: DbSession,
    _: RequireViewer,
    machine_id: int | None = None,
    hours: int = Query(default=8, ge=1, le=168),
) -> OEEMetrics:
    if machine_id is not None and machine_crud.get(db, machine_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Máquina não encontrada")
    return compute_oee(db, machine_id=machine_id, hours=hours)


@router.get(
    "/oee/ranking",
    response_model=list[OEEMetrics],
    summary="OEE por máquina, do pior para o melhor (gargalo primeiro)",
)
def oee_ranking(
    db: DbSession, _: RequireViewer, hours: int = Query(default=8, ge=1, le=168)
) -> list[OEEMetrics]:
    return machine_oee_ranking(db, hours=hours)


@router.get("/{record_id}", response_model=ProductionRecordRead, summary="Detalha um registro")
def get_record(db: DbSession, _: RequireViewer, record_id: int) -> ProductionRecordRead:
    record = production_crud.get(db, record_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registro não encontrado")
    return ProductionRecordRead.model_validate(record)


@router.post(
    "",
    response_model=ProductionRecordRead,
    status_code=status.HTTP_201_CREATED,
    summary="Cria registro de produção",
)
def create_record(
    db: DbSession, _: RequireOperator, payload: ProductionRecordCreate
) -> ProductionRecordRead:
    if machine_crud.get(db, payload.machine_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Máquina não encontrada")
    return ProductionRecordRead.model_validate(production_crud.create(db, payload))


@router.patch(
    "/{record_id}", response_model=ProductionRecordRead, summary="Atualiza registro de produção"
)
def update_record(
    db: DbSession, _: RequireOperator, record_id: int, payload: ProductionRecordUpdate
) -> ProductionRecordRead:
    record = production_crud.get(db, record_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registro não encontrado")
    return ProductionRecordRead.model_validate(production_crud.update(db, record, payload))


@router.delete("/{record_id}", response_model=Message, summary="Remove registro de produção")
def delete_record(db: DbSession, _: RequireAdmin, record_id: int) -> Message:
    record = production_crud.get(db, record_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registro não encontrado")
    production_crud.delete(db, record)
    return Message(detail="Registro removido")
