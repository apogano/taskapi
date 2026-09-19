from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import  task as task_models
from app.schemas import task as task_schema
from app.database import get_db

from app.dependencies.tasks import Service
from app.dependencies.auth import CurrentUser

router = APIRouter(prefix="/tasks",tags=["tasks"])


@router.post("",response_model=task_schema.TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: task_schema.TaskCreate, service: Service, user: CurrentUser):
    return service.create(user.id,payload)

@router.get("", response_model=list[task_schema.TaskRead])
def list_tasks(
    service: Service,
    user: CurrentUser,
    done: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return service.list(user.id,done=done, limit=limit, offset=offset)
    
@router.get("/{task_uuid}",response_model=task_schema.TaskRead)
def get_task(task_uuid:UUID, service: Service,  user: CurrentUser):
    return service.get(user.id,task_uuid)

@router.patch("/{task_uuid}",response_model=task_schema.TaskRead)
def update_task(task_uuid:UUID,payload:task_schema.TaskUpdate, service: Service, user: CurrentUser):
    return service.update(user.id,task_uuid, payload)
    
@router.delete("/{task_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_uuid: UUID,  service: Service, user: CurrentUser):
    service.delete(user.id,task_uuid)
