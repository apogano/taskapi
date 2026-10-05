import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.orm import Session

import app.models
from app.config import settings
from app.database import Base, get_db
from app.main import app

_dev_url = make_url(settings.database_url)
TEST_URL = _dev_url.set(database=f"{_dev_url.database}_test")


def _ensure_database() -> None:
    admin = create_engine(
        TEST_URL.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_URL.database},
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_URL.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def engine():
    assert TEST_URL.database.endswith("_test")
    _ensure_database()
    engine = create_engine(TEST_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
    )
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def login_as(client):
    def _login(email: str, password: str = "test-password") -> dict:
        client.post("/auth/register", json={"email": email, "password": password})
        response = client.post(
            "/auth/login", data={"username": email, "password": password}
        )
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login


@pytest.fixture
def fake_storage(monkeypatch):
    """Replaces app.storage's GCS calls with in-memory fakes, so attachment
    tests don't hit real Google Cloud Storage. Returns the in-memory dict
    of uploaded blobs (path -> size in bytes) so tests can simulate an
    upload having happened."""
    uploaded_blobs: dict[str, int] = {}

    def fake_generate_upload_url(storage_path, content_type, expires_minutes):
        return f"https://fake-upload-url/{storage_path}"

    def fake_generate_download_url(storage_path, expires_minutes):
        return f"https://fake-download-url/{storage_path}"

    def fake_get_blob_size(storage_path):
        return uploaded_blobs.get(storage_path)

    def fake_delete_object(storage_path):
        uploaded_blobs.pop(storage_path, None)

    monkeypatch.setattr(
        "app.services.attachment.generate_upload_url", fake_generate_upload_url
    )
    monkeypatch.setattr(
        "app.services.attachment.generate_download_url", fake_generate_download_url
    )
    monkeypatch.setattr("app.services.attachment.get_blob_size", fake_get_blob_size)
    monkeypatch.setattr("app.services.attachment.delete_object", fake_delete_object)

    return uploaded_blobs
