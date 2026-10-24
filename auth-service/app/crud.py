import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy import func, or_, select
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


def get_current_admin(user: models.User = Depends(get_current_token_user)) -> models.User:
    """Admin по базе, а не по токену: снятый admin теряет права сразу, а не через 15 минут."""
    if user.role != models.UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def list_users(
    db: Session,
    *,
    role: models.UserRole | None,
    is_active: bool | None,
    q: str | None,
    ids: list[int],
    sort: str,
    limit: int,
    offset: int,
):
    """(items, total); total считается с теми же фильтрами."""
    user = models.User
    conditions = []
    if role is not None:
        conditions.append(user.role == role)
    if is_active is not None:
        conditions.append(user.is_active == is_active)
    if q is not None:
        # %, _ и \ — обычные символы
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        conditions.append(
            or_(user.email.ilike(pattern, escape="\\"), user.full_name.ilike(pattern, escape="\\"))
        )
    if ids:
        conditions.append(user.id.in_(ids))
    descending = sort.startswith("-")
    column = user.created_at if sort.lstrip("-") == "created_at" else user.email
    order = [
        column.desc() if descending else column.asc(),
        user.id.desc() if descending else user.id.asc(),
    ]
    total = db.scalar(select(func.count()).select_from(user).where(*conditions))
    items = db.scalars(select(user).where(*conditions).order_by(*order).limit(limit).offset(offset))
    return list(items), total
