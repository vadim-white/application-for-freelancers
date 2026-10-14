from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime

class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    external_id: Optional[int] = None

class ProjectRead(ProjectBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True

class TimeEntryBase(BaseModel):
    task_id: int
    minutes: int = Field(..., gt=0, description="Количество минут > 0")
    description: Optional[str] = None

    @validator('minutes')
    def validate_minutes(cls, v):
        if v is None or v <= 0:
            raise ValueError("minutes must be greater than 0")
        return int(v)

class TimeEntryCreate(TimeEntryBase):
    # user_id не принимается от клиента: берётся из токена (лишнее поле в теле игнорируется)
    pass

class TimeEntryRead(TimeEntryBase):
    id: int
    user_id: Optional[int] = None
    date: datetime
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
