from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Float, func
from sqlalchemy.orm import relationship
from .db import Base

class TimeEntry(Base):
    __tablename__ = "time_entries"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=False)
    minutes = Column(Integer, nullable=False)
    description = Column(String, nullable=True)
    date = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
