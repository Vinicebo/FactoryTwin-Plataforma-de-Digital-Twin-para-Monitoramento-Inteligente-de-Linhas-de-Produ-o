"""Engine e fábrica de sessões SQLAlchemy."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_connect_args: dict[str, object] = {}
if settings.is_sqlite:
    # O simulador roda numa thread separada do event loop do FastAPI.
    _connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.SQL_ECHO,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

if settings.is_sqlite:

    @event.listens_for(Engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        """Liga a checagem de chave estrangeira no SQLite.

        O SQLite ignora `ON DELETE CASCADE` por padrão. Sem este PRAGMA,
        apagar uma máquina deixaria leituras e alarmes órfãos — e como o
        SQLite reaproveita o rowid da última linha removida, esses registros
        acabariam colados à próxima máquina cadastrada. No PostgreSQL a
        integridade já é aplicada nativamente.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Dependência do FastAPI: entrega uma sessão e garante o fechamento."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Sessão transacional para uso fora do ciclo de request (simulador, CLI)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
