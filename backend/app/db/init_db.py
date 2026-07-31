"""Criação do schema e carga inicial.

Para o escopo do projeto usamos `create_all` + seed idempotente no boot. Numa
operação real, migrações Alembic assumiriam o lugar do `create_all`.
"""

from __future__ import annotations

import logging

# Import com efeito colateral: registra todas as tabelas no metadata.
import app.models  # noqa: F401
from app.db.base import Base
from app.db.seed import seed_all
from app.db.session import SessionLocal, engine

logger = logging.getLogger(__name__)


def create_schema() -> None:
    Base.metadata.create_all(bind=engine)
    logger.info("Schema verificado/criado (%d tabelas)", len(Base.metadata.tables))


def init_db(with_seed: bool = True) -> None:
    create_schema()
    if not with_seed:
        return
    db = SessionLocal()
    try:
        seed_all(db)
    finally:
        db.close()


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    init_db()
    print("Banco inicializado.")
