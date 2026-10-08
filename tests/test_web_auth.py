from app.config import settings

EMAIL = "alice@example.com"
PASSWORD = "test-password"
COOKIE = settings.refresh_cookie_name


def register(client, email=EMAIL, password=PASSWORD):
    return client.post("/auth/register", json={"email": email, "password": password})


def web_login(client, email=EMAIL, password=PASSWORD):
    return client.post(
        "/auth/web/login", data={"username": email, "password": password}
    )


def native_login(client, email=EMAIL, password=PASSWORD):
    return client.post("/auth/login", data={"username": email, "password": password})


def web_refresh_with(client, token):
    # Sends a specific cookie value explicity, bypassing the client's jar
    # so a test can replay an old token
    client.cookies.clear()
    return client.post("/auth/web/refresh", headers={"Cookie": f"{COOKIE}={token}"})


def test_web_login_puts_refresh_token_only_in_httponly_cookie(client):
    register(client)
    response = web_login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert "refresh_token" not in body

    set_cookie = response.headers["set-cookie"].lower()
    assert f"{COOKIE}=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "path=/auth/web" in set_cookie


def test_web_refresh_rotates_the_cookie(client):
    register(client)
    web_login(client)
    first = client.cookies.get(COOKIE)

    response = client.post("/auth/web/refresh")

    assert response.status_code == 200
    assert "refresh_token" not in response.json()
    assert client.cookies.get(COOKIE) != first


def test_web_refresh_without_cookie_returns_401(client):
    assert client.post("/auth/web/refresh").status_code == 401


def test_reusing_a_rotated_web_cookie_revokes_the_family(client):
    register(client)
    web_login(client)
    original = client.cookies.get(COOKIE)
    client.post("/auth/web/refresh")
    rotated = client.cookies.get(COOKIE)

    assert web_refresh_with(client, original).status_code == 401
    # Theft detection revoked the whole family, including the legitimate token
    assert web_refresh_with(client, rotated).status_code == 401


def test_web_logout_revokes_and_clears_cookie(client):
    register(client)
    web_login(client)
    token = client.cookies.get(COOKIE)

    response = client.post("/auth/web/logout")

    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert web_refresh_with(client, token).status_code == 401


def test_failed_web_refresh_clears_the_cookie(client):
    response = web_refresh_with(client, "not-a-real-token")

    assert response.status_code == 401
    assert "max-age=0" in response.headers["set-cookie"].lower()


# --- the two flows (native and web) must never cross over ---
def test_web_refresh_ignores_a_token_in_the_body(client):
    register(client)
    tokens = native_login(client).json()
    client.cookies.clear()

    response = client.post(
        "/auth/web/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 401


def test_native_refresh_ignores_the_cookie(client):
    register(client)
    web_login(client)
    token = client.cookies.get(COOKIE)

    # Cookie present, body missing: the native endpoint must not fall back to it
    response = client.post("/auth/refresh", headers={"Cookie": f"{COOKIE}={token}"})
    assert response.status_code == 422


def test_native_login_sets_no_cookie(client):
    register(client)
    response = native_login(client)

    assert response.status_code == 200
    assert "set-cookie" not in response.headers


def test_web_and_native_login_share_rate_limits(client):
    register(client)
    for i in range(settings.rate_limit_login_attempts):
        attempt = web_login if i % 2 == 0 else native_login
        attempt(client, password="wrong-password")

    # Alternating endpoints must not have bought any extra attempts
    assert native_login(client, password="wrong-password").status_code == 429
    assert web_login(client, password="wrong-password").status_code == 429


def test_failed_native_refresh_sets_no_cookie(client):
    response = client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})

    assert response.status_code == 401
    assert "set-cookie" not in response.headers
