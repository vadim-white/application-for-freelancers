from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class TimeEntry(Base):
    __tablename__ = "time_entries"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    task_id: Mapped[int]
    user_id: Mapped[int]
    minutes: Mapped[int]
    description: Mapped[str | None]
    date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_active: Mapped[bool | None] = mapped_column(default=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )
