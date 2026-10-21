from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

from .config import settings

password_hash = PasswordHash((BcryptHasher(),))

# вход с неизвестным email тоже проверяет пароль, чтобы по времени ответа не было видно,
# зарегистрирован ли email
DUMMY_HASH = password_hash.hash("dummy-password")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # bcrypt берёт не больше 72 байт, а bcrypt 5 на длинном пароле бросает ValueError
    if len(plain_password.encode("utf-8")) > 72:
        return False
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"require": ["exp"]},
    )


def create_tokens_for_user(user) -> dict[str, str]:
    """Access-токен всегда несёт актуальную роль пользователя из БД."""
    return {
        "access_token": create_access_token(
            {"sub": str(user.id), "type": "access", "role": user.role.value}
        ),
        "refresh_token": create_refresh_token({"sub": str(user.id), "type": "refresh"}),
    }
