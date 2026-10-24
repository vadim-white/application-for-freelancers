from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator


class TimeEntryCreate(BaseModel):
    # user_id не принимается от клиента: берётся из токена (лишнее поле в теле игнорируется)
    task_id: int
    started_at: AwareDatetime
    stopped_at: AwareDatetime
    description: str | None = None


class TimeEntryUpdate(BaseModel):
    # merge-patch: нет поля — не трогать; null допустим только у description (очистить заметку);
    # неизвестное поле (в том числе user_id) — 422, иначе опечатка молча ничего не меняет
    model_config = ConfigDict(extra="forbid")

    task_id: int | None = None
    started_at: AwareDatetime | None = None
    stopped_at: AwareDatetime | None = None
    description: str | None = None

    @model_validator(mode="after")
    def no_null_for_required(self):
        for name in ("task_id", "started_at", "stopped_at"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class TimeEntryRead(BaseModel):
    id: int
    user_id: int
    task_id: int
    started_at: datetime
    stopped_at: datetime | None
    duration_seconds: int | None
    description: str | None = None
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


class TimeEntryList(BaseModel):
    items: list[TimeEntryRead]
    total: int
    limit: int
    offset: int


class UserStatistics(BaseModel):
    user_id: int
    entries_count: int
    tasks_count: int
    total_seconds: int
    avg_seconds_per_task: int
