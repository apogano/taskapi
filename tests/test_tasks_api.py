from uuid import UUID, uuid4


def create_task(client, **overrides):
    payload = {"title": "Learn FastAPI", **overrides}
    response = client.post("/tasks", json=payload)
    assert response.status_code == 201
    return response.json()


def test_create_task(client):
    response = client.post("/tasks", json={"title": "Learn FastAPI", "description": "Basics"})

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Learn FastAPI"
    assert body["description"] == "Basics"
    assert body["done"] is False
    UUID(body["id"])  # πετάει exception αν δεν είναι έγκυρο UUID


def test_create_task_with_empty_title_is_rejected(client):
    response = client.post("/tasks", json={"title": ""})
    assert response.status_code == 422
    
def test_create_task_with_max_length_description_is_accepted(client):
    response = client.post(
        "/tasks", json={"title": "Test", "description": "x" * 2000}
    )
    assert response.status_code == 201


def test_create_task_with_long_description_is_rejected(client):
    long_description = "x" * 2001
    response = client.post("/tasks", json={"title": "testDescription","description":long_description})
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "string_too_long"


def test_update_task_with_empty_title_is_rejected(client):
    task = create_task(client, title="Original", description="Test empty title")
    response = client.patch(f"/tasks/{task['id']}", json={"title": ""})
    assert response.status_code == 422    
    assert client.get(f"/tasks/{task['id']}").json()["title"] == "Original"


def test_get_task(client):
    task = create_task(client)
    response = client.get(f"/tasks/{task['id']}")
    assert response.status_code == 200
    assert response.json() == task


def test_get_missing_task_returns_404(client):
    response = client.get(f"/tasks/{uuid4()}")
    assert response.status_code == 404


def test_invalid_uuid_returns_422(client):
    response = client.get("/tasks/not-a-uuid")
    assert response.status_code == 422


def test_patch_updates_only_sent_fields(client):
    task = create_task(client, title="Original", description="Keep me")

    response = client.patch(f"/tasks/{task['id']}", json={"done": True})

    assert response.status_code == 200
    body = response.json()
    assert body["done"] is True
    assert body["title"] == "Original"
    assert body["description"] == "Keep me"


def test_delete_task(client):
    task = create_task(client)

    assert client.delete(f"/tasks/{task['id']}").status_code == 204
    assert client.get(f"/tasks/{task['id']}").status_code == 404


def test_list_filters_by_done(client):
    open_task = create_task(client, title="Open")
    done_task = create_task(client, title="Done")
    client.patch(f"/tasks/{done_task['id']}", json={"done": True})

    response = client.get("/tasks", params={"done": True})

    ids = [t["id"] for t in response.json()]
    assert ids == [done_task["id"]]
    assert open_task["id"] not in ids


def test_list_pagination_does_not_overlap(client):
    created = {create_task(client, title=f"Task {i}")["id"] for i in range(3)}

    page1 = client.get("/tasks", params={"limit": 2, "offset": 0}).json()
    page2 = client.get("/tasks", params={"limit": 2, "offset": 2}).json()

    assert len(page1) == 2
    assert len(page2) == 1
    assert {t["id"] for t in page1 + page2} == created


def test_list_rejects_out_of_range_limit(client):
    assert client.get("/tasks", params={"limit": 1000}).status_code == 422
    assert client.get("/tasks", params={"limit": 0}).status_code == 422
