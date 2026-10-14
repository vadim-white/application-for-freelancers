from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum

# Pydantic v2: use from_attributes in Config for ORM models

class TaskStatus(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"
    blocked = "blocked"

# Project schemas
class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: Optional[bool] = True

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(ProjectBase):
    name: Optional[str] = None

# owner_id только в ответах: владельца задаёт токен, поле в теле запроса игнорируется
class ProjectRead(ProjectBase):
    id: int
    owner_id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Task schemas
class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    status: Optional[TaskStatus] = TaskStatus.todo
    deadline: Optional[datetime] = None
    project_id: Optional[int] = None
    is_active: Optional[bool] = True

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    deadline: Optional[datetime] = None
    project_id: Optional[int] = None
    is_active: Optional[bool] = None

class TaskRead(TaskBase):
    id: int
    owner_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    project: Optional[ProjectRead] = None

    class Config:
        from_attributes = True
