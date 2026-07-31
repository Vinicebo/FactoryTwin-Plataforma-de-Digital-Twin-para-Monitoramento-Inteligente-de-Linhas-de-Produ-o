"""Canal WebSocket de tempo real (Fase 6).

O navegador não permite enviar cabeçalhos numa conexão WebSocket, então o JWT
viaja como query string (`?token=...`) — mesmo token do Bearer usado no REST.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.security import decode_access_token
from app.crud import alarm_crud, user_crud
from app.db.session import SessionLocal
from app.schemas.alarm import AlarmRead
from app.services.analytics import build_live_machines, compute_line_summary
from app.services.realtime import EventType, build_event, manager

logger = logging.getLogger(__name__)

router = APIRouter()


def _authenticate(token: str | None) -> str | None:
    """Devolve o nome do usuário, ou `None` se o token não for válido."""
    if not token:
        return None
    payload = decode_access_token(token)
    if payload is None or payload.get("type") != "access":
        return None
    username = payload.get("sub")
    if not username:
        return None

    with SessionLocal() as db:
        user = user_crud.get_by_username(db, username)
        if user is None or not user.is_active:
            return None
        return user.username


def _build_snapshot() -> dict:
    """Estado completo enviado logo após a conexão.

    Sem isso o dashboard ficaria em branco até o primeiro tick do simulador.
    """
    with SessionLocal() as db:
        machines = [m.model_dump(mode="json") for m in build_live_machines(db)]
        summary = compute_line_summary(db).model_dump(mode="json")
        rows, _ = alarm_crud.list_with_machine(db, only_open=True, limit=100)
        alarms = [
            {
                **AlarmRead.model_validate(alarm).model_dump(mode="json"),
                "machine_code": code,
                "machine_name": name,
            }
            for alarm, code, name in rows
        ]
    return {"machines": machines, "summary": summary, "alarms": alarms}


@router.websocket("/live")
async def live_feed(websocket: WebSocket, token: str | None = Query(default=None)) -> None:
    username = _authenticate(token)
    if username is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Token inválido")
        return

    await manager.connect(websocket)
    try:
        await manager.send_personal(websocket, build_event(EventType.SNAPSHOT, _build_snapshot()))

        # O cliente não precisa mandar nada; o receive serve para detectar a
        # desconexão e para responder a "ping" com "pong" (keep-alive).
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Erro na conexão WebSocket de %s", username)
    finally:
        await manager.disconnect(websocket)
