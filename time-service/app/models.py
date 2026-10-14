from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Float, func
from sqlalchemy.orm import relationship
from .db import Base

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    external_id = Column(Integer, unique=True, nullable=True)


class TimeEntry(Base):
    __tablename__ = "time_entries"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=False)
    # user_id теперь nullable — если мы не смогли достать user из токена,
    # позволим NULL в БД (и в ответе это будет `null`)
    user_id = Column(Integer, nullable=True)
    minutes = Column(Integer, nullable=False)
    description = Column(String, nullable=True)
    date = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
