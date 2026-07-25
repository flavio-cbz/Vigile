from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from master.api.deps import get_current_user, require_role


@pytest.mark.asyncio
async def test_require_role_calls_get_current_user_once() -> None:
    """
    BE-08: require_role() must NOT re-decode the JWT.
    It must reuse the result from get_current_user() via FastAPI's
    Depends caching. This test verifies that get_current_user is
    called exactly once when both CurrentUser and require_role are used.
    """
    call_count = 0

    async def mock_get_current_user() -> dict:
        nonlocal call_count
        call_count += 1
        return {"role": "admin", "sub": "test-user", "username": "test_user"}

    app = FastAPI()

    @app.get("/test-dedup")
    async def test_endpoint(
        current_user: dict = Depends(get_current_user),
        _role: dict = Depends(require_role("admin")),
    ):
        return {"ok": True, "user": current_user}

    app.dependency_overrides[get_current_user] = mock_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/test-dedup")
        assert response.status_code == 200
        assert call_count == 1, (
            f"get_current_user was called {call_count} times, expected 1. "
            "require_role must reuse the cached dependency result."
        )
        data = response.json()
        assert data["ok"] is True
        assert data["user"]["role"] == "admin"
