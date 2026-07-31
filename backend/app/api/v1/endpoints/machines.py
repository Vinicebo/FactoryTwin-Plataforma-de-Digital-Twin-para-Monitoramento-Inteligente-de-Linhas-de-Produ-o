"""CRUD de máquinas e leitura do estado ao vivo."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbSession, RequireAdmin, RequireOperator, RequireViewer
from app.crud import machine_crud
from app.models.enums import MachineStatus
from app.schemas.common import Message, Page
from app.schemas.machine import (
    MachineCreate,
    MachineLive,
    MachineRead,
    MachineStatusUpdate,
    MachineUpdate,
)
from app.services.analytics import build_live_machines
from app.services.realtime import EventType, build_event, manager

router = APIRouter()


@router.get("", response_model=Page[MachineRead], summary="Lista máquinas")
def list_machines(
    db: DbSession,
    _: RequireViewer,
    line: str | None = None,
    machine_status: MachineStatus | None = Query(default=None, alias="status"),
    only_active: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[MachineRead]:
    machines, total = machine_crud.list_filtered(
        db, line=line, status=machine_status, only_active=only_active, limit=limit, offset=offset
    )
    return Page(
        items=[MachineRead.model_validate(m) for m in machines],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/live",
    response_model=list[MachineLive],
    summary="Máquinas com a última telemetria e alarmes abertos",
)
def list_live(db: DbSession, _: RequireViewer, line: str | None = None) -> list[MachineLive]:
    """Payload que alimenta o mapa da fábrica no dashboard."""
    return build_live_machines(db, line=line)


@router.get("/{machine_id}", response_model=MachineRead, summary="Detalha uma máquina")
def get_machine(db: DbSession, _: RequireViewer, machine_id: int) -> MachineRead:
    machine = machine_crud.get(db, machine_id)
    if machine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Máquina não encontrada")
    return MachineRead.model_validate(machine)


@router.post(
    "",
    response_model=MachineRead,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra máquina",
)
def create_machine(db: DbSession, _: RequireAdmin, payload: MachineCreate) -> MachineRead:
    if machine_crud.get_by_code(db, payload.code):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Código {payload.code} já cadastrado")
    machine = machine_crud.create(db, payload)
    return MachineRead.model_validate(machine)


@router.patch("/{machine_id}", response_model=MachineRead, summary="Atualiza máquina")
def update_machine(
    db: DbSession, _: RequireAdmin, machine_id: int, payload: MachineUpdate
) -> MachineRead:
    machine = machine_crud.get(db, machine_id)
    if machine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Máquina não encontrada")
    return MachineRead.model_validate(machine_crud.update(db, machine, payload))


@router.delete("/{machine_id}", response_model=Message, summary="Remove máquina")
def delete_machine(db: DbSession, _: RequireAdmin, machine_id: int) -> Message:
    machine = machine_crud.get(db, machine_id)
    if machine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Máquina não encontrada")
    machine_crud.delete(db, machine)
    return Message(detail=f"Máquina {machine.code} removida")


@router.post(
    "/{machine_id}/status",
    response_model=MachineRead,
    summary="Comanda o estado da máquina (operador)",
)
async def set_machine_status(
    db: DbSession, operator: RequireOperator, machine_id: int, payload: MachineStatusUpdate
) -> MachineRead:
    """Intervenção manual do operador.

    O simulador reconcilia o estado interno no tick seguinte, então o comando
    vale como condição inicial — não como trava permanente.
    """
    machine = machine_crud.get(db, machine_id)
    if machine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Máquina não encontrada")

    previous = machine.status
    machine = machine_crud.set_status(db, machine, payload.status)

    await manager.broadcast(
        build_event(
            EventType.MACHINE_STATUS,
            {
                "machine_id": machine.id,
                "machine_code": machine.code,
                "from": previous.value,
                "to": machine.status.value,
                "by": operator.username,
                "reason": payload.reason,
            },
        )
    )
    return MachineRead.model_validate(machine)
