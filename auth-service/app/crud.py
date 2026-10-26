from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from . import models, schemas
from .core.config import settings
from .core.security import decode_token, get_password_hash
from .deps import get_db


def now() -> datetime:
    return datetime.now(UTC)


def login_window() -> timedelta:
    return timedelta(seconds=settings.LOGIN_WINDOW_SECONDS)


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


def lock_active_admin_ids(db: Session) -> set[int]:
    """id активных admin; строки заблокированы до конца транзакции.

    Порядок блокировки по id один у всех запросов — взаимной блокировки нет.
    В SQLite FOR UPDATE нет, запись там и так одна за раз.
    """
    user = models.User
    query = (
        select(user.id)
        .where(user.role == models.UserRole.admin, user.is_active.is_(True))
        .order_by(user.id)
        .with_for_update()
    )
    return set(db.scalars(query))


def audit_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return value.value


def update_user_by_admin(
    db: Session, actor: models.User, user_id: int, data: schemas.UserAdminUpdate
) -> models.User:
    """Смена роли и отключение одной транзакцией, строка user_audit на каждое изменённое поле."""
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        user = db.get(models.User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    if user_id == actor.id:
        raise HTTPException(status_code=409, detail="Cannot change your own role or status")
    # Хотя бы один активный admin остаётся всегда: автор — активный admin под блокировкой
    # и меняет не себя. Параллельный запрос ждёт блокировку и перечитывает набор:
    # если его автора тем временем понизили или отключили — 403
    if actor.id not in lock_active_admin_ids(db):
        raise HTTPException(status_code=403, detail="Admin role required")
    query = (
        select(models.User)
        .where(models.User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    user = db.scalars(query).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    for field, new in changes.items():
        old = getattr(user, field)
        if old == new:
            continue
        db.add(
            models.UserAudit(
                actor_id=actor.id,
                target_id=user.id,
                field=field,
                old_value=audit_value(old),
                new_value=audit_value(new),
            )
        )
        setattr(user, field, new)
    db.commit()
    db.refresh(user)
    return user


def count_login_attempt(db: Session, email: str, now: datetime) -> tuple[int, datetime]:
    """Засчитать попытку входа: (номер попытки в окне, начало окна).

    Один INSERT … ON CONFLICT: параллельные попытки через разные реплики получают разные
    номера, «прочитать → записать» дал бы IntegrityError на новом email и потерянный счёт.
    Окно истекло — счёт с 1. Коммит сразу: попытка засчитана, что бы ни было дальше.
    """
    table = models.LoginAttempts.__table__
    insert = postgresql.insert if db.get_bind().dialect.name == "postgresql" else sqlite.insert
    stmt = insert(table).values(email=email, attempts=1, window_start=now)
    expired = table.c.window_start <= now - login_window()
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.email],
        set_={
            "attempts": case((expired, 1), else_=table.c.attempts + 1),
            "window_start": case((expired, stmt.excluded.window_start), else_=table.c.window_start),
        },
    ).returning(table.c.attempts, table.c.window_start)
    attempts, window_start = db.execute(stmt).one()
    db.commit()
    return attempts, window_start


def clear_login_attempts(db: Session, email: str, now: datetime) -> None:
    """Удалить счётчик email и заодно строки с истёкшим окном (по индексу window_start)."""
    table = models.LoginAttempts.__table__
    db.execute(
        delete(table).where(
            or_(table.c.email == email, table.c.window_start <= now - login_window())
        )
    )
    db.commit()
