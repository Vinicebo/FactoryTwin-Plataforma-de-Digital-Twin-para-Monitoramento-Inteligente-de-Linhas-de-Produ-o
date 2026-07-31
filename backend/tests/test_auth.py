"""Autenticação e controle de acesso por perfil (Fase 9)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.enums import UserRole


class TestHierarquiaDePerfis:
    def test_admin_satisfaz_todos_os_niveis(self) -> None:
        assert UserRole.ADMIN.satisfies(UserRole.VIEWER)
        assert UserRole.ADMIN.satisfies(UserRole.OPERATOR)
        assert UserRole.ADMIN.satisfies(UserRole.ADMIN)

    def test_viewer_nao_satisfaz_niveis_superiores(self) -> None:
        assert UserRole.VIEWER.satisfies(UserRole.VIEWER)
        assert not UserRole.VIEWER.satisfies(UserRole.OPERATOR)
        assert not UserRole.VIEWER.satisfies(UserRole.ADMIN)


class TestLogin:
    def test_login_valido_retorna_token_e_usuario(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/login/json", json={"username": "admin", "password": "admin123"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["user"]["role"] == "ADMIN"
        assert body["expires_in"] > 0
        # A senha (nem o hash) nunca pode vazar na resposta.
        assert "password" not in body["user"]
        assert "hashed_password" not in body["user"]

    def test_senha_incorreta_retorna_401(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/login/json", json={"username": "admin", "password": "errada"}
        )
        assert response.status_code == 401

    def test_usuario_inexistente_retorna_401(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/login/json", json={"username": "ninguem", "password": "seja-la"}
        )
        assert response.status_code == 401

    def test_fluxo_oauth2_form_funciona(self, client: TestClient) -> None:
        """É o fluxo que o botão Authorize do Swagger usa."""
        response = client.post(
            "/api/v1/auth/login", data={"username": "admin", "password": "admin123"}
        )
        assert response.status_code == 200
        assert "access_token" in response.json()


class TestProtecaoDeRotas:
    def test_sem_token_retorna_401(self, client: TestClient) -> None:
        assert client.get("/api/v1/machines").status_code == 401

    def test_token_invalido_retorna_401(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/machines", headers={"Authorization": "Bearer nao-e-um-jwt"}
        )
        assert response.status_code == 401

    def test_viewer_le_mas_nao_escreve(
        self, client: TestClient, viewer_headers: dict[str, str]
    ) -> None:
        assert client.get("/api/v1/machines", headers=viewer_headers).status_code == 200

        response = client.post(
            "/api/v1/machines",
            headers=viewer_headers,
            json={"code": "XXX-01", "name": "Proibida", "machine_type": "ROBOT"},
        )
        assert response.status_code == 403

    def test_operador_nao_cria_maquina(
        self, client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        """Cadastro de equipamento é atribuição de administrador."""
        response = client.post(
            "/api/v1/machines",
            headers=operator_headers,
            json={"code": "XXX-02", "name": "Proibida", "machine_type": "ROBOT"},
        )
        assert response.status_code == 403

    def test_operador_lista_usuarios_e_barrado(
        self, client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        assert client.get("/api/v1/auth/users", headers=operator_headers).status_code == 403

    def test_me_retorna_usuario_autenticado(
        self, client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        body = client.get("/api/v1/auth/me", headers=operator_headers).json()
        assert body["username"] == "operador"
        assert body["role"] == "OPERATOR"


class TestGestaoDeUsuarios:
    def test_admin_cria_e_remove_usuario(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        payload = {
            "username": "novo.operador",
            "email": "novo@factorytwin.io",
            "full_name": "Novo Operador",
            "password": "senha123",
            "role": "OPERATOR",
        }
        created = client.post("/api/v1/auth/users", headers=admin_headers, json=payload)
        assert created.status_code == 201
        user_id = created.json()["id"]

        duplicated = client.post("/api/v1/auth/users", headers=admin_headers, json=payload)
        assert duplicated.status_code == 409

        # O usuário criado consegue autenticar.
        login = client.post(
            "/api/v1/auth/login/json",
            json={"username": "novo.operador", "password": "senha123"},
        )
        assert login.status_code == 200

        removed = client.delete(f"/api/v1/auth/users/{user_id}", headers=admin_headers)
        assert removed.status_code == 200

    def test_admin_nao_remove_a_propria_conta(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        me = client.get("/api/v1/auth/me", headers=admin_headers).json()
        response = client.delete(f"/api/v1/auth/users/{me['id']}", headers=admin_headers)
        assert response.status_code == 400

    def test_admin_nao_rebaixa_a_si_mesmo(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """Evita o sistema ficar sem nenhum administrador ativo."""
        me = client.get("/api/v1/auth/me", headers=admin_headers).json()
        response = client.patch(
            f"/api/v1/auth/users/{me['id']}", headers=admin_headers, json={"role": "VIEWER"}
        )
        assert response.status_code == 400
