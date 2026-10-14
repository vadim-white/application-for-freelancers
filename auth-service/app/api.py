from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from . import schemas, crud
from .deps import get_db
from .core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from datetime import timedelta
from jose import JWTError

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
    access_token = create_access_token({"sub": str(user.id), "type": "access", "role": user.role.value})
    refresh_token = create_refresh_token({"sub": str(user.id), "type": "refresh"})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

@router.post("/refresh", response_model=schemas.TokenRefreshResponse)
def refresh_token(data: schemas.TokenRefreshRequest):
    token = data.refresh_token
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")
    user_id = payload.get("sub")
    new_access = create_access_token({"sub": user_id, "type": "access"})
    return {"access_token": new_access, "token_type": "bearer"}

@router.get("/me", response_model=schemas.UserRead)
def read_me(user = Depends(crud.get_current_token_user)):
    # get_current_token_user returns a full user model
    return user
