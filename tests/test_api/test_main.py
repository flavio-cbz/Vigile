from __future__ import annotations

import importlib
import json
import os
import sys
import time
from pathlib import Path

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient

# Set environment variables before reloading the app and settings to trigger all code paths
os.environ["CORS_ORIGINS"] = "*"
os.environ["ENFORCE_HTTPS"] = "true"

import master.config
import master.middleware
import master.main

importlib.reload(master.config)
importlib.reload(master.middleware)
importlib.reload(master.main)

from master.config import settings
from master.core.security_manager import SecurityManager
from master.db.database import reset_db
from master.main import app

from starlette.routing import Route

# Register temporary test routes to verify exception handling logic
# Must be inserted directly at the front of the app.router.routes list to avoid being shadowed by "/" mount
def raise_dict(request):
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": "dict_error"})

def raise_str(request):
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="str_error")

app.router.routes.insert(0, Route("/_test/exc-dict", raise_dict, methods=["GET"]))
app.router.routes.insert(0, Route("/_test/exc-str", raise_str, methods=["GET"]))



@pytest.fixture
def auth_headers(security: SecurityManager):
    def _make(role: str = "admin"):
        token = security.create_access_token("test-user", "test_user", role)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.mark.asyncio
async def test_main_lifespan(temp_dir, monkeypatch):
    # Ensure database is clean
    await reset_db()

    db_path = os.path.join(temp_dir, "lifespan_test.db")
    key_path = os.path.join(temp_dir, "master_ed25519.key")

    import master.main
    import master.config
    import master.lifespan
    monkeypatch.setattr(master.main.settings, "database_path", db_path)
    monkeypatch.setattr(master.main.settings, "master_key_path", key_path)
    monkeypatch.setattr(master.main.settings, "plugins_dir", temp_dir)
    monkeypatch.setattr(master.config.settings, "database_path", db_path)
    monkeypatch.setattr(master.config.settings, "master_key_path", key_path)
    monkeypatch.setattr(master.config.settings, "plugins_dir", temp_dir)
    monkeypatch.setattr(master.lifespan.settings, "database_path", db_path)
    monkeypatch.setattr(master.lifespan.settings, "master_key_path", key_path)
    monkeypatch.setattr(master.lifespan.settings, "plugins_dir", temp_dir)

    # Temporarily reset the security manager singleton to allow the lifespan to initialize it
    import master.core.security_manager as sm

    old_security = sm._security_instance
    sm._security_instance = None

    try:
        # Run the lifespan context manager directly to guarantee startup/shutdown are executed
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                # Request health check which will verify the lifespan started and set state
                response = await c.get("/health")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["status"] == "ok"
                assert data["uptime_seconds"] >= 0

                # Test admin connections endpoint
                token = sm.get_security_instance().create_access_token(
                    "demo-user", "demo-user", "admin"
                )
                headers = {"Authorization": f"Bearer {token}"}
                response = await c.get("/api/admin/nodes/connections", headers=headers)
                assert response.status_code == status.HTTP_200_OK
                assert response.json()["connected_nodes"] == []

                # Test admin plugins endpoint
                response = await c.get("/api/admin/plugins", headers=headers)
                assert response.status_code == status.HTTP_200_OK
                assert "loaded_plugins" in response.json()
    finally:
        sm._security_instance = old_security


@pytest.mark.asyncio
async def test_custom_http_exception_handlers(db):
    transport = ASGITransport(app=app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp_dict = await c.get("/_test/exc-dict")
        assert resp_dict.status_code == status.HTTP_400_BAD_REQUEST
        assert resp_dict.json() == {"error": "dict_error"}

        resp_str = await c.get("/_test/exc-str")
        assert resp_str.status_code == status.HTTP_400_BAD_REQUEST
        assert resp_str.json() == {"detail": "str_error"}


@pytest.mark.asyncio
async def test_cors_echo_origin_middleware(db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Request with Origin header should echo it back
        response = await c.get("/health", headers={"Origin": "https://example.com"})
        assert response.headers.get("Access-Control-Allow-Origin") == "https://example.com"


@pytest.mark.asyncio
async def test_https_enforcement_middleware(db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # 1. Non-HTTPS requests should be rejected if X-Forwarded-Proto is not https
        response = await c.get("/health", headers={"X-Forwarded-Proto": "http"})
        assert response.status_code == status.HTTP_426_UPGRADE_REQUIRED
        assert response.json()["error"] == "HTTPS required"

        # 2. X-Forwarded-Proto is https -> success
        response = await c.get("/health", headers={"X-Forwarded-Proto": "https"})
        assert response.status_code == status.HTTP_200_OK

        # 3. Request path starts with /ws -> bypassed even with http proto
        response = await c.get("/ws/worker/join", headers={"X-Forwarded-Proto": "http"})
        assert response.status_code != status.HTTP_426_UPGRADE_REQUIRED


@pytest.mark.asyncio
async def test_admin_audit_verify_endpoint(db, auth_headers):
    # This requires the db connection initialized via db fixture
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get("/api/admin/audit-verify", headers=auth_headers("admin"))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["valid"] is True
        assert "total_entries" in data


@pytest.mark.asyncio
async def test_admin_settings_endpoint(db, auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # 1. Admin user -> success
        response = await c.get("/api/admin/settings", headers=auth_headers("admin"))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "master_url" in data
        assert "server_secret_key" in data
        assert data["server_secret_key"] == "••••••••"

        # 2. Operator user -> 200 OK
        response2 = await c.get("/api/admin/settings", headers=auth_headers("operator"))
        assert response2.status_code == status.HTTP_200_OK

        # 3. Viewer user -> 403 Forbidden
        response3 = await c.get("/api/admin/settings", headers=auth_headers("viewer"))
        assert response3.status_code == status.HTTP_403_FORBIDDEN

        # 4. Unauthenticated -> 401 Unauthorized
        response4 = await c.get("/api/admin/settings")
        assert response4.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_update_llm_settings(db, auth_headers, temp_dir, monkeypatch):
    """Test updating LLM settings via POST /api/admin/settings/llm."""
    import master.main
    import master.config
    db_path = os.path.join(temp_dir, "override_main_test.db")
    monkeypatch.setattr(master.main.settings, "database_path", db_path)
    monkeypatch.setattr(master.config.settings, "database_path", db_path)

    # Clean up static overrides before test
    override_file = Path(db_path).parent / "settings_override.json"
    if override_file.exists():
        override_file.unlink()

    from master.core.security_manager import get_security_instance

    security = get_security_instance()
    demo_token = security.create_access_token("demo-user", "guest", "admin")
    demo_headers = {"Authorization": f"Bearer {demo_token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # 1. Non-admin -> 403
        payload = {
            "llm_base_url": "http://updated-from-api",
            "llm_api_key": "some-key",
            "llm_model": "some-model",
        }
        res1 = await c.post(
            "/api/admin/settings/llm", json=payload, headers=auth_headers("operator")
        )
        assert res1.status_code == status.HTTP_403_FORBIDDEN

        # 2. Demo user -> 403
        res2 = await c.post("/api/admin/settings/llm", json=payload, headers=demo_headers)
        assert res2.status_code == status.HTTP_403_FORBIDDEN

        # 3. Admin user -> 200 (Success)
        res3 = await c.post("/api/admin/settings/llm", json=payload, headers=auth_headers("admin"))
        assert res3.status_code == status.HTTP_200_OK
        data = res3.json()
        assert data["llm_base_url"] == "http://updated-from-api"
        assert data["llm_model"] == "some-model"
        assert data["llm_api_key"] == "••••••••"

        # Verify settings_override.json was written to disk
        assert override_file.exists()
        with override_file.open("r", encoding="utf-8") as f:
            saved_override = json.load(f)
        assert saved_override["llm_base_url"] == "http://updated-from-api"
        assert saved_override["llm_api_key"] == "some-key"
        assert saved_override["llm_model"] == "some-model"

        # 4. Check masked key override: passing masked API key preserves the saved one
        payload_masked = {
            "llm_base_url": "http://updated-from-api-2",
            "llm_api_key": "••••••••",
            "llm_model": "some-model-2",
        }
        res4 = await c.post(
            "/api/admin/settings/llm", json=payload_masked, headers=auth_headers("admin")
        )
        assert res4.status_code == status.HTTP_200_OK

        # Verify JSON file has original key
        with override_file.open("r", encoding="utf-8") as f:
            saved_override2 = json.load(f)
        assert saved_override2["llm_base_url"] == "http://updated-from-api-2"
        assert saved_override2["llm_api_key"] == "some-key"  # kept original key
        assert saved_override2["llm_model"] == "some-model-2"


@pytest.mark.asyncio
async def test_test_llm_settings(db, auth_headers):
    """Test testing LLM settings via POST /api/admin/settings/llm/test."""
    from master.core.security_manager import get_security_instance

    security = get_security_instance()
    demo_token = security.create_access_token("demo-user", "guest", "admin")
    demo_headers = {"Authorization": f"Bearer {demo_token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        payload = {
            "llm_base_url": "http://updated-from-api",
            "llm_api_key": "some-key",
            "llm_model": "some-model",
        }

        # 1. Non-admin -> 403
        res1 = await c.post(
            "/api/admin/settings/llm/test", json=payload, headers=auth_headers("operator")
        )
        assert res1.status_code == status.HTTP_403_FORBIDDEN

        # 2. Demo user -> 403
        res2 = await c.post("/api/admin/settings/llm/test", json=payload, headers=demo_headers)
        assert res2.status_code == status.HTTP_403_FORBIDDEN

        # 3. Success (Admin) with mocked complete()
        import unittest.mock as mock

        mock_complete = mock.AsyncMock(return_value={"choices": [{"message": {"content": "pong"}}]})
        with mock.patch("master.core.llm_client.LLMClient.complete", mock_complete):
            res3 = await c.post(
                "/api/admin/settings/llm/test", json=payload, headers=auth_headers("admin")
            )
            assert res3.status_code == status.HTTP_200_OK
            assert res3.json()["status"] == "success"


@pytest.mark.asyncio
async def test_llm_client_lazy_recreation():
    """Test N3 level: lazy recreation of LLMClient on settings update."""
    from master.api.deps import get_llm_client, reset_llm_clients
    from master.config import settings

    # Reset cached clients first to clear any cached client from previous tests
    reset_llm_clients()

    # 1. Access initial client
    settings.apply_overrides(
        base_url="http://initial-base-url", api_key="key", model="initial-model"
    )
    client1 = get_llm_client()
    assert client1.base_url == "http://initial-base-url"

    # 2. Apply new settings and reset clients
    settings.apply_overrides(base_url="http://new-base-url", api_key="key", model="new-model")
    reset_llm_clients()

    # 3. Access client again - must be a new instance with the new settings
    client2 = get_llm_client()
    assert client2 is not client1
    assert client2.base_url == "http://new-base-url"
