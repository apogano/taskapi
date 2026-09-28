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
