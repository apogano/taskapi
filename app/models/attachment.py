import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

class Attachment(Base):
    __tablename__ = "attachments"

    id : Mapped[uuid.UUID] = mapped_column(primary_key=True,default=uuid.uuid4())
    task_id : Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(255))
    status : Mapped[str] = mapped_column(String(20),default="pending")
    storage_path: Mapped[str] = mapped_column(String(500), unique=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )