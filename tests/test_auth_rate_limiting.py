from app.config import settings
    
EMAIL = "alice@example.com"
PASSWORD = "test-password"


def register(client, email=EMAIL, password=PASSWORD):
    return client.post("/auth/register", json={"email": email, "password": password})


def login(client, email=EMAIL, password=PASSWORD):
    return client.post("/auth/login", data={"username": email, "password": password})


def test_login_rate_limit_blocks_after_threshold(client):

    for _ in range(settings.rate_limit_login_attempts):
        login(client, password="wrong-password")

    response = login(client, password="wrong-password")

    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_login_rate_limit_applies_even_with_correct_password(client):
    # The rate limit is enforced BEFORE the password check, so it also
    # protects against brute-force attempts using an already-known correct
    # password (e.g. credential stuffing), not just failed attempts.

    register(client)
    for _ in range(settings.rate_limit_login_attempts):
        login(client, password="wrong-password")

    response = login(client)  # τώρα με το ΣΩΣΤΟ password

    assert response.status_code == 429


def test_register_rate_limit_blocks_after_threshold(client):
    for i in range(settings.rate_limit_register_attempts):
        register(client, email=f"user{i}@example.com")

    response = register(client, email="one-too-many@example.com")

    assert response.status_code == 429


def test_rate_limits_are_independent_per_endpoint(client):
    # TestClient always sends the same internal test IP, so this confirms
    # that different endpoints use independent keys, not that different
    # real-world IPs are isolated from each other.
    for _ in range(settings.rate_limit_login_attempts):
        login(client, password="wrong-password")

    # login hit its limit, but register has its own, independent key
    response = register(client, email="still-works@example.com")
    assert response.status_code == 201


def login_from_ip(client, ip, email=EMAIL, password=PASSWORD):
    return client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"X-Forwarded-For": ip},
    )


def test_per_account_limit_blocks_attacks_spread_across_many_ips(client):
    register(client)

    # Each attempt comes from a DIFFERENT IP, so the per-IP limit never
    # triggers on its own. The per-account limit must still catch this.
    for i in range(settings.rate_limit_login_account_attempts):
        response = login_from_ip(client, f"10.0.0.{i}", password="wrong-password")
        assert response.status_code == 401  # still under the account limit

    blocked = login_from_ip(
        client, "10.0.0.999", password="wrong-password"
    )
    assert blocked.status_code == 429


def test_per_account_limit_is_independent_of_ip_limit(client):
    register(client, email="alice@example.com")
    register(client, email="bob@example.com")

    # Exhaust alice's account-scoped limit from many different IPs.
    for i in range(settings.rate_limit_login_account_attempts):
        login_from_ip(client, f"10.0.1.{i}", email="alice@example.com", password="wrong-password")

    alice_blocked = login_from_ip(
        client, "10.0.1.999", email="alice@example.com", password="wrong-password"
    )
    assert alice_blocked.status_code == 429

    # bob, from one of the SAME ips, is unaffected: the account key is
    # different, and none of those individual IPs hit their own per-IP limit
    bob_response = login_from_ip(
        client, "10.0.1.0", email="bob@example.com", password="wrong-password"
    )
    assert bob_response.status_code == 401  # not 429


def test_per_account_limit_uses_email_case_insensitively(client):
    register(client, email="alice@example.com")

    for i in range(settings.rate_limit_login_account_attempts):
        login_from_ip(
            client, f"10.0.2.{i}", email="alice@example.com", password="wrong-password"
        )

    # Same account, different casing, different (fresh) IP — must still be blocked
    blocked = login_from_ip(
        client, "10.0.2.999", email="ALICE@EXAMPLE.COM", password="wrong-password"
    )
    assert blocked.status_code == 429
