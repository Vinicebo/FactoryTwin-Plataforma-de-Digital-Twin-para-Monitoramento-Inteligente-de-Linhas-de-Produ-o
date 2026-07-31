"""Dependências compartilhadas: sessão de banco e controle de acesso (Fase 9)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.crud import user_crud
from app.db.session import get_db
from app.models import User
from app.models.enums import UserRole

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login",
    auto_error=False,
)

DbSession = Annotated[Session, Depends(get_db)]

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciais inválidas ou expiradas",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    db: DbSession,
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> User:
    if not token:
        raise CREDENTIALS_ERROR

    payload = decode_access_token(token)
    if payload is None or payload.get("type") != "access":
        raise CREDENTIALS_ERROR

    username = payload.get("sub")
    if not username:
        raise CREDENTIALS_ERROR

    user = user_crud.get_by_username(db, username)
    if user is None or not user.is_active:
        raise CREDENTIALS_ERROR
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(minimum: UserRole):
    """Fábrica de dependência que exige um perfil mínimo.

    A hierarquia é VIEWER < OPERATOR < ADMIN (ver `UserRole.satisfies`), então
    um ADMIN atende a qualquer exigência.
    """

    def _dependency(current_user: CurrentUser) -> User:
        if not current_user.role.satisfies(minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requer perfil {minimum.value} ou superior",
            )
        return current_user

    return _dependency


RequireViewer = Annotated[User, Depends(require_role(UserRole.VIEWER))]
RequireOperator = Annotated[User, Depends(require_role(UserRole.OPERATOR))]
RequireAdmin = Annotated[User, Depends(require_role(UserRole.ADMIN))]
