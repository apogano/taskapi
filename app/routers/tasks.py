from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import task as task_model
from app.schemas import task as task_schema
from app.database import get_db

router = APIRouter(prefix="/tasks",tags=["tasks"])

DBSession = Annotated[Session, Depends(get_db)]

def get_task_or_404(db:Session, task_uuid:UUID)-> task_model.Task:
    task = db.get(task_model.Task, task_uuid)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task
    
@router.post("",response_model=task_schema.TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: task_schema.TaskCreate, db:DBSession):
    task = models.Task(**payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

@router.get("/{task_uuid}",response_model=task_schema.TaskRead)
def get_task(task_uuid:UUID, db:DBSession):
    return get_task_or_404(db,task_uuid)

@router.patch("/{task_uuid}",response_model=task_schema.TaskRead)
def update_task(task_uuid:UUID,payload:task_schema.TaskUpdate, db:DBSession):
    task = get_task_or_404(db,task_uuid)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task,field,value)
    db.commit()
    db.refresh(task)
    return task
    
@router.delete("/{task_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_uuid: UUID, db: DBSession):
    task = get_task_or_404(db, task_uuid)
    db.delete(task)
    db.commit()
