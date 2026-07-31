"""Fixtures de teste.

O `DATABASE_URL` é apontado para um SQLite temporário **antes** de qualquer
import de `app.*`: `app.core.config.settings` é cacheado no import, então
trocar a variável depois não teria efeito.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

_TMP_DB = Path(tempfile.gettempdir()) / "factorytwin_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"
os.environ["SIMULATOR_ENABLED"] = "false"
os.environ["ML_SCORING_ENABLED"] = "false"
os.environ["SECRET_KEY"] = "chave-de-teste"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.seed import seed_all  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Machine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database() -> Generator[None, None, None]:
    """Banco limpo por sessão de teste."""
    if _TMP_DB.exists():
        _TMP_DB.unlink()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_all(db)
    yield
    engine.dispose()
    if _TMP_DB.exists():
        _TMP_DB.unlink()


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def _auth_header(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login/json", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin_headers(client: TestClient) -> dict[str, str]:
    return _auth_header(client, "admin", "admin123")


@pytest.fixture(scope="session")
def operator_headers(client: TestClient) -> dict[str, str]:
    return _auth_header(client, "operador", "operador123")


@pytest.fixture(scope="session")
def viewer_headers(client: TestClient) -> dict[str, str]:
    return _auth_header(client, "visitante", "visitante123")


@pytest.fixture(scope="session")
def admin_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login/json", json={"username": "admin", "password": "admin123"}
    )
    return response.json()["access_token"]


@pytest.fixture
def sample_machine(db: Session) -> Machine:
    machine = db.query(Machine).filter(Machine.code == "INJ-01").one()
    return machine
