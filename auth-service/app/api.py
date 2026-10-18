from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy.orm import Session

from . import crud, schemas
from .core.security import (
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
    user = crud.get_user_by_email(db, form_data.email)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")
    return {**create_tokens_for_user(user), "token_type": "bearer"}


@router.post("/refresh", response_model=schemas.TokenRefreshResponse)
def refresh_token(data: schemas.TokenRefreshRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_token(data.refresh_token)
    except JWTError:
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
    # get_current_token_user returns a full user model
    return user
