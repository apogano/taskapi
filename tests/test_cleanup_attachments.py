from datetime import UTC, datetime, timedelta

from app.models import Attachment
from app.repositories.attachment import AttachmentRepository
from app.repositories.task import TaskRepository
from app.services.attachment import AttachmentService

EMAIL = "alice@example.com"
PASSWORD = "test-password"


def register(client, email=EMAIL, password=PASSWORD):
    return client.post("/auth/register", json={"email": email, "password": password})


def login(client, email=EMAIL, password=PASSWORD):
    return client.post("/auth/login", data={"username": email, "password": password})


def auth_headers(client):
    register(client)
    tokens = login(client).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def create_task(client, headers):
    return client.post("/tasks", json={"title": "Task"}, headers=headers).json()


def create_attachment(client, headers, task_id):
    return client.post(
        f"/tasks/{task_id}/attachments",
        json={"filename": "test.txt", "content_type": "text/plain"},
        headers=headers,
    ).json()["attachment"]


def test_cleanup_deletes_stale_pending_attachments(client, db, fake_storage):
    headers = auth_headers(client)
    task = create_task(client, headers)
    attachment = create_attachment(client, headers, task["id"])

    row = db.query(Attachment).filter(Attachment.id == attachment["id"]).first()
    row.created_at = datetime.now(UTC) - timedelta(hours=48)
    db.commit()

    service = AttachmentService(db, AttachmentRepository(db), TaskRepository(db))
    deleted = service.cleanup_stale_pending(older_than_hours=24)
    db.commit()

    assert deleted == 1
    assert db.query(Attachment).count() == 0


def test_cleanup_keeps_recent_pending_attachments(client, db, fake_storage):
    headers = auth_headers(client)
    task = create_task(client, headers)
    create_attachment(client, headers, task["id"])  # created just now

    service = AttachmentService(db, AttachmentRepository(db), TaskRepository(db))
    deleted = service.cleanup_stale_pending(older_than_hours=24)
    db.commit()

    assert deleted == 0
    assert db.query(Attachment).count() == 1


def test_cleanup_keeps_uploaded_attachments_even_if_old(client, db, fake_storage):
    headers = auth_headers(client)
    task = create_task(client, headers)
    attachment = create_attachment(client, headers, task["id"])

    storage_path = f"tasks/{task['id']}/{attachment['id']}/test.txt"
    fake_storage[storage_path] = 100
    client.post(f"/tasks/{task['id']}/attachments/{attachment['id']}/confirm", headers=headers)

    row = db.query(Attachment).filter(Attachment.id == attachment["id"]).first()
    row.created_at = datetime.now(UTC) - timedelta(hours=48)
    db.commit()

    service = AttachmentService(db, AttachmentRepository(db), TaskRepository(db))
    deleted = service.cleanup_stale_pending(older_than_hours=24)
    db.commit()

    # Confirmed uploads are never touched by this cleanup, no matter how old
    assert deleted == 0
    assert db.query(Attachment).count() == 1


def test_cleanup_also_removes_the_storage_object_if_present(client, db, fake_storage):
    headers = auth_headers(client)
    task = create_task(client, headers)
    attachment = create_attachment(client, headers, task["id"])

    # Simulate a partial/abandoned upload: a file exists in storage, but
    # confirm was never called, so the row is still "pending"
    storage_path = f"tasks/{task['id']}/{attachment['id']}/test.txt"
    fake_storage[storage_path] = 50

    row = db.query(Attachment).filter(Attachment.id == attachment["id"]).first()
    row.created_at = datetime.now(UTC) - timedelta(hours=48)
    db.commit()

    service = AttachmentService(db, AttachmentRepository(db), TaskRepository(db))
    service.cleanup_stale_pending(older_than_hours=24)
    db.commit()

    assert storage_path not in fake_storage