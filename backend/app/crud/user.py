"""Operações de banco para usuários."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas.user import UserCreate, UserUpdate


class CRUDUser:
    def get(self, db: Session, user_id: int) -> User | None:
        return db.get(User, user_id)

    def get_by_username(self, db: Session, username: str) -> User | None:
        return db.scalar(select(User).where(User.username == username))

    def get_by_email(self, db: Session, email: str) -> User | None:
        return db.scalar(select(User).where(User.email == email))

    def list(self, db: Session, *, limit: int = 100, offset: int = 0) -> tuple[list[User], int]:
        stmt = select(User).order_by(User.id).limit(limit).offset(offset)
        total = db.scalar(select(func.count()).select_from(User)) or 0
        return list(db.scalars(stmt).all()), total

    def create(self, db: Session, payload: UserCreate) -> User:
        user = User(
            username=payload.username,
            email=str(payload.email),
            full_name=payload.full_name,
            role=payload.role,
            hashed_password=hash_password(payload.password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def update(self, db: Session, user: User, payload: UserUpdate) -> User:
        data = payload.model_dump(exclude_unset=True)
        # A senha nunca é persistida em claro: troca-se o campo pelo hash.
        if (password := data.pop("password", None)) is not None:
            user.hashed_password = hash_password(password)
        if (email := data.pop("email", None)) is not None:
            user.email = str(email)
        for field, value in data.items():
            setattr(user, field, value)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def delete(self, db: Session, user: User) -> None:
        db.delete(user)
        db.commit()

    def authenticate(self, db: Session, username: str, password: str) -> User | None:
        user = self.get_by_username(db, username)
        if user is None or not user.is_active:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user


user_crud = CRUDUser()
