import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from master.api import deps
from master.core.rate_limiter import rate_limiter
from master.main import app


@pytest.fixture
async def client(db):
    app.dependency_overrides[deps.get_db] = lambda: db
    app.state.master_url = "http://localhost:8000"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(deps.get_db, None)


@pytest.fixture(autouse=True)
def clear_rate_limiter():
    rate_limiter._buckets.clear()


@pytest.mark.asyncio
async def test_login_rate_limit_exceeded(client: AsyncClient):
    """6 rapid login attempts → 6th returns 429 (limit=5/min)."""
    payload = {"username": "admin", "password": "admin"}
    for i in range(5):
        response = await client.post("/api/auth/login", json=payload)
        assert response.status_code == status.HTTP_200_OK, (
            f"Attempt {i + 1} should succeed, got {response.status_code}"
        )

    response = await client.post("/api/auth/login", json=payload)
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "Too many requests" in response.json()["detail"]


@pytest.mark.asyncio
async def test_kickstart_rate_limit_exceeded(client: AsyncClient):
    """11 rapid GET /api/nodes/kickstart.sh → 11th returns 429 (limit=10/min)."""
    for i in range(10):
        response = await client.get("/api/nodes/kickstart.sh")
        assert response.status_code == status.HTTP_200_OK, (
            f"Attempt {i + 1} should succeed, got {response.status_code}"
        )

    response = await client.get("/api/nodes/kickstart.sh")
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "Too many requests" in response.json()["detail"]


@pytest.mark.asyncio
async def test_global_middleware_backstop(client: AsyncClient):
    """Global middleware blocks requests above its limit (tested at reduced max=5)."""
    original = rate_limiter.max_requests
    rate_limiter.max_requests = 5
    try:
        for i in range(5):
            response = await client.get("/health")
            assert response.status_code == status.HTTP_200_OK, (
                f"Attempt {i + 1} should succeed, got {response.status_code}"
            )

        response = await client.get("/health")
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.json()["error"] == "Too many requests"
    finally:
        rate_limiter.max_requests = original


@pytest.mark.asyncio
async def test_per_endpoint_and_global_buckets_are_independent(client: AsyncClient):
    """Dep-buckets (prefixed 'dep:') don't count toward global middleware."""
    # Exhaust the login dep bucket (5 req)
    for _ in range(5):
        resp = await client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin"}
        )
        assert resp.status_code == status.HTTP_200_OK

    # 6th login → 429 from dependency
    resp = await client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin"}
    )
    assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    # /health should still work — its global bucket is separate (different key)
    resp = await client.get("/health")
    assert resp.status_code == status.HTTP_200_OK
