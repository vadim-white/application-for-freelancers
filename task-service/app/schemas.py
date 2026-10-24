from datetime import datetime
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints, model_validator

from .models import TaskStatus

# Название на вводе: пробелы по краям обрезаются, затем 1–255 символов (колонка VARCHAR(255):
# длиннее на PostgreSQL — 500). Только в схемах ввода: ответы наследуют …Base и отдают
# уже сохранённые названия как есть
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]

# merge-patch (PATCH): нет поля — не трогать, null — очистить (где поле может быть пустым);
# неизвестное поле — 422, иначе опечатка или owner_id молча ничего не меняют
PATCH_CONFIG = ConfigDict(extra="forbid")


def _no_null(model: BaseModel, *names: str) -> BaseModel:
    """null у обязательного поля — 422: модель его пропускает, видно только по model_fields_set."""
    for name in model.model_fields_set.intersection(names):
        if getattr(model, name) is None:
            raise ValueError(f"{name} cannot be null")
    return model


# Project schemas
class ProjectBase(BaseModel):
    name: str
    description: str | None = None
    is_active: bool | None = True


class ProjectCreate(ProjectBase):
    name: Title


# Без значений по умолчанию: ProjectUpdate наследовал is_active=True, и PUT без него снимал архив
class ProjectPatch(BaseModel):
    model_config = PATCH_CONFIG

    name: Title | None = None
    description: str | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def no_null(self):
        return _no_null(self, "name", "is_active")


# owner_id только в ответах: владельца задаёт токен, поле в теле запроса игнорируется
class ProjectRead(ProjectBase):
    id: int
    owner_id: int
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TaskPreview(BaseModel):
    id: int
    title: str
    status: TaskStatus

    model_config = ConfigDict(from_attributes=True)


# Только для списка: во вложенном в TaskRead ProjectRead этих полей нет.
# Считаются активные задачи проекта; превью — первые по created_at, id
class ProjectListItem(ProjectRead):
    tasks_count: int
    tasks_preview: list[TaskPreview]


# Конверт списка: total — число подходящих под фильтры, не размер страницы
class ProjectList(BaseModel):
    items: list[ProjectListItem]
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


# deadline только с часовым поясом: без него PostgreSQL считает время UTC, SQLite хранит как есть
class TaskCreate(TaskBase):
    title: Title
    deadline: AwareDatetime | None = None


# null у project_id — вынос из проекта, владелец задачи прежний
class TaskPatch(BaseModel):
    model_config = PATCH_CONFIG

    title: Title | None = None
    description: str | None = None
    status: TaskStatus | None = None
    deadline: AwareDatetime | None = None
    project_id: int | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def no_null(self):
        return _no_null(self, "title", "status", "is_active")


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
