from .crud import get_db
from typing import Generator
from sqlalchemy.orm import Session

def get_db_dep() -> Generator:
    yield from get_db()
