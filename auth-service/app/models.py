import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String, func

from .db import Base


class UserRole(enum.Enum):
    user = "user"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.user, nullable=False)
