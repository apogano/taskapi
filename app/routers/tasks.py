from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app import schemas
from app.dependencies.auth import CurrentUser
from app.dependencies.tasks import Service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=schemas.TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: schemas.TaskCreate, service: Service, user: CurrentUser):
    return service.create(user.id, payload)


@router.get("", response_model=schemas.Page[schemas.TaskRead])
def list_tasks(
    service: Service,
    user: CurrentUser,
    done: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    items, total = service.list(user.id, done=done, limit=limit, offset=offset)
    return schemas.Page[schemas.TaskRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get("/{task_uuid}", response_model=schemas.TaskRead)
def get_task(task_uuid: UUID, service: Service, user: CurrentUser):
    return service.get(user.id, task_uuid)


@router.patch("/{task_uuid}", response_model=schemas.TaskRead)
def update_task(
    task_uuid: UUID,
    payload: schemas.TaskUpdate,
    service: Service,
    user: CurrentUser,
):
    return service.update(user.id, task_uuid, payload)


@router.delete("/{task_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_uuid: UUID, service: Service, user: CurrentUser):
    service.delete(user.id, task_uuid)
