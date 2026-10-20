import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from . import models, schemas
from .core.security import decode_token, get_password_hash
from .deps import get_db


def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()


def create_user(db: Session, user_in: schemas.UserCreate):
    user = models.User(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=get_password_hash(user_in.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_active_user_by_sub(db: Session, sub) -> models.User | None:
    """Пользователь по claim `sub` токена; None, если sub некорректен,
    пользователя нет или он неактивен.
    """
    if not isinstance(sub, str) or not sub.isdigit():
        return None
    user = db.query(models.User).filter(models.User.id == int(sub)).first()
    if not user or not user.is_active:
        return None
    return user


def get_current_token_user(db: Session = Depends(get_db), authorization: str | None = Header(None)):
    """Get current user from Authorization header (Bearer access token)"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid auth scheme")

    try:
        payload = decode_token(parts[1])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from None
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user = get_active_user_by_sub(db, payload.get("sub"))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user
