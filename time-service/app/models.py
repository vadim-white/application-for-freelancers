from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from .db import Base

RUNNING = "stopped_at IS NULL"


class UTCDateTime(TypeDecorator):
    """Время с поясом; из базы всегда aware UTC.

    SQLite хранит и отдаёт время без пояса: пишем в UTC, прочитанное считаем UTC.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime: time must be timezone-aware")
        return value.astimezone(UTC)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class TimeEntry(Base):
    __tablename__ = "time_entries"
    __table_args__ = (
        # один идущий таймер на пользователя: гарантия базы, а не проверка в коде (реплики, гонки)
        Index(
            "ux_time_entries_running",
            "user_id",
            unique=True,
            sqlite_where=text(RUNNING),
            postgresql_where=text(RUNNING),
        ),
        Index("ix_time_entries_user_id_started_at", "user_id", "started_at"),
        CheckConstraint(
            "stopped_at IS NULL OR stopped_at >= started_at",
            name="ck_time_entries_stopped_after_started",
        ),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="ck_time_entries_duration_not_negative",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    task_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[int]
    description: Mapped[str | None]
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    stopped_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    duration_seconds: Mapped[int | None]
    created_at: Mapped[datetime | None] = mapped_column(UTCDateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, onupdate=func.now())
