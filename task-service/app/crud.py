from typing import Literal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from . import models, schemas


def _order_by(sort: str, columns: dict, id_column) -> list:
    """sort — поле с «-» или без; NULL в конце в обе стороны, при равенстве id в ту же сторону.

    nulls_last явно: без него SQLite ставит NULL первыми по возрастанию, PostgreSQL — последними.
    """
    descending = sort.startswith("-")
    column = columns[sort.lstrip("-")]
    first = column.desc() if descending else column.asc()
    return [first.nulls_last(), id_column.desc() if descending else id_column.asc()]


# Projects
def create_project(db: Session, project_in: schemas.ProjectCreate, owner_id: int) -> models.Project:
    project = models.Project(
        name=project_in.name,
        description=project_in.description,
        owner_id=owner_id,
        is_active=project_in.is_active if project_in.is_active is not None else True,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_project(db: Session, project_id: int) -> models.Project | None:
    return db.query(models.Project).filter(models.Project.id == project_id).first()


def list_projects(
    db: Session,
    *,
    owner_id: int | None,
    is_active: bool | None,
    sort: str,
    limit: int,
    offset: int,
):
    """(items, total); total считается с теми же фильтрами."""
    project = models.Project
    conditions = []
    if owner_id is not None:
        conditions.append(project.owner_id == owner_id)
    if is_active is not None:
        conditions.append(project.is_active == is_active)
    # lower: иначе заглавные раньше всех строчных (сравнение по кодам символов)
    columns = {"created_at": project.created_at, "name": func.lower(project.name)}
    order = _order_by(sort, columns, project.id)
    total = db.scalar(select(func.count()).select_from(project).where(*conditions))
    items = db.scalars(
        select(project).where(*conditions).order_by(*order).limit(limit).offset(offset)
    )
    return list(items), total


def update_project(
    db: Session, project: models.Project, update_in: schemas.ProjectUpdate
) -> models.Project:
    if update_in.name is not None:
        project.name = update_in.name
    if update_in.description is not None:
        project.description = update_in.description
    if update_in.is_active is not None:
        project.is_active = update_in.is_active
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project: models.Project):
    db.delete(project)
    db.commit()
    return True


# Tasks
def create_task(db: Session, task_in: schemas.TaskCreate, owner_id: int) -> models.Task:
    task = models.Task(
        title=task_in.title,
        description=task_in.description,
        status=task_in.status,
        deadline=task_in.deadline,
        project_id=task_in.project_id,
        owner_id=owner_id,
        is_active=task_in.is_active if task_in.is_active is not None else True,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: int) -> models.Task | None:
    return db.query(models.Task).filter(models.Task.id == task_id).first()


def list_tasks(
    db: Session,
    *,
    owner_id: int | None,
    project_id: int | Literal["none"] | None,
    statuses: list[models.TaskStatus],
    is_active: bool | None,
    sort: str,
    limit: int,
    offset: int,
):
    """(items, total); total считается с теми же фильтрами.

    project_id="none" — задачи без проекта.
    """
    task = models.Task
    conditions = []
    if owner_id is not None:
        conditions.append(task.owner_id == owner_id)
    if project_id == "none":
        conditions.append(task.project_id.is_(None))
    elif project_id is not None:
        conditions.append(task.project_id == project_id)
    if statuses:
        conditions.append(task.status.in_(statuses))
    if is_active is not None:
        conditions.append(task.is_active == is_active)
    columns = {
        "created_at": task.created_at,
        # updated_at пуст до первой правки: новая задача считается изменённой при создании
        "updated_at": func.coalesce(task.updated_at, task.created_at),
        "deadline": task.deadline,
        "title": func.lower(task.title),
        # порядок объявления TaskStatus: SQLite иначе сортирует enum по алфавиту
        "status": case({s: i for i, s in enumerate(models.TaskStatus)}, value=task.status),
    }
    order = _order_by(sort, columns, task.id)
    total = db.scalar(select(func.count()).select_from(task).where(*conditions))
    # проект каждой задачи одним запросом, а не отдельным при сериализации TaskRead
    query = select(task).where(*conditions).options(selectinload(task.project))
    items = db.scalars(query.order_by(*order).limit(limit).offset(offset))
    return list(items), total


def update_task(db: Session, task: models.Task, update_in: schemas.TaskUpdate) -> models.Task:
    if update_in.title is not None:
        task.title = update_in.title
    if update_in.description is not None:
        task.description = update_in.description
    if update_in.status is not None:
        task.status = update_in.status
    if update_in.deadline is not None:
        task.deadline = update_in.deadline
    if update_in.project_id is not None:
        task.project_id = update_in.project_id
    if update_in.is_active is not None:
        task.is_active = update_in.is_active
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task: models.Task):
    db.delete(task)
    db.commit()
    return True
