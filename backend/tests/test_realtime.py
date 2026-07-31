"""Canal WebSocket de tempo real (Fase 6)."""

from __future__ import annotations

from datetime import UTC

from fastapi.testclient import TestClient

from app.services.realtime import EventType, build_event


class TestEnvelopeDeEvento:
    def test_evento_tem_tipo_timestamp_e_payload(self) -> None:
        event = build_event(EventType.TELEMETRY, {"machine_id": 1})
        assert event["type"] == "telemetry"
        assert "ts" in event
        assert event["payload"] == {"machine_id": 1}

    def test_datetimes_e_enums_viram_json(self) -> None:
        from datetime import datetime

        from app.models.enums import MachineStatus

        event = build_event(
            EventType.MACHINE_STATUS,
            {"status": MachineStatus.RUNNING, "at": datetime(2026, 1, 1, tzinfo=UTC)},
        )
        assert event["payload"]["status"] == "RUNNING"
        assert event["payload"]["at"].startswith("2026-01-01")


class TestConexao:
    def test_token_valido_recebe_snapshot(self, client: TestClient, admin_token: str) -> None:
        with client.websocket_connect(f"/ws/live?token={admin_token}") as ws:
            event = ws.receive_json()
            assert event["type"] == EventType.SNAPSHOT.value
            payload = event["payload"]
            # O snapshot precisa bastar para pintar o dashboard inteiro.
            assert len(payload["machines"]) >= 8
            assert "summary" in payload
            assert "alarms" in payload

    def test_ping_responde_pong(self, client: TestClient, admin_token: str) -> None:
        with client.websocket_connect(f"/ws/live?token={admin_token}") as ws:
            ws.receive_json()  # descarta o snapshot
            ws.send_text("ping")
            assert ws.receive_text() == "pong"

    def test_sem_token_a_conexao_e_recusada(self, client: TestClient) -> None:
        from starlette.websockets import WebSocketDisconnect

        try:
            with client.websocket_connect("/ws/live") as ws:
                ws.receive_json()
            raise AssertionError("A conexão sem token deveria ter sido recusada")
        except WebSocketDisconnect as exc:
            assert exc.code == 1008

    def test_token_invalido_e_recusado(self, client: TestClient) -> None:
        from starlette.websockets import WebSocketDisconnect

        try:
            with client.websocket_connect("/ws/live?token=lixo") as ws:
                ws.receive_json()
            raise AssertionError("A conexão com token inválido deveria ter sido recusada")
        except WebSocketDisconnect as exc:
            assert exc.code == 1008
