from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

class TaskCreate(BaseModel):
    title : str = Field(min_length=1, max_length=200)
    description : str | None = Field(default=None, max_length=2000)
    
class TaskUpdate(BaseModel):
    title : str | None = Field(default=None , min_length=1, max_length = 200)
    description : str | None = Field(default=None, max_length=2000)
    done : bool | None = None

class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    title: str
    description: str | None
    done: bool
    created_at: datetime
    
