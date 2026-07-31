"""Camada de acesso a dados."""

from app.crud.alarm import alarm_crud
from app.crud.machine import machine_crud
from app.crud.production import production_crud
from app.crud.reading import reading_crud
from app.crud.user import user_crud

__all__ = ["alarm_crud", "machine_crud", "production_crud", "reading_crud", "user_crud"]
