
from fastapi import HTTPException, Request
from jose import JWTError, jwt

from .core.config import settings

# Эндпоинты, доступные без токена. Сравнение точное: /api/auth/login/../x сюда не попадёт.
PUBLIC_PATHS = frozenset({
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/refresh",
})

ALLOWED_ROLES = frozenset({"user", "admin"})


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def authenticate(request: Request) -> dict | None:
    """
    Проверяет Bearer access-токен для всех путей, кроме PUBLIC_PATHS.
    Возвращает {"id": str, "role": str} или None для публичного пути.
    При любой проблеме с токеном бросает 401.
    """
    if request.url.path in PUBLIC_PATHS:
        return None

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

    # role нет в токенах после /refresh (чинится в auth); по умолчанию минимальные права
    role = payload.get("role", "user")
    if role not in ALLOWED_ROLES:
        raise _unauthorized("Invalid token role")

    return {"id": sub, "role": role}
