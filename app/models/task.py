from datetime import datetime
import uuid


from sqlalchemy import DateTime, String, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base

class Task(Base):
    __tablename__ = "tasks"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    title : Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(2000))
    done: Mapped[bool] = mapped_column(default=False)
    priority: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at : Mapped[datetime] = mapped_column (DateTime(timezone=True),server_default=func.now())

