from datetime import datetime


from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base

class Task(Base):
    __tablename__ = "tasks"
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    title : Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(2000))
    done: Mapped[bool] = mapped_column(default=False)
    created_at : Mapped[datetime] = mapped_column (DateTime(timezone=True),server_default=func.now())

