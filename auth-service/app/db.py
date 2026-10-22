from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .core.config import settings

SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL


def connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    if url.startswith("postgresql"):
        # недоступная база — ошибка за 2 с, раньше таймаута readiness-пробы (3 с);
        # на открытом соединении: запрос дольше 5 с отменяет база, обрыв сети ловит keepalive
        return {
            "connect_timeout": 2,
            "options": "-c statement_timeout=5000",
            "keepalives": 1,
            "keepalives_idle": 5,
            "keepalives_interval": 2,
            "keepalives_count": 3,
            "tcp_user_timeout": 5000,
        }
    return {}


def make_engine(url: str):
    # pre-ping: соединение, закрытое базой (перезапуск), заменяется до запроса, а не даёт 500
    return create_engine(url, connect_args=connect_args(url), pool_pre_ping=True)


engine = make_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass
