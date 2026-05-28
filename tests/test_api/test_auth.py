import time
import pytest
from fastapi import status
from httpx import AsyncClient
from master.main import app
from master.api import deps
from master.core.security_manager import SecurityManager


@pytest.fixture
async def client(db):
    from httpx import AsyncClient, ASGITransport
    app.dependency_overrides[deps.get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(deps.get_db, None)


@pytest.fixture(autouse=True)
def clear_rate_limiter():
    from master.core.rate_limiter import rate_limiter
    rate_limiter._buckets.clear()


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, db):
    # The default admin user is seeded: admin / admin
    response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0

    # Verify last_login updated
    async with db.execute("SELECT last_login FROM users WHERE username = 'admin'") as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row["last_login"] is not None
        assert row["last_login"] > 0


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrongpassword"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "invalid credentials" in response.json()["detail"].lower()

    # User enumeration mitigation test
    response_nonexistent = await client.post(
        "/api/auth/login",
        json={"username": "nonexistent", "password": "anypassword"}
    )
    assert response_nonexistent.status_code == status.HTTP_401_UNAUTHORIZED
    assert "invalid credentials" in response_nonexistent.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_inactive_user(client: AsyncClient, db, security: SecurityManager):
    # Insert inactive user
    import uuid
    user_id = str(uuid.uuid4())
    pw_hash = security.hash_password("password123")
    await db.execute(
        "INSERT INTO users (id, username, password_hash, role, is_active, must_change_password, created_at, updated_at) "
        "VALUES (?, 'inactive_user', ?, 'viewer', 0, 0, ?, ?)",
        (user_id, pw_hash, time.time(), time.time())
    )
    await db.commit()

    response = await client.post(
        "/api/auth/login",
        json={"username": "inactive_user", "password": "password123"}
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "account deactivated" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_refresh_token_success(client: AsyncClient, db):
    # Login to get valid refresh token
    login_resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"}
    )
    refresh_token = login_resp.json()["refresh_token"]

    # Call refresh endpoint
    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_refresh_token_theft_detection(client: AsyncClient, db):
    # Login to get valid refresh token
    login_resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"}
    )
    refresh_token = login_resp.json()["refresh_token"]

    # 1. Use token once (this will revoke the original token and return new ones)
    refresh_resp_1 = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert refresh_resp_1.status_code == status.HTTP_200_OK

    # 2. Use same token again (theft detection triggers!)
    refresh_resp_2 = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert refresh_resp_2.status_code == status.HTTP_401_UNAUTHORIZED
    assert "token reuse detected" in refresh_resp_2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_refresh_token_expired(client: AsyncClient, db, security: SecurityManager):
    # Generate expired refresh token
    import uuid
    user_id = "some-user-id"
    # We must insert user first to satisfy FK or just insert token. Let's insert user first.
    await db.execute(
        "INSERT INTO users (id, username, password_hash, role, is_active, must_change_password, created_at, updated_at) "
        "VALUES (?, 'temp_user', 'no-hash', 'viewer', 1, 0, ?, ?)",
        (user_id, time.time(), time.time())
    )
    await db.commit()

    # Generate token using security manager directly (but with expired time)
    # We temporarily set _jwt_refresh_token_ttl to negative value
    original_ttl = security._jwt_refresh_token_ttl
    security._jwt_refresh_token_ttl = -10
    token, family_id = security.create_refresh_token(user_id=user_id)
    security._jwt_refresh_token_ttl = original_ttl

    # Store it in DB
    token_hash = security.hash_refresh_token(token)
    await db.execute(
        "INSERT INTO refresh_tokens (id, user_id, token_hash, family_id, issued_at, expires_at, revoked) "
        "VALUES (?, ?, ?, ?, ?, ?, 0)",
        (str(uuid.uuid4()), user_id, token_hash, family_id, time.time() - 20, time.time() - 10)
    )
    await db.commit()

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": token}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "expired" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_logout(client: AsyncClient, db, security: SecurityManager):
    # Login to get token
    login_resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"}
    )
    refresh_token = login_resp.json()["refresh_token"]
    token_hash = security.hash_refresh_token(refresh_token)

    # Invalidate via logout
    logout_resp = await client.post(
        "/api/auth/logout",
        json={"refresh_token": refresh_token}
    )
    assert logout_resp.status_code == status.HTTP_204_NO_CONTENT

    # Check revoked in DB
    async with db.execute("SELECT revoked FROM refresh_tokens WHERE token_hash = ?", (token_hash,)) as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row["revoked"] == 1


@pytest.mark.asyncio
async def test_change_password_success(client: AsyncClient, db, security: SecurityManager):
    # Login to get access token
    login_resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"}
    )
    access_token = login_resp.json()["access_token"]
    refresh_token = login_resp.json()["refresh_token"]

    # Change password
    headers = {"Authorization": f"Bearer {access_token}"}
    response = await client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"old_password": "admin", "new_password": "newadminpassword"}
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verify password hash updated in DB and must_change_password set to 0
    async with db.execute("SELECT password_hash, must_change_password FROM users WHERE username = 'admin'") as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert security.verify_password("newadminpassword", row["password_hash"])
        assert row["must_change_password"] == 0

    # Verify refresh tokens revoked
    token_hash = security.hash_refresh_token(refresh_token)
    async with db.execute("SELECT revoked FROM refresh_tokens WHERE token_hash = ?", (token_hash,)) as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row["revoked"] == 1


@pytest.mark.asyncio
async def test_change_password_invalid_old(client: AsyncClient, db):
    # Login to get access token
    login_resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"}
    )
    access_token = login_resp.json()["access_token"]

    # Change password with wrong old password
    headers = {"Authorization": f"Bearer {access_token}"}
    response = await client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"old_password": "wrongoldpassword", "new_password": "newadminpassword"}
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "invalid old password" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, db):
    # 1. Unauthorized
    unauth_resp = await client.get("/api/auth/me")
    assert unauth_resp.status_code == status.HTTP_401_UNAUTHORIZED

    # Set must_change_password to 0 for admin
    await db.execute("UPDATE users SET must_change_password = 0 WHERE username = 'admin'")
    await db.commit()

    # 2. Login to get token
    login_resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"}
    )
    access_token = login_resp.json()["access_token"]

    # 3. Authorized request
    headers = {"Authorization": f"Bearer {access_token}"}
    response = await client.get("/api/auth/me", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "user_id" in data
    assert data["username"] == "admin"
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_login_password_verify_exception(client: AsyncClient, security: SecurityManager):
    # Mock SecurityManager.verify_password to raise an exception
    import unittest.mock as mock
    with mock.patch.object(security, "verify_password", side_effect=Exception("verification error")):
        response = await client.post(
            "/api/auth/login",
            json={"username": "nonexistent", "password": "anypassword"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "invalid credentials" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_refresh_token_not_in_db(client: AsyncClient, security: SecurityManager):
    # Generate a structurally valid refresh token but don't insert it to DB
    token, _ = security.create_refresh_token(user_id="user-1")
    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": token}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "invalid refresh token" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_refresh_token_expired_in_db(client: AsyncClient, db, security: SecurityManager):
    # Generate a token that's valid in JWT, but expired in DB
    user_id = "user-exp-db"
    await db.execute(
        "INSERT INTO users (id, username, password_hash, role, is_active, must_change_password, created_at, updated_at) "
        "VALUES (?, 'user-exp-db', 'no-hash', 'viewer', 1, 0, ?, ?)",
        (user_id, time.time(), time.time())
    )
    await db.commit()

    token, family_id = security.create_refresh_token(user_id=user_id)
    token_hash = security.hash_refresh_token(token)

    # Insert into DB with past expiration
    import uuid
    await db.execute(
        "INSERT INTO refresh_tokens (id, user_id, token_hash, family_id, issued_at, expires_at, revoked) "
        "VALUES (?, ?, ?, ?, ?, ?, 0)",
        (str(uuid.uuid4()), user_id, token_hash, family_id, time.time() - 20, time.time() - 10)
    )
    await db.commit()

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": token}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "refresh token expired" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_refresh_token_user_not_found_or_inactive(client: AsyncClient, db, security: SecurityManager):
    # Case 1: User does not exist in token sub, but token must reference a valid user in DB to satisfy FK
    dummy_user_id = "dummy-user-id"
    await db.execute(
        "INSERT INTO users (id, username, password_hash, role, is_active, must_change_password, created_at, updated_at) "
        "VALUES (?, 'dummy-user-1', 'no-hash', 'viewer', 1, 0, ?, ?)",
        (dummy_user_id, time.time(), time.time())
    )
    user_id = "nonexistent-user-id"
    token, family_id = security.create_refresh_token(user_id=user_id)
    token_hash = security.hash_refresh_token(token)

    import uuid
    await db.execute(
        "INSERT INTO refresh_tokens (id, user_id, token_hash, family_id, issued_at, expires_at, revoked) "
        "VALUES (?, ?, ?, ?, ?, ?, 0)",
        (str(uuid.uuid4()), dummy_user_id, token_hash, family_id, time.time(), time.time() + 3600)
    )
    await db.commit()

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": token}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "user not found or deactivated" in response.json()["detail"].lower()

    # Case 2: User exists but is inactive
    user_id_2 = "inactive-user-id"
    await db.execute(
        "INSERT INTO users (id, username, password_hash, role, is_active, must_change_password, created_at, updated_at) "
        "VALUES (?, 'inactive-user-2', 'no-hash', 'viewer', 0, 0, ?, ?)",
        (user_id_2, time.time(), time.time())
    )
    token2, family_id2 = security.create_refresh_token(user_id=user_id_2)
    token_hash2 = security.hash_refresh_token(token2)
    await db.execute(
        "INSERT INTO refresh_tokens (id, user_id, token_hash, family_id, issued_at, expires_at, revoked) "
        "VALUES (?, ?, ?, ?, ?, ?, 0)",
        (str(uuid.uuid4()), user_id_2, token_hash2, family_id2, time.time(), time.time() + 3600)
    )
    await db.commit()

    response2 = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": token2}
    )
    assert response2.status_code == status.HTTP_401_UNAUTHORIZED
    assert "user not found or deactivated" in response2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_logout_with_invalid_token(client: AsyncClient):
    response = await client.post(
        "/api/auth/logout",
        json={"refresh_token": "invalid_token_string"}
    )
    # The endpoint should handle the verification exception, log "unknown", and revoke/complete successfully
    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_change_password_user_not_found(client: AsyncClient, security: SecurityManager):
    # Create access token for user ID that does not exist in DB
    access_token = security.create_access_token("nonexistent-user-id-123", "ghost", "viewer")
    headers = {"Authorization": f"Bearer {access_token}"}
    response = await client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"old_password": "any", "new_password": "newadminpassword"}
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "user not found" in response.json()["detail"].lower()
