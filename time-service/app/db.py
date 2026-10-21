from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .core.config import settings

SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL


def connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    if url.startswith("postgresql"):
        # недоступная база — ошибка за 2 с, раньше таймаута readiness-пробы (3 с)
        return {"connect_timeout": 2}
    return {}


engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args(SQLALCHEMY_DATABASE_URL))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass
