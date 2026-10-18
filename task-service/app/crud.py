from sqlalchemy.orm import Session

from . import models, schemas


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
    db: Session, skip: int = 0, limit: int = 100, owner_id: int | None = None
) -> list[models.Project]:
    q = db.query(models.Project)
    if owner_id is not None:
        q = q.filter(models.Project.owner_id == owner_id)
    return q.offset(skip).limit(limit).all()


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
    skip: int = 0,
    limit: int = 100,
    project_id: int | None = None,
    status: models.TaskStatus | None = None,
    owner_id: int | None = None,
) -> list[models.Task]:
    q = db.query(models.Task)
    if owner_id is not None:
        q = q.filter(models.Task.owner_id == owner_id)
    if project_id is not None:
        q = q.filter(models.Task.project_id == project_id)
    if status is not None:
        q = q.filter(models.Task.status == status)
    return q.offset(skip).limit(limit).all()


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
