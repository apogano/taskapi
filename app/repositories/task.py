from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task

class TaskRepository:
    def __init__(self,db:Session):
        self.db = db
    
    def get(self,owner_id:UUID, task_uuid:UUID) -> Task |None:
        return self.db.scalar(
            select(Task).where(Task.id==task_uuid, Task.owner_id==owner_id)
        )
    
    def list(self,owner_id:UUID,*, done:bool | None = None, limit: int=50, offset:int=0)-> list[Task]:
        stmt = select(Task).where(Task.owner_id==owner_id)
        if done is not None:
            stmt = stmt.where(Task.done == done)
        stmt = stmt.order_by(Task.created_at,Task.id)
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))
    
    def add(self, task:Task) -> Task:
        self.db.add(task)
        self.db.flush()
        return task

    def delete(self, task:Task) -> None:
        self.db.delete(task)
