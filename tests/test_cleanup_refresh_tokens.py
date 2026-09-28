from datetime import UTC, datetime, timedelta

from app.models import RefreshToken
from app.repositories.refresh_token import RefreshTokenRepository

EMAIL = "alice@example.com"
PASSWORD = "test-password"


def register(client, email=EMAIL, password=PASSWORD):
    return client.post("/auth/register", json={"email": email, "password": password})


def login(client, email=EMAIL, password=PASSWORD):
    return client.post("/auth/login", data={"username": email, "password": password})


def test_cleanup_deletes_expired_tokens(client, db):
    register(client)
    login(client)  # δημιουργεί ένα refresh token στη βάση

    token = db.query(RefreshToken).first()
    token.expires_at = datetime.now(UTC) - timedelta(days=1)
    db.commit()

    deleted = RefreshTokenRepository(db).delete_expired_and_revoked()
    db.commit()

    assert deleted == 1
    assert db.query(RefreshToken).count() == 0


def test_cleanup_keeps_active_tokens(client, db):
    register(client)
    login(client)

    deleted = RefreshTokenRepository(db).delete_expired_and_revoked()
    db.commit()

    assert deleted == 0
    assert db.query(RefreshToken).count() == 1


def test_cleanup_respects_grace_period_for_revoked_tokens(client, db):
    register(client)
    login(client)

    token = db.query(RefreshToken).first()
    token.revoked_at = datetime.now(UTC) - timedelta(days=1)  # μόλις ανακλήθηκε
    db.commit()

    deleted = RefreshTokenRepository(db).delete_expired_and_revoked(
        revoked_grace_period_days=7
    )
    db.commit()

    assert deleted == 0  # ακόμα μέσα στο grace period, δεν σβήνεται
    assert db.query(RefreshToken).count() == 1


def test_cleanup_deletes_revoked_tokens_past_grace_period(client, db):
    register(client)
    login(client)

    token = db.query(RefreshToken).first()
    token.revoked_at = datetime.now(UTC) - timedelta(days=10)  # παλιό
    db.commit()

    deleted = RefreshTokenRepository(db).delete_expired_and_revoked(
        revoked_grace_period_days=7
    )
    db.commit()

    assert deleted == 1
    assert db.query(RefreshToken).count() == 0
