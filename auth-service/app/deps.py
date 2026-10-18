from collections.abc import Generator

from .crud import get_db


def get_db_dep() -> Generator:
    yield from get_db()
