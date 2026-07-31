"""Agregador das rotas da v1 da API."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    alarms,
    auth,
    machines,
    ml,
    production,
    readings,
    simulation,
    websocket,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Autenticação"])
api_router.include_router(machines.router, prefix="/machines", tags=["Máquinas"])
api_router.include_router(readings.router, prefix="/readings", tags=["Sensores"])
api_router.include_router(production.router, prefix="/production", tags=["Produção e KPIs"])
api_router.include_router(alarms.router, prefix="/alarms", tags=["Alarmes"])
api_router.include_router(ml.router, prefix="/ml", tags=["IA / Anomalias"])
api_router.include_router(simulation.router, prefix="/simulation", tags=["Simulador"])

# WebSocket fica fora do prefixo versionado do OpenAPI, mas na mesma árvore.
ws_router = APIRouter()
ws_router.include_router(websocket.router, prefix="/ws")
