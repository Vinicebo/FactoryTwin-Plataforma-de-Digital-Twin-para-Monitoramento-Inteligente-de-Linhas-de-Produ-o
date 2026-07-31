"""Barramento de eventos em tempo real via WebSocket (Fase 6).

Um único `ConnectionManager` global mantém as conexões abertas. Tanto o
simulador quanto os endpoints REST publicam eventos por aqui, e o dashboard
recebe tudo por um canal só — sem polling.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.db.base import utcnow

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    SNAPSHOT = "snapshot"
    TELEMETRY = "telemetry"
    ALARM_RAISED = "alarm_raised"
    ALARM_UPDATED = "alarm_updated"
    ALARM_RESOLVED = "alarm_resolved"
    MACHINE_STATUS = "machine_status"
    LINE_SUMMARY = "line_summary"
    SIMULATOR_STATE = "simulator_state"


def _json_safe(value: Any) -> Any:
    """Converte datetimes e enums para tipos serializáveis em JSON."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(v) for v in value]
    return value


def build_event(event_type: EventType, payload: Any) -> dict[str, Any]:
    return {
        "type": event_type.value,
        "ts": utcnow().isoformat(),
        "payload": _json_safe(payload),
    }


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.info("WebSocket conectado (%d ativos)", self.active_count)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)
        logger.info("WebSocket desconectado (%d ativos)", self.active_count)

    async def send_personal(self, websocket: WebSocket, event: dict[str, Any]) -> None:
        if websocket.client_state is WebSocketState.CONNECTED:
            await websocket.send_json(event)

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Envia a todos os clientes; descarta os que falharem.

        Um cliente lento ou morto não pode derrubar o loop do simulador, então
        toda exceção de envio vira apenas remoção da conexão.
        """
        async with self._lock:
            targets = list(self._connections)

        if not targets:
            return

        results = await asyncio.gather(
            *(self._safe_send(ws, event) for ws in targets), return_exceptions=True
        )
        dead = [ws for ws, ok in zip(targets, results, strict=False) if ok is not True]
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)
            logger.debug("Removidas %d conexões inativas", len(dead))

    @staticmethod
    async def _safe_send(websocket: WebSocket, event: dict[str, Any]) -> bool:
        try:
            if websocket.client_state is not WebSocketState.CONNECTED:
                return False
            await websocket.send_json(event)
            return True
        except Exception:
            return False


#: Instância global usada por endpoints e pelo simulador.
manager = ConnectionManager()
