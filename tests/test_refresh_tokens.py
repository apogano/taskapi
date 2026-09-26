from datetime import UTC

EMAIL = "alice@example.com"
PASSWORD = "test-password"


def register(client, email=EMAIL, password=PASSWORD):
    return client.post("/auth/register", json={"email": email, "password": password})


def login(client, email=EMAIL, password=PASSWORD):
    return client.post("/auth/login", data={"username": email, "password": password})


def refresh(client, token):
    return client.post("/auth/refresh", json={"refresh_token": token})


def logout(client, token):
    return client.post("/auth/logout", json={"refresh_token": token})


def test_refresh_returns_new_token_pair(client):
    register(client)
    tokens = login(client).json()

    response = refresh(client, tokens["refresh_token"])

    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["access_token"]
    assert new_tokens["refresh_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]


def test_new_access_token_works_on_protected_endpoint(client):
    register(client)
    tokens = login(client).json()

    new_tokens = refresh(client, tokens["refresh_token"]).json()

    me = client.get(
        "/users/me", headers={"Authorization": f"Bearer {new_tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == EMAIL


def test_old_refresh_token_cannot_be_reused(client):
    register(client)
    tokens = login(client).json()

    first = refresh(client, tokens["refresh_token"])
    assert first.status_code == 200

    second = refresh(client, tokens["refresh_token"])  # ίδιο, ήδη-χρησιμοποιημένο token
    assert second.status_code == 401


def test_reuse_of_revoked_token_revokes_whole_family(client):
    register(client)
    tokens = login(client).json()

    first_rotation = refresh(client, tokens["refresh_token"]).json()

    # Reuse the ORIGINAL (revoked already) token --> suspicious
    reuse_attempt = refresh(client, tokens["refresh_token"])
    assert reuse_attempt.status_code == 401

    # The first token which is legit should be also revoked
    # as it belongs to same family
    third = refresh(client, first_rotation["refresh_token"])
    assert third.status_code == 401


def test_refresh_with_unknown_token_returns_401(client):
    response = refresh(client, "this-token-does-not-exist")
    assert response.status_code == 401


def test_refresh_with_expired_token_returns_401(client, db):
    from datetime import datetime, timedelta

    from app.models import RefreshToken

    register(client)
    tokens = login(client).json()

    record = (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id.isnot(None))
        .order_by(RefreshToken.created_at.desc())
        .first()
    )
    record.expires_at = datetime.now(UTC) - timedelta(days=1)
    db.commit()

    response = refresh(client, tokens["refresh_token"])
    assert response.status_code == 401


def test_logout_revokes_refresh_token(client):
    register(client)
    tokens = login(client).json()

    response = logout(client, tokens["refresh_token"])
    assert response.status_code == 204

    reuse = refresh(client, tokens["refresh_token"])
    assert reuse.status_code == 401


def test_logout_is_idempotent(client):
    register(client)
    tokens = login(client).json()

    logout(client, tokens["refresh_token"])
    second_logout = logout(client, tokens["refresh_token"])

    assert second_logout.status_code == 204  # όχι σφάλμα, απλά δεν κάνει τίποτα


def test_logout_with_unknown_token_returns_204(client):
    response = logout(client, "this-token-does-not-exist")
    assert response.status_code == 204


def test_new_login_creates_separate_family_from_previous(client, db):
    from app.models import RefreshToken

    register(client)
    first_login = login(client).json()
    second_login = login(client).json()

    families = {
        r.family_id
        for r in db.query(RefreshToken).filter(RefreshToken.user_id.isnot(None)).all()
    }
    assert len(families) == 2  # two different logins -> two different families

    # The first login's refresh token must continue valid
    first_response = refresh(client, first_login["refresh_token"])
    assert first_response.status_code == 200
    second_response = refresh(client, second_login["refresh_token"])
    assert second_response.status_code == 200
