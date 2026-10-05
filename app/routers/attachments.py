from uuid import UUID

from fastapi import APIRouter, status

from app import schemas
from app.dependencies.attachment import AttachmentServiceDep
from app.dependencies.auth import CurrentUser

router = APIRouter(prefix="/tasks/{task_id}/attachments",tags=["attachments"])

@router.post("", response_model=schemas.UploadUrlResponse,status_code=status.HTTP_201_CREATED)
def create_attachment(
    task_id:UUID,
    payload: schemas.AttachmentCreate,
    user:CurrentUser,
    service:AttachmentServiceDep,
):
    attachment, upload_url = service.create(user.id,task_id,payload)
    return schemas.UploadUrlResponse(
        attachment=schemas.AttachmentRead.model_validate(attachment),
        upload_url=upload_url
    )

@router.post("/{attachment_id}/confirm",response_model=schemas.AttachmentRead)
def confirm_attachment(
    task_id:UUID,
    attachment_id:UUID,
    user:CurrentUser,
    service:AttachmentServiceDep
):
    return service.confirm(user.id,task_id,attachment_id)

@router.get("/{attachment_id}/download-url",response_model=schemas.DownloadUrlResponse)
def get_download_url(
    task_id:UUID,
    attachment_id:UUID,
    user:CurrentUser,
    service: AttachmentServiceDep
):
    url = service.get_download_url(user.id,task_id,attachment_id)
    return schemas.DownloadUrlResponse(download_url=url)

@router.delete("/{attachment_id}",status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    task_id:UUID,
    attachment_id:UUID,
    user:CurrentUser,
    service: AttachmentServiceDep
):
    service.delete(user.id,task_id,attachment_id)