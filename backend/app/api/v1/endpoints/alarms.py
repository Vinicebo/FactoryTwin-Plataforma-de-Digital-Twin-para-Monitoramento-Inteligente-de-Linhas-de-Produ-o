"""Consulta e tratamento de alarmes (Fase 7)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbSession, RequireOperator, RequireViewer
from app.crud import alarm_crud, machine_crud
from app.models.enums import AlarmCode, AlarmSeverity, AlarmStatus
from app.schemas.alarm import (
    AlarmAcknowledge,
    AlarmCreate,
    AlarmRead,
    AlarmStats,
    AlarmWithMachine,
)
from app.schemas.common import Page
from app.services.realtime import EventType, build_event, manager

router = APIRouter()


@router.get("", response_model=Page[AlarmWithMachine], summary="Lista alarmes")
def list_alarms(
    db: DbSession,
    _: RequireViewer,
    only_open: bool = Query(default=True, description="Apenas ACTIVE e ACKNOWLEDGED"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[AlarmWithMachine]:
    rows, total = alarm_crud.list_with_machine(
        db, only_open=only_open, limit=limit, offset=offset
    )
    items = [
        AlarmWithMachine(
            **AlarmRead.model_validate(alarm).model_dump(),
            machine_code=code,
            machine_name=name,
        )
        for alarm, code, name in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/stats", response_model=AlarmStats, summary="Contagem de alarmes abertos")
def alarm_stats(db: DbSession, _: RequireViewer) -> AlarmStats:
    return AlarmStats(**alarm_crud.stats(db))


@router.get("/search", response_model=Page[AlarmRead], summary="Busca alarmes com filtros")
def search_alarms(
    db: DbSession,
    _: RequireViewer,
    machine_id: int | None = None,
    alarm_status: AlarmStatus | None = Query(default=None, alias="status"),
    severity: AlarmSeverity | None = None,
    code: AlarmCode | None = None,
    since: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[AlarmRead]:
    alarms, total = alarm_crud.list_filtered(
        db,
        machine_id=machine_id,
        status=alarm_status,
        severity=severity,
        code=code,
        since=since,
        limit=limit,
        offset=offset,
    )
    return Page(
        items=[AlarmRead.model_validate(a) for a in alarms],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{alarm_id}", response_model=AlarmRead, summary="Detalha um alarme")
def get_alarm(db: DbSession, _: RequireViewer, alarm_id: int) -> AlarmRead:
    alarm = alarm_crud.get(db, alarm_id)
    if alarm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alarme não encontrado")
    return AlarmRead.model_validate(alarm)


@router.post(
    "",
    response_model=AlarmRead,
    status_code=status.HTTP_201_CREATED,
    summary="Cria alarme manualmente",
)
async def create_alarm(db: DbSession, _: RequireOperator, payload: AlarmCreate) -> AlarmRead:
    machine = machine_crud.get(db, payload.machine_id)
    if machine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Máquina não encontrada")

    # Respeita a mesma deduplicação do motor automático.
    if alarm_crud.get_open_by_code(db, payload.machine_id, payload.code):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Já existe um alarme aberto de código {payload.code.value} nesta máquina",
        )

    from app.models import Alarm

    alarm = Alarm(**payload.model_dump())
    db.add(alarm)
    db.commit()
    db.refresh(alarm)

    result = AlarmRead.model_validate(alarm)
    await manager.broadcast(
        build_event(
            EventType.ALARM_RAISED,
            {**result.model_dump(), "machine_code": machine.code, "machine_name": machine.name},
        )
    )
    return result


@router.post(
    "/{alarm_id}/acknowledge",
    response_model=AlarmRead,
    summary="Reconhece um alarme (operador)",
)
async def acknowledge_alarm(
    db: DbSession,
    operator: RequireOperator,
    alarm_id: int,
    payload: AlarmAcknowledge | None = None,
) -> AlarmRead:
    alarm = alarm_crud.get(db, alarm_id)
    if alarm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alarme não encontrado")
    if alarm.status is AlarmStatus.RESOLVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Alarme já resolvido")

    alarm = alarm_crud.acknowledge(db, alarm, operator.id)
    result = AlarmRead.model_validate(alarm)
    await manager.broadcast(
        build_event(
            EventType.ALARM_UPDATED,
            {**result.model_dump(), "acknowledged_by": operator.username},
        )
    )
    return result


@router.post("/{alarm_id}/resolve", response_model=AlarmRead, summary="Resolve um alarme")
async def resolve_alarm(db: DbSession, operator: RequireOperator, alarm_id: int) -> AlarmRead:
    """Encerramento manual.

    O motor de alarmes resolve sozinho quando a grandeza normaliza; este
    endpoint existe para os casos em que o operador sanou a causa em campo.
    """
    alarm = alarm_crud.get(db, alarm_id)
    if alarm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alarme não encontrado")

    alarm = alarm_crud.resolve(db, alarm)
    result = AlarmRead.model_validate(alarm)
    await manager.broadcast(
        build_event(EventType.ALARM_RESOLVED, {**result.model_dump(), "by": operator.username})
    )
    return result
