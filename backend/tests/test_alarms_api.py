"""Endpoints de alarmes e ingestão de leituras (Fases 3 e 7 na borda HTTP)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _machine_id(client: TestClient, headers: dict[str, str], code: str = "OVN-01") -> int:
    body = client.get("/api/v1/machines?limit=50", headers=headers).json()
    return next(m["id"] for m in body["items"] if m["code"] == code)


class TestIngestaoDispararAlarme:
    def test_leitura_extrema_abre_alarme_critico(
        self, client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        machine_id = _machine_id(client, operator_headers, "OVN-01")

        response = client.post(
            "/api/v1/readings",
            headers=operator_headers,
            json={
                "machine_id": machine_id,
                "temperature": 400.0,
                "speed": 8.0,
                "efficiency": 90.0,
                "energy": 80.0,
                "vibration": 0.5,
                "pressure": 1.0,
                "status": "RUNNING",
            },
        )
        assert response.status_code == 201

        alarmes = client.get(
            f"/api/v1/alarms/search?machine_id={machine_id}", headers=operator_headers
        ).json()
        codigos = [a["code"] for a in alarmes["items"]]
        assert "HIGH_TEMPERATURE" in codigos

    def test_ingestao_em_maquina_inexistente_da_404(
        self, client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = client.post(
            "/api/v1/readings",
            headers=operator_headers,
            json={
                "machine_id": 999999,
                "temperature": 50.0,
                "speed": 10.0,
                "efficiency": 90.0,
                "energy": 5.0,
                "vibration": 0.5,
                "pressure": 1.0,
            },
        )
        assert response.status_code == 404

    def test_eficiencia_fora_da_faixa_e_rejeitada(
        self, client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        machine_id = _machine_id(client, operator_headers)
        response = client.post(
            "/api/v1/readings",
            headers=operator_headers,
            json={
                "machine_id": machine_id,
                "temperature": 50.0,
                "speed": 10.0,
                "efficiency": 150.0,
                "energy": 5.0,
                "vibration": 0.5,
                "pressure": 1.0,
            },
        )
        assert response.status_code == 422


class TestTratamentoDeAlarmes:
    def test_reconhecer_e_resolver(
        self, client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        machine_id = _machine_id(client, operator_headers, "PNT-01")
        criado = client.post(
            "/api/v1/alarms",
            headers=operator_headers,
            json={
                "machine_id": machine_id,
                "code": "MACHINE_FAULT",
                "severity": "CRITICAL",
                "message": "Alarme manual de teste",
            },
        )
        assert criado.status_code == 201
        alarm_id = criado.json()["id"]

        # Deduplicação vale também para criação manual.
        duplicado = client.post(
            "/api/v1/alarms",
            headers=operator_headers,
            json={
                "machine_id": machine_id,
                "code": "MACHINE_FAULT",
                "severity": "CRITICAL",
                "message": "Duplicado",
            },
        )
        assert duplicado.status_code == 409

        ack = client.post(f"/api/v1/alarms/{alarm_id}/acknowledge", headers=operator_headers)
        assert ack.status_code == 200
        assert ack.json()["status"] == "ACKNOWLEDGED"
        assert ack.json()["acknowledged_at"] is not None
        assert ack.json()["acknowledged_by_id"] is not None

        resolve = client.post(f"/api/v1/alarms/{alarm_id}/resolve", headers=operator_headers)
        assert resolve.status_code == 200
        assert resolve.json()["status"] == "RESOLVED"
        assert resolve.json()["resolved_at"] is not None

        # Reconhecer um alarme já resolvido não faz sentido.
        assert (
            client.post(
                f"/api/v1/alarms/{alarm_id}/acknowledge", headers=operator_headers
            ).status_code
            == 409
        )

    def test_visitante_nao_reconhece_alarme(
        self, client: TestClient, viewer_headers: dict[str, str]
    ) -> None:
        alarmes = client.get("/api/v1/alarms?only_open=false", headers=viewer_headers).json()
        if not alarmes["items"]:
            return
        alarm_id = alarmes["items"][0]["id"]
        response = client.post(f"/api/v1/alarms/{alarm_id}/acknowledge", headers=viewer_headers)
        assert response.status_code == 403

    def test_alarme_inexistente_da_404(
        self, client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        assert (
            client.get("/api/v1/alarms/999999", headers=operator_headers).status_code == 404
        )


class TestConsultas:
    def test_listagem_traz_dados_da_maquina(
        self, client: TestClient, viewer_headers: dict[str, str]
    ) -> None:
        body = client.get("/api/v1/alarms?only_open=false", headers=viewer_headers).json()
        if body["items"]:
            assert "machine_code" in body["items"][0]
            assert "machine_name" in body["items"][0]

    def test_estatisticas_agregam_por_severidade(
        self, client: TestClient, viewer_headers: dict[str, str]
    ) -> None:
        body = client.get("/api/v1/alarms/stats", headers=viewer_headers).json()
        assert body["total_active"] == sum(body["by_severity"].values())

    def test_serie_temporal_de_metrica(
        self, client: TestClient, viewer_headers: dict[str, str]
    ) -> None:
        machine_id = _machine_id(client, viewer_headers, "OVN-01")
        body = client.get(
            f"/api/v1/readings/machines/{machine_id}/series?metric=temperature&minutes=60",
            headers=viewer_headers,
        ).json()
        assert body["metric"] == "temperature"
        assert body["unit"] == "°C"
        assert isinstance(body["points"], list)

    def test_metrica_desconhecida_e_rejeitada(
        self, client: TestClient, viewer_headers: dict[str, str]
    ) -> None:
        machine_id = _machine_id(client, viewer_headers)
        response = client.get(
            f"/api/v1/readings/machines/{machine_id}/series?metric=inexistente",
            headers=viewer_headers,
        )
        assert response.status_code == 422
