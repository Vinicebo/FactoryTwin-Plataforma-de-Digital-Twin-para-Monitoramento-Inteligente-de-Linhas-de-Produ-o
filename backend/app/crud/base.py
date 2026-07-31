"""CRUD genérico — evita repetir get/list/create/update/delete por modelo."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)
CreateSchemaT = TypeVar("CreateSchemaT", bound=BaseModel)
UpdateSchemaT = TypeVar("UpdateSchemaT", bound=BaseModel)


class CRUDBase(Generic[ModelT, CreateSchemaT, UpdateSchemaT]):
    def __init__(self, model: type[ModelT]) -> None:
        self.model = model

    def get(self, db: Session, obj_id: int) -> ModelT | None:
        return db.get(self.model, obj_id)

    def list(self, db: Session, *, limit: int = 100, offset: int = 0) -> list[ModelT]:
        stmt = select(self.model).limit(limit).offset(offset)
        return list(db.scalars(stmt).all())

    def count(self, db: Session) -> int:
        return db.scalar(select(func.count()).select_from(self.model)) or 0

    def create(self, db: Session, payload: CreateSchemaT, **extra: Any) -> ModelT:
        obj = self.model(**payload.model_dump(exclude_unset=False), **extra)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def update(self, db: Session, obj: ModelT, payload: UpdateSchemaT) -> ModelT:
        # `exclude_unset` garante que campos omitidos no PATCH não sejam
        # sobrescritos com `None`.
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(obj, field, value)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def delete(self, db: Session, obj: ModelT) -> None:
        db.delete(obj)
        db.commit()
