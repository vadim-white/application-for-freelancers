from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt, JWTError
from .config import settings
from typing import Dict

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Валидация перед проверкой
    if len(plain_password.encode('utf-8')) > 72:
        return False
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    # Трункейт пароль до 72 байт для bcrypt
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password = password_bytes[:72].decode('utf-8', errors='ignore')
    return pwd_context.hash(password)

def create_access_token(data: Dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_refresh_token(data: Dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_token(token: str) -> Dict:
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"require_exp": True},
    )

def create_tokens_for_user(user) -> Dict[str, str]:
    """Access-токен всегда несёт актуальную роль пользователя из БД."""
    return {
        "access_token": create_access_token({"sub": str(user.id), "type": "access", "role": user.role.value}),
        "refresh_token": create_refresh_token({"sub": str(user.id), "type": "refresh"}),
    }
