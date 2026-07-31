"""Configuração central da aplicação, carregada de variáveis de ambiente."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", BACKEND_DIR.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Aplicação -------------------------------------------------------
    PROJECT_NAME: str = "FactoryTwin"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # --- Banco de dados --------------------------------------------------
    # Em produção usamos PostgreSQL; em dev/teste, SQLite é o padrão para que o
    # projeto rode sem dependência externa.
    DATABASE_URL: str = f"sqlite:///{(BACKEND_DIR / 'factorytwin.db').as_posix()}"
    SQL_ECHO: bool = False

    # --- Segurança / JWT -------------------------------------------------
    SECRET_KEY: str = "troque-esta-chave-em-producao-factorytwin"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8

    # Credenciais do administrador criado no seed inicial.
    FIRST_ADMIN_USERNAME: str = "admin"
    FIRST_ADMIN_PASSWORD: str = "admin123"
    # `.local` é um TLD de uso especial e seria recusado pelo validador de
    # e-mail do Pydantic, então o domínio de demonstração usa um TLD normal.
    FIRST_ADMIN_EMAIL: str = "admin@factorytwin.io"

    # --- CORS ------------------------------------------------------------
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
        ]
    )

    # --- Simulador -------------------------------------------------------
    SIMULATOR_ENABLED: bool = True
    SIMULATOR_TICK_SECONDS: float = 2.0
    #: Probabilidade, por tick e por máquina, de uma falha não planejada.
    SIMULATOR_FAULT_PROBABILITY: float = 0.004
    #: Quantos ticks manter em memória antes de persistir em lote.
    SIMULATOR_PERSIST_EVERY: int = 1

    # --- Machine Learning ------------------------------------------------
    ML_MODEL_PATH: str = str(BACKEND_DIR / "app" / "ml" / "artifacts" / "anomaly_model.joblib")
    ML_CONTAMINATION: float = 0.03
    ML_SCORING_ENABLED: bool = True

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Aceita `CORS_ORIGINS` como lista JSON ou string separada por vírgula."""
        if isinstance(value, str) and not value.strip().startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
