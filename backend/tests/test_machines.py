"""CRUD de máquinas e endpoints de estado ao vivo (Fase 3)."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestListagem:
    def test_lista_as_oito_maquinas_da_linha(
        self, client: TestClient, viewer_headers: dict[str, str]
    ) -> None:
        body = client.get("/api/v1/machines", headers=viewer_headers).json()
        assert body["total"] >= 8
        codes = [m["code"] for m in body["items"]]
        assert "INJ-01" in codes and "PAL-01" in codes

    def test_ordenacao_segue_o_fluxo_produtivo(
        self, client: TestClient, viewer_headers: dict[str, str]
    ) -> None:
        body = client.get(
            "/api/v1/machines?line=LINE-01&limit=50", headers=viewer_headers
        ).json()
        sequences = [m["sequence"] for m in body["items"]]
        assert sequences == sorted(sequences)

    def test_filtro_por_linha(self, client: TestClient, viewer_headers: dict[str, str]) -> None:
        body = client.get("/api/v1/machines?line=INEXISTENTE", headers=viewer_headers).json()
        assert body["total"] == 0

    def test_paginacao(self, client: TestClient, viewer_headers: dict[str, str]) -> None:
        page = client.get("/api/v1/machines?limit=3&offset=0", headers=viewer_headers).json()
        assert len(page["items"]) == 3
        assert page["limit"] == 3

    def test_endpoint_live_traz_alarmes_e_telemetria(
        self, client: TestClient, viewer_headers: dict[str, str]
    ) -> None:
        body = client.get("/api/v1/machines/live", headers=viewer_headers).json()
        assert len(body) >= 8
        primeira = body[0]
        # Campos que o mapa da fábrica consome.
        for field in ("pos_x", "pos_y", "status", "active_alarms", "code"):
            assert field in primeira

    def test_maquina_inexistente_retorna_404(
        self, client: TestClient, viewer_headers: dict[str, str]
    ) -> None:
        assert client.get("/api/v1/machines/999999", headers=viewer_headers).status_code == 404


class TestCriacaoEEdicao:
    def test_ciclo_completo_de_cadastro(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        payload = {
            "code": "TST-CRUD",
            "name": "Máquina de Teste",
            "machine_type": "ROBOT",
            "line": "LINE-TEST",
            "sequence": 1,
            "pos_x": 10.0,
            "pos_y": 20.0,
            "ideal_cycle_time_s": 5.0,
        }
        created = client.post("/api/v1/machines", headers=admin_headers, json=payload)
        assert created.status_code == 201
        machine_id = created.json()["id"]

        conflict = client.post("/api/v1/machines", headers=admin_headers, json=payload)
        assert conflict.status_code == 409

        updated = client.patch(
            f"/api/v1/machines/{machine_id}",
            headers=admin_headers,
            json={"name": "Nome Alterado", "ideal_cycle_time_s": 7.5},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Nome Alterado"
        assert updated.json()["ideal_cycle_time_s"] == 7.5
        # PATCH parcial não pode zerar campos não enviados.
        assert updated.json()["pos_x"] == 10.0

        deleted = client.delete(f"/api/v1/machines/{machine_id}", headers=admin_headers)
        assert deleted.status_code == 200
        assert client.get(f"/api/v1/machines/{machine_id}", headers=admin_headers).status_code == 404

    def test_codigo_invalido_e_rejeitado(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        response = client.post(
            "/api/v1/machines",
            headers=admin_headers,
            json={"code": "minusculo!", "name": "Inválida", "machine_type": "ROBOT"},
        )
        assert response.status_code == 422

    def test_limites_invertidos_sao_rejeitados(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """temp_warning acima de temp_critical tornaria o alarme incoerente."""
        response = client.post(
            "/api/v1/machines",
            headers=admin_headers,
            json={
                "code": "TST-BAD",
                "name": "Limites Invertidos",
                "machine_type": "OVEN",
                "temp_warning": 200.0,
                "temp_critical": 100.0,
            },
        )
        assert response.status_code == 422


class TestComandoDeEstado:
    def test_operador_altera_estado(
        self, client: TestClient, operator_headers: dict[str, str], viewer_headers: dict[str, str]
    ) -> None:
        machines = client.get("/api/v1/machines", headers=viewer_headers).json()["items"]
        machine_id = machines[0]["id"]

        response = client.post(
            f"/api/v1/machines/{machine_id}/status",
            headers=operator_headers,
            json={"status": "MAINTENANCE", "reason": "Manutenção preventiva"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "MAINTENANCE"

    def test_visitante_nao_altera_estado(
        self, client: TestClient, viewer_headers: dict[str, str]
    ) -> None:
        machines = client.get("/api/v1/machines", headers=viewer_headers).json()["items"]
        response = client.post(
            f"/api/v1/machines/{machines[0]['id']}/status",
            headers=viewer_headers,
            json={"status": "OFFLINE"},
        )
        assert response.status_code == 403
