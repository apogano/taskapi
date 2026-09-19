from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Task
from app.repositories.task import TaskRepository
from app.schemas.task import TaskCreate, TaskUpdate

class TaskNotFoundError(Exception):
    def __init__(self, task_id:UUID):
        super().__init__(f"Task {task_id} not found")
        self.task_id = task_id

class TaskService:
    def __init__(self, db:Session, repo:TaskRepository):
        self.db = db
        self.repo = repo
    
    def create(self, owner_id:UUID,payload: TaskCreate) -> Task:
        task = self.repo.add(Task(**payload.model_dump(), owner_id=owner_id))
        self.db.commit()
        self.db.refresh(task)
        return task
        
    def get(self,  owner_id:UUID, task_uuid:UUID) -> Task:
        task = self.repo.get(owner_id,task_uuid)
        if task is None:
            raise TaskNotFoundError(task_uuid)
        return task
    
    def list(self,owner_id:UUID, *,  done:bool|None=None, limit:int=50, offset:int=0 )->list[Task]:
        return self.repo.list(owner_id,done=done,limit=limit,offset=offset)
    
    def update(self,owner_id:UUID, task_id:UUID, payload:TaskUpdate)->Task:
        task = self.get(owner_id,task_id)
        for field,value in payload.model_dump(exclude_unset=True).items():
            setattr(task,field,value)
        self.db.commit()
        self.db.refresh(task)
        return task
    
    def delete(self,owner_id:UUID, task_id:UUID)->None:
        task = self.get(owner_id,task_id)
        self.repo.delete(task)
        self.db.commit()
