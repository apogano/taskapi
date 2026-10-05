EMAIL = "alice@example.com"
PASSWORD = "test-password"


def auth_headers(client):
    client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    tokens = client.post(
        "/auth/login", data={"username": EMAIL, "password": PASSWORD}
    ).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def create_task(client, headers):
    return client.post("/tasks", json={"title": "Task with attachment"}, headers=headers).json()


def create_attachment(client, headers, task_id, filename="test.txt", content_type="text/plain"):
    return client.post(
        f"/tasks/{task_id}/attachments",
        json={"filename": filename, "content_type": content_type},
        headers=headers,
    )


def test_create_attachment_returns_pending_status_and_upload_url(client, fake_storage):
    headers = auth_headers(client)
    task = create_task(client, headers)

    response = create_attachment(client, headers, task["id"])

    assert response.status_code == 201
    body = response.json()
    assert body["attachment"]["status"] == "pending"
    assert body["attachment"]["filename"] == "test.txt"
    assert body["upload_url"].startswith("https://fake-upload-url/")


def test_create_attachment_on_missing_task_returns_404(client, fake_storage):
    headers = auth_headers(client)
    response = create_attachment(client, headers, "00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_create_attachment_on_other_users_task_returns_404(client, fake_storage):
    headers = auth_headers(client)
    task = create_task(client, headers)

    bob_headers = {}
    client.post("/auth/register", json={"email": "bob@example.com", "password": PASSWORD})
    bob_tokens = client.post(
        "/auth/login", data={"username": "bob@example.com", "password": PASSWORD}
    ).json()
    bob_headers = {"Authorization": f"Bearer {bob_tokens['access_token']}"}

    response = create_attachment(client, bob_headers, task["id"])
    assert response.status_code == 404


def test_confirm_marks_attachment_as_uploaded(client, fake_storage):
    headers = auth_headers(client)
    task = create_task(client, headers)
    attachment = create_attachment(client, headers, task["id"]).json()["attachment"]

    # Simulate the client having uploaded the file directly to GCS
    storage_path = f"tasks/{task['id']}/{attachment['id']}/test.txt"
    fake_storage[storage_path] = 100  # 100 bytes

    response = client.post(
        f"/tasks/{task['id']}/attachments/{attachment['id']}/confirm", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "uploaded"


def test_confirm_without_upload_returns_404(client, fake_storage):
    headers = auth_headers(client)
    task = create_task(client, headers)
    attachment = create_attachment(client, headers, task["id"]).json()["attachment"]

    # Nothing was added to fake_storage, so get_blob_size returns None
    response = client.post(
        f"/tasks/{task['id']}/attachments/{attachment['id']}/confirm", headers=headers
    )

    assert response.status_code == 404


def test_confirm_rejects_file_over_size_limit(client, fake_storage):
    from app.config import settings

    headers = auth_headers(client)
    task = create_task(client, headers)
    attachment = create_attachment(client, headers, task["id"]).json()["attachment"]

    storage_path = f"tasks/{task['id']}/{attachment['id']}/test.txt"
    too_big = settings.attachment_max_size_mb * 1024 * 1024 + 1
    fake_storage[storage_path] = too_big

    response = client.post(
        f"/tasks/{task['id']}/attachments/{attachment['id']}/confirm", headers=headers
    )

    assert response.status_code == 413
    # The oversized file must be removed from storage, not left dangling
    assert storage_path not in fake_storage


def test_confirm_rejects_file_over_size_limit_deletes_db_row_too(client, fake_storage):
    from app.config import settings

    headers = auth_headers(client)
    task = create_task(client, headers)
    attachment = create_attachment(client, headers, task["id"]).json()["attachment"]

    storage_path = f"tasks/{task['id']}/{attachment['id']}/test.txt"
    fake_storage[storage_path] = settings.attachment_max_size_mb * 1024 * 1024 + 1

    client.post(
        f"/tasks/{task['id']}/attachments/{attachment['id']}/confirm", headers=headers
    )

    # The record is gone, not just the storage object
    download_response = client.get(
        f"/tasks/{task['id']}/attachments/{attachment['id']}/download-url", headers=headers
    )
    assert download_response.status_code == 404


def test_download_url_before_confirm_returns_409(client, fake_storage):
    headers = auth_headers(client)
    task = create_task(client, headers)
    attachment = create_attachment(client, headers, task["id"]).json()["attachment"]

    response = client.get(
        f"/tasks/{task['id']}/attachments/{attachment['id']}/download-url", headers=headers
    )

    assert response.status_code == 409


def test_download_url_after_confirm_returns_url(client, fake_storage):
    headers = auth_headers(client)
    task = create_task(client, headers)
    attachment = create_attachment(client, headers, task["id"]).json()["attachment"]

    storage_path = f"tasks/{task['id']}/{attachment['id']}/test.txt"
    fake_storage[storage_path] = 100
    client.post(f"/tasks/{task['id']}/attachments/{attachment['id']}/confirm", headers=headers)

    response = client.get(
        f"/tasks/{task['id']}/attachments/{attachment['id']}/download-url", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["download_url"].startswith("https://fake-download-url/")


def test_delete_attachment_removes_from_storage_and_db(client, fake_storage):
    headers = auth_headers(client)
    task = create_task(client, headers)
    attachment = create_attachment(client, headers, task["id"]).json()["attachment"]

    storage_path = f"tasks/{task['id']}/{attachment['id']}/test.txt"
    fake_storage[storage_path] = 100

    response = client.delete(
        f"/tasks/{task['id']}/attachments/{attachment['id']}", headers=headers
    )

    assert response.status_code == 204
    assert storage_path not in fake_storage

    # Gone from the DB too
    confirm_again = client.post(
        f"/tasks/{task['id']}/attachments/{attachment['id']}/confirm", headers=headers
    )
    assert confirm_again.status_code == 404


def test_task_deletion_cascades_to_attachments(client, db, fake_storage):
    from app.models import Attachment

    headers = auth_headers(client)
    task = create_task(client, headers)
    attachment = create_attachment(client, headers, task["id"]).json()["attachment"]

    client.delete(f"/tasks/{task['id']}", headers=headers)

    # The attachment row is gone via ON DELETE CASCADE, even though we
    # never called the attachment delete endpoint
    remaining = db.query(Attachment).filter(Attachment.id == attachment["id"]).first()
    assert remaining is None