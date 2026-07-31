"""Login, perfil e gestão de usuários (Fase 9)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentUser, DbSession, RequireAdmin
from app.core.config import settings
from app.core.security import create_access_token
from app.crud import user_crud
from app.schemas.common import Message, Page
from app.schemas.user import LoginRequest, Token, UserCreate, UserRead, UserUpdate

router = APIRouter()


def _issue_token(user) -> Token:
    access_token = create_access_token(subject=user.username, role=user.role.value)
    return Token(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserRead.model_validate(user),
    )


@router.post("/login", response_model=Token, summary="Autentica e emite um JWT")
def login(
    db: DbSession,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    """Fluxo OAuth2 *password* — é o que o botão "Authorize" do Swagger usa."""
    user = user_crud.authenticate(db, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _issue_token(user)


@router.post("/login/json", response_model=Token, summary="Login via JSON (usado pelo frontend)")
def login_json(db: DbSession, payload: LoginRequest) -> Token:
    user = user_crud.authenticate(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos",
        )
    return _issue_token(user)


@router.get("/me", response_model=UserRead, summary="Dados do usuário autenticado")
def read_me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


# --- Administração de usuários (somente ADMIN) ---------------------------


@router.get("/users", response_model=Page[UserRead], summary="Lista usuários")
def list_users(
    db: DbSession,
    _: RequireAdmin,
    limit: int = 50,
    offset: int = 0,
) -> Page[UserRead]:
    users, total = user_crud.list(db, limit=limit, offset=offset)
    return Page(
        items=[UserRead.model_validate(u) for u in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Cria usuário",
)
def create_user(db: DbSession, _: RequireAdmin, payload: UserCreate) -> UserRead:
    if user_crud.get_by_username(db, payload.username):
        raise HTTPException(status.HTTP_409_CONFLICT, "Nome de usuário já cadastrado")
    if user_crud.get_by_email(db, str(payload.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "E-mail já cadastrado")
    return UserRead.model_validate(user_crud.create(db, payload))


@router.patch("/users/{user_id}", response_model=UserRead, summary="Atualiza usuário")
def update_user(
    db: DbSession, admin: RequireAdmin, user_id: int, payload: UserUpdate
) -> UserRead:
    user = user_crud.get(db, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado")
    # Um admin não pode rebaixar ou desativar a si mesmo — evita deixar o
    # sistema sem nenhum administrador ativo por acidente.
    if user.id == admin.id and (payload.role is not None or payload.is_active is False):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Não é possível alterar o próprio perfil ou desativar a própria conta",
        )
    return UserRead.model_validate(user_crud.update(db, user, payload))


@router.delete("/users/{user_id}", response_model=Message, summary="Remove usuário")
def delete_user(db: DbSession, admin: RequireAdmin, user_id: int) -> Message:
    user = user_crud.get(db, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Não é possível remover a própria conta")
    user_crud.delete(db, user)
    return Message(detail="Usuário removido")
