from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.repositories.task import TaskRepository
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.task import TaskNotFoundError, TaskService

from app.models import User


@pytest.fixture
def owner(db):
    user = User(email="owner@example.com", hashed_password="not-a-real-hash")
    db.add(user)
    db.flush()
    return user

class FakeTaskRepository:
    def get(self,owner_id, task_id):
        return None


def test_get_missing_task_raises_with_fake_repo():
    service = TaskService(db=MagicMock(), repo=FakeTaskRepository())

    with pytest.raises(TaskNotFoundError):
        service.get(uuid4(), uuid4())


def test_update_missing_task_raises(db,owner):
    service = TaskService(db, TaskRepository(db))

    with pytest.raises(TaskNotFoundError):
        service.update(owner.id,uuid4(), TaskUpdate(done=True))


def test_update_keeps_unset_fields(db,owner):
    service = TaskService(db, TaskRepository(db))
    task = service.create(owner.id,TaskCreate(title="Original", description="Keep me"))

    updated = service.update(owner.id,task.id, TaskUpdate(done=True))

    assert updated.done is True
    assert updated.title == "Original"
    assert updated.description == "Keep me"
