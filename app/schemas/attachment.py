from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AttachmentCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=100)


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    content_type: str
    status: str
    created_at: datetime


class UploadUrlResponse(BaseModel):
    attachment: AttachmentRead
    upload_url: str


class DownloadUrlResponse(BaseModel):
    download_url: str
