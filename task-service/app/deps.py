from .db import SessionLocal
from typing import Generator
from sqlalchemy.orm import Session

def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
