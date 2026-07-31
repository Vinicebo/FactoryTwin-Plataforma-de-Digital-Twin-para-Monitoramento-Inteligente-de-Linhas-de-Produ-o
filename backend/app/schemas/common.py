"""Schemas genéricos reaproveitados pelos endpoints."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base dos schemas de leitura — habilita conversão direta do objeto ORM."""

    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    """Envelope de paginação por offset."""

    items: list[T]
    total: int = Field(..., description="Total de registros que atendem ao filtro")
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class Message(BaseModel):
    detail: str
