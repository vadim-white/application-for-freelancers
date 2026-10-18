from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from jose import JWTError, jwt

from .config import settings

ALLOWED_ROLES = frozenset({"user", "admin"})


@dataclass(frozen=True)
class CurrentUser:
    id: int
    role: str
    # исходный заголовок Authorization, чтобы пробрасывать его в другие сервисы
    authorization: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(request: Request) -> CurrentUser:
    """
    Проверяет Bearer access-токен так же, как gateway: подпись, обязательный exp,
    type == "access", sub — число, role из ALLOWED_ROLES (нет role — user).
    Заголовкам X-User-* не доверяем: сервис может быть доступен в обход gateway.
    """
    auth_header = request.headers.get("authorization")
    if not auth_header:
        raise _unauthorized("Missing authorization header")

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise _unauthorized("Invalid authorization header format")

    try:
        payload = jwt.decode(
            parts[1],
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require_exp": True},
        )
    except JWTError:
        raise _unauthorized("Invalid or expired token") from None

    # refresh-токен подписан тем же ключом, как access его принимать нельзя
    if payload.get("type") != "access":
        raise _unauthorized("Invalid token type")

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub.isdigit():
        raise _unauthorized("Invalid token subject")

    role = payload.get("role", "user")
    if role not in ALLOWED_ROLES:
        raise _unauthorized("Invalid token role")

    return CurrentUser(id=int(sub), role=role, authorization=auth_header)


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin role required")
    return user
