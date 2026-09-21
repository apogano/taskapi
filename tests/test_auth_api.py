from datetime import timedelta
from uuid import UUID, uuid4

from app.models import User
from app.security import create_access_token

EMAIL = "alice@example.com"
PASSWORD = "test-password"


def register(client, email=EMAIL, password=PASSWORD):
    return client.post("/auth/register", json={"email": email, "password": password})


def login(client, email=EMAIL, password=PASSWORD):
    return client.post("/auth/login", data={"username": email, "password": password})


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_returns_user_without_password(client):
    response = register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == EMAIL
    assert body["is_active"] is True
    assert "password" not in body
    assert "hashed_password" not in body


def test_register_duplicate_email_is_rejected_case_insensitively(client):
    register(client, email="alice@example.com")
    response = register(client, email="ALICE@example.com")

    assert response.status_code == 409


def test_register_rejects_short_password(client):
    assert register(client, password="short").status_code == 422


def test_register_rejects_invalid_email(client):
    assert register(client, email="not-an-email").status_code == 422


def test_password_is_stored_hashed(client, db):
    from sqlalchemy import select

    from app.models import User

    register(client)
    user = db.scalar(select(User).where(User.email == EMAIL))
    assert user.hashed_password != PASSWORD
    assert user.hashed_password.startswith("$argon2")


def test_login_returns_bearer_token(client):
    register(client)
    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_with_wrong_password_returns_401(client):
    register(client)
    assert (login(client, password="wrong-password")).status_code == 401


def test_login_with_unknown_email_returns_401(client):
    assert (login(client, email="nobody@example.com")).status_code == 401


def test_me_with_valid_token(client):
    register(client)
    token = login(client).json()["access_token"]

    response = client.get("/users/me", headers=auth_header(token))

    assert response.status_code == 200
    assert response.json()["email"] == EMAIL


def test_me_without_token_returns_401(client):
    assert client.get("/users/me").status_code == 401


def test_me_with_garbase_token_returns_401(client):
    response = client.get("/users/me", headers=auth_header("garbage"))
    assert response.status_code == 401


def test_me_with_expired_token_returns_401(client):
    user_id = register(client).json()["id"]
    token = create_access_token(user_id, expires_delta=timedelta(minutes=-1))

    assert client.get("users/me", headers=auth_header(token)).status_code == 401


def test_me_with_token_of_unknown_user_returns_401(client):
    token = create_access_token(str(uuid4()))
    assert client.get("/users/me", headers=auth_header(token)).status_code == 401


def test_me_with_token_of_deleted_user_returns_401(client, db):
    user_id = register(client).json()["id"]
    token = login(client).json()["access_token"]
    headers = auth_header(token)
    assert client.get("/users/me", headers=headers).status_code == 200

    db.delete(db.get(User, UUID(user_id)))
    db.commit()

    assert client.get("/users/me", headers=headers).status_code == 401


def test_me_with_token_of_inactive_user_returns_401(client, db):
    user_id = register(client).json()["id"]
    token = login(client).json()["access_token"]

    db.get(User, UUID(user_id)).is_active = False
    db.commit()

    assert client.get("/users/me", headers=auth_header(token)).status_code == 401
