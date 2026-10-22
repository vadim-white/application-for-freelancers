from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TimeEntryBase(BaseModel):
    task_id: int
    minutes: int = Field(..., gt=0, description="Количество минут > 0")
    description: str | None = None

    @field_validator("minutes")
    @classmethod
    def validate_minutes(cls, v):
        if v is None or v <= 0:
            raise ValueError("minutes must be greater than 0")
        return int(v)


class TimeEntryCreate(TimeEntryBase):
    # user_id не принимается от клиента: берётся из токена (лишнее поле в теле игнорируется)
    pass


class TimeEntryRead(BaseModel):
    id: int
    user_id: int
    task_id: int
    started_at: datetime | None
    stopped_at: datetime | None
    duration_seconds: int | None
    description: str | None = None
    minutes: int | None
    date: datetime
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TimerStart(BaseModel):
    task_id: int
    description: str | None = None


class TimerState(BaseModel):
    entry: TimeEntryRead | None
    server_time: datetime


class TimerStarted(BaseModel):
    entry: TimeEntryRead
    stopped: TimeEntryRead | None
    server_time: datetime


class TimerStopped(BaseModel):
    stopped: TimeEntryRead | None
    server_time: datetime
