import logging
import re

from app.database import get_db
from app.main import app
from app.repositories.user import UserRepository
from app.logging_config import RequestIdFilter

EMAIL = "alice@example.com"
PASSWORD = "test-password"


def test_app_configures_logging():
    import app.main  # noqa: F401 

    handlers = logging.getLogger().handlers
    assert any(
        isinstance(f, RequestIdFilter) for h in handlers for f in h.filters
    )
    
def test_response_has_request_id(client):
    response = client.get("/users/me")
    assert response.headers["X-Request-ID"]

def test_incoming_request_id_is_kept(client):
    response = client.get("/users/me", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


def test_malformed_request_id_is_replaced(client):
    response = client.get("/users/me", headers={"X-Request-ID": "bad id with spaces"})
    request_id = response.headers["X-Request-ID"]
    assert request_id != "bad id with spaces"
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id)

def test_unhandled_error_returns_500_without_leaking_details(client,caplog):
    def broken_db():
        raise RuntimeError("secret internal detail")
    
    app.dependency_overrides[get_db] = broken_db
    
    response = client.post("/auth/register",json={"email":EMAIL,"password":PASSWORD})
    
    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert "secret internal detail" not in response.text
    assert any(r.levelno == logging.ERROR for r in caplog.records)

def test_failed_login_is_logged_without_email(client, caplog):
    caplog.set_level(logging.WARNING)

    client.post(
        "/auth/login", data={"username": "nobody@example.com", "password": "whatever-123"}
    )

    assert "Failed login attempt" in caplog.text
    assert "nobody@example.com" not in caplog.text


def test_register_race_condition_returns_409(client, monkeypatch):
    client.post("/auth/register", json={"email":EMAIL,"password":PASSWORD})
    #Simulationg that first check didn't see the existing user
    monkeypatch.setattr(UserRepository, "get_by_email", lambda self, email: None)

    response = client.post("/auth/register", json={"email":EMAIL,"password":PASSWORD})

    assert response.status_code == 409
