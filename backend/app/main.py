"""Ponto de entrada da aplicação FastAPI."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router, ws_router
from app.core.config import settings
from app.db.init_db import init_db
from app.services.anomaly import detector
from app.services.realtime import manager
from app.services.simulator import simulator

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DESCRIPTION = """
Plataforma de **Digital Twin** para monitoramento inteligente de linhas de produção.

* **Máquinas** — cadastro, limites de processo e estado ao vivo
* **Sensores** — série temporal de temperatura, velocidade, eficiência, energia, vibração e pressão
* **Produção** — contagem de peças, refugo e OEE decomposto (Disponibilidade × Performance × Qualidade)
* **Alarmes** — motor de regras com deduplicação, escalonamento e histerese
* **IA** — detecção de anomalias com IsolationForest
* **Tempo real** — todos os eventos publicados em `WS /ws/live?token=...`

Autentique-se em `POST /api/v1/auth/login` (usuário `admin`, senha `admin123` no ambiente padrão).
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando %s v%s (%s)", settings.PROJECT_NAME, __version__, settings.ENVIRONMENT)
    init_db()

    if detector.is_ready:
        logger.info("Detector de anomalias pronto: %s", detector.metadata.get("trained_at"))
    else:
        logger.info("Detector de anomalias inativo — rode `python -m app.ml.train --synthetic`")

    if settings.SIMULATOR_ENABLED:
        await simulator.start()

    yield

    await simulator.stop()
    logger.info("Aplicação encerrada")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=DESCRIPTION,
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
app.include_router(ws_router)


@app.get("/", tags=["Sistema"], summary="Identificação do serviço")
def root() -> dict:
    return {
        "name": settings.PROJECT_NAME,
        "version": __version__,
        "docs": "/docs",
        "websocket": "/ws/live?token=<JWT>",
    }


@app.get("/health", tags=["Sistema"], summary="Health check")
def health() -> dict:
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
        "simulator_running": simulator.is_running,
        "simulator_ticks": simulator.tick_count,
        "websocket_clients": manager.active_count,
        "anomaly_model_ready": detector.is_ready,
    }
