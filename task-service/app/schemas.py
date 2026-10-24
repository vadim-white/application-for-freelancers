from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .models import TaskStatus


# Project schemas
class ProjectBase(BaseModel):
    name: str
    description: str | None = None
    is_active: bool | None = True


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(ProjectBase):
    name: str | None = None


# owner_id только в ответах: владельца задаёт токен, поле в теле запроса игнорируется
class ProjectRead(ProjectBase):
    id: int
    owner_id: int
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# Конверт списка: total — число подходящих под фильтры, не размер страницы
class ProjectList(BaseModel):
    items: list[ProjectRead]
    total: int
    limit: int
    offset: int


# Task schemas
class TaskBase(BaseModel):
    title: str
    description: str | None = None
    status: TaskStatus | None = TaskStatus.todo
    deadline: datetime | None = None
    project_id: int | None = None
    is_active: bool | None = True


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    deadline: datetime | None = None
    project_id: int | None = None
    is_active: bool | None = None


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskRead(TaskBase):
    id: int
    owner_id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    project: ProjectRead | None = None

    model_config = ConfigDict(from_attributes=True)


class TaskList(BaseModel):
    items: list[TaskRead]
    total: int
    limit: int
    offset: int
