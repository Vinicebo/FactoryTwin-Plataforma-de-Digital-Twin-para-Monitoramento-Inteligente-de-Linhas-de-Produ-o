"""Controle do simulador (Fase 4) — start/stop e injeção de falhas."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import DbSession, RequireAdmin, RequireOperator, RequireViewer
from app.crud import machine_crud
from app.models.enums import MachineStatus
from app.schemas.common import Message
from app.services.realtime import EventType, build_event, manager
from app.services.simulator import FAULT_TICKS, simulator

router = APIRouter()


class SimulatorState(BaseModel):
    running: bool
    tick_seconds: float
    tick_count: int
    machines_tracked: int
    websocket_clients: int


def _state() -> SimulatorState:
    return SimulatorState(
        running=simulator.is_running,
        tick_seconds=simulator.tick_seconds,
        tick_count=simulator.tick_count,
        machines_tracked=len(simulator._states),  # noqa: SLF001 — leitura de diagnóstico
        websocket_clients=manager.active_count,
    )


@router.get("/state", response_model=SimulatorState, summary="Estado do simulador")
def get_state(_: RequireViewer) -> SimulatorState:
    return _state()


@router.post("/start", response_model=SimulatorState, summary="Inicia o simulador")
async def start(_: RequireAdmin) -> SimulatorState:
    await simulator.start()
    await manager.broadcast(build_event(EventType.SIMULATOR_STATE, {"running": True}))
    return _state()


@router.post("/stop", response_model=SimulatorState, summary="Para o simulador")
async def stop(_: RequireAdmin) -> SimulatorState:
    await simulator.stop()
    await manager.broadcast(build_event(EventType.SIMULATOR_STATE, {"running": False}))
    return _state()


@router.post(
    "/machines/{machine_id}/inject-fault",
    response_model=Message,
    summary="Injeta uma falha na máquina (demonstração)",
)
async def inject_fault(db: DbSession, operator: RequireOperator, machine_id: int) -> Message:
    """Força a máquina para `FAULT` — útil para demonstrar alarmes ao vivo.

    Escreve tanto no banco quanto no estado interno do simulador; caso contrário
    o próximo tick sobrescreveria o comando.
    """
    machine = machine_crud.get(db, machine_id)
    if machine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Máquina não encontrada")

    previous = machine.status
    machine_crud.set_status(db, machine, MachineStatus.FAULT)

    state = simulator._states.get(machine_id)  # noqa: SLF001 — controle da simulação
    if state is not None:
        simulator._enter(state, MachineStatus.FAULT, FAULT_TICKS)  # noqa: SLF001

    await manager.broadcast(
        build_event(
            EventType.MACHINE_STATUS,
            {
                "machine_id": machine.id,
                "machine_code": machine.code,
                "from": previous.value,
                "to": MachineStatus.FAULT.value,
                "by": operator.username,
                "reason": "Falha injetada manualmente",
            },
        )
    )
    return Message(detail=f"Falha injetada em {machine.code}")
