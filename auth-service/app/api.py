import math
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .core.config import settings
from .core.security import (
    DUMMY_HASH,
    create_tokens_for_user,
    decode_token,
    verify_password,
)
from .deps import get_db

router = APIRouter()


@router.post("/register", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED)
def register(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = crud.get_user_by_email(db, email=user_in.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = crud.create_user(db, user_in)
    return user


@router.post("/login", response_model=schemas.Token)
def login(form_data: schemas.UserAuth, db: Session = Depends(get_db)):
    # попытка считается до проверки пароля: за окно bcrypt проверяет не больше
    # LOGIN_MAX_ATTEMPTS паролей на email, даже при параллельных запросах через реплики
    now = crud.now()
    attempts, window_start = crud.count_login_attempt(db, form_data.email, now)
    if attempts > settings.LOGIN_MAX_ATTEMPTS:
        retry_after = math.ceil((window_start + crud.login_window() - now).total_seconds())
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts",
            headers={"Retry-After": str(max(1, retry_after))},
        )
    user = crud.get_user_by_email(db, form_data.email)
    if not user:
        verify_password(form_data.password, DUMMY_HASH)
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    crud.clear_login_attempts(db, form_data.email, now)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")
    return {**create_tokens_for_user(user), "token_type": "bearer"}


@router.post("/refresh", response_model=schemas.TokenRefreshResponse)
def refresh_token(data: schemas.TokenRefreshRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_token(data.refresh_token)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from None
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")
    # роль берётся из БД: удалённый, отключённый или сменивший роль пользователь
    # не получит старые права
    user = crud.get_active_user_by_sub(db, payload.get("sub"))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return {"access_token": create_tokens_for_user(user)["access_token"], "token_type": "bearer"}


@router.get("/me", response_model=schemas.UserRead)
def read_me(user=Depends(crud.get_current_token_user)):
    return user


@router.get("/users", response_model=schemas.UserList)
def list_users(
    role: models.UserRole | None = None,
    is_active: bool | None = None,
    q: str | None = Query(None, min_length=1, max_length=100),
    id: list[int] = Query([], max_length=200),
    sort: Literal["created_at", "-created_at", "email", "-email"] = "-created_at",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _admin: models.User = Depends(crud.get_current_admin),
):
    """Только admin (по базе). q — подстрока в email или имени без учёта регистра."""
    items, total = crud.list_users(
        db, role=role, is_active=is_active, q=q, ids=id, sort=sort, limit=limit, offset=offset
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.patch("/users/{user_id}", response_model=schemas.UserRead)
def update_user(
    user_id: int,
    user_in: schemas.UserAdminUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(crud.get_current_admin),
):
    """Только admin (по базе): role и is_active другого пользователя.

    Удаления нет — только отключение.
    """
    return crud.update_user_by_admin(db, admin, user_id, user_in)
