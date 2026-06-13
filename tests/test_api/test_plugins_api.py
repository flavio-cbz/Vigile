import json
import os
import shutil

import pytest
from fastapi import status
from httpx import AsyncClient

from master.api import deps
from master.config import settings
from master.core.plugin_manager import plugin_manager
from master.core.security_manager import SecurityManager
from master.main import app


@pytest.fixture
def auth_headers(security: SecurityManager):
    def _make(role: str = "admin"):
        token = security.create_access_token("test-user", "test_user", role)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
async def client(db):
    from httpx import ASGITransport, AsyncClient

    app.dependency_overrides[deps.get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(deps.get_db, None)


@pytest.fixture(autouse=True)
def clear_rate_limiter():
    from master.core.rate_limiter import rate_limiter

    rate_limiter._buckets.clear()


@pytest.fixture(autouse=True)
def setup_temp_plugins_dir(tmp_path):
    # Backup original plugins dir setting
    old_plugins_dir = settings.plugins_dir
    temp_dir = tmp_path / "plugins"
    temp_dir.mkdir()
    settings.plugins_dir = str(temp_dir)
    try:
        import master.api.admin

        master.api.admin.settings.plugins_dir = str(temp_dir)
    except Exception:
        pass

    # Copy default plugins to temp dir so they are available
    shutil.copy("master/plugins/metrics_plugin.py", temp_dir / "metrics.py")
    shutil.copy("master/plugins/systemd_plugin.py", temp_dir / "systemd.py")
    shutil.copy("master/plugins/docker_plugin.py", temp_dir / "docker.py")

    # Reset plugin_manager in-memory lists
    plugin_manager._loaded_plugins.clear()
    plugin_manager._hooks.clear()
    plugin_manager.load_plugins_from_dir(str(temp_dir))

    yield temp_dir

    # Restore settings
    settings.plugins_dir = old_plugins_dir
    try:
        import master.api.admin

        master.api.admin.settings.plugins_dir = old_plugins_dir
    except Exception:
        pass


@pytest.mark.asyncio
async def test_list_plugins_auth_roles(client: AsyncClient, auth_headers):
    # Admin -> Success
    res = await client.get("/api/admin/plugins", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert isinstance(data, dict)
    assert "loaded_plugins" in data
    assert "hooks" in data
    plugins_list = data["plugins"]
    assert len(plugins_list) >= 3
    plugin_ids = [p["id"] for p in plugins_list]
    assert "metrics" in plugin_ids
    assert "systemd" in plugin_ids
    assert "docker" in plugin_ids

    # Operator -> Success
    res = await client.get("/api/admin/plugins", headers=auth_headers("operator"))
    assert res.status_code == status.HTTP_200_OK

    # Viewer -> Forbidden
    res = await client.get("/api/admin/plugins", headers=auth_headers("viewer"))
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # Unauthenticated -> Unauthorized
    res = await client.get("/api/admin/plugins")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_configure_plugin(client: AsyncClient, auth_headers):
    # Configure systemd
    new_config = {"monitored_services": "ssh,nginx", "allow_restart_all": True}
    res = await client.post(
        "/api/admin/plugins/systemd/config", headers=auth_headers("admin"), json=new_config
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["status"] == "success"

    # Get plugins list and verify config was saved
    res = await client.get("/api/admin/plugins", headers=auth_headers("admin"))
    data = res.json()["plugins"]
    systemd_plugin = next(p for p in data if p["id"] == "systemd")
    assert systemd_plugin["config"] == new_config


@pytest.mark.asyncio
async def test_toggle_plugin_state(client: AsyncClient, auth_headers):
    # Disable systemd
    res = await client.post("/api/admin/plugins/systemd/toggle", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK

    # Verify in list
    res = await client.get("/api/admin/plugins", headers=auth_headers("admin"))
    data = res.json()["plugins"]
    systemd_plugin = next(p for p in data if p["id"] == "systemd")
    assert systemd_plugin["enabled"] is False
    assert systemd_plugin["loaded"] is False

    # Enable systemd back
    res = await client.post("/api/admin/plugins/systemd/toggle", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK

    # Verify loaded again
    res = await client.get("/api/admin/plugins", headers=auth_headers("admin"))
    data = res.json()["plugins"]
    systemd_plugin = next(p for p in data if p["id"] == "systemd")
    assert systemd_plugin["enabled"] is True
    assert systemd_plugin["loaded"] is True


@pytest.mark.asyncio
async def test_upload_and_delete_plugin(client: AsyncClient, auth_headers, setup_temp_plugins_dir):
    # 1. Upload invalid python file -> syntax error
    bad_code = "def register(pm):\n    syntax error here!"
    files = {"file": ("bad_plugin.py", bad_code, "text/plain")}
    res = await client.post("/api/admin/plugins/upload", headers=auth_headers("admin"), files=files)
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "Erreur de syntaxe Python" in res.json()["detail"]

    # 2. Upload python file missing register() function
    no_register_code = "def some_helper(pm):\n    pass"
    files = {"file": ("no_reg_plugin.py", no_register_code, "text/plain")}
    res = await client.post("/api/admin/plugins/upload", headers=auth_headers("admin"), files=files)
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "le plugin doit définir une fonction 'register(pm)'" in res.json()["detail"]

    # 3. Upload valid plugin
    valid_code = """
def register(pm) -> None:
    pm.register("get_supported_actions", _actions, plugin_name="test_upload")

def _actions() -> list[str]:
    return ["TEST_ACTION"]

def get_config_schema() -> dict:
    return {
        "name": "Test Upload Plugin",
        "category": "Custom",
        "description": "A dynamic plugin for testing upload.",
        "schema": {
            "test_key": {"type": "string", "default": "default_val"}
        }
    }
"""
    files = {"file": ("test_upload.py", valid_code, "text/plain")}
    res = await client.post("/api/admin/plugins/upload", headers=auth_headers("admin"), files=files)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["status"] == "success"

    # Verify it is loaded and has correct metadata and hooks
    res = await client.get("/api/admin/plugins", headers=auth_headers("admin"))
    data = res.json()["plugins"]
    plugin = next(p for p in data if p["id"] == "test_upload")
    assert plugin["enabled"] is True
    assert plugin["loaded"] is True
    assert plugin["name"] == "Test Upload Plugin"
    assert plugin["category"] == "Custom"
    assert "get_supported_actions" in plugin["hooks"]

    # 4. Try to delete core plugin -> forbidden
    res = await client.delete("/api/admin/plugins/metrics", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "extensions intégrées" in res.json()["detail"]

    # 5. Delete uploaded plugin
    res = await client.delete("/api/admin/plugins/test_upload", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["status"] == "success"

    # Verify it is removed from list
    res = await client.get("/api/admin/plugins", headers=auth_headers("admin"))
    data = res.json()["plugins"]
    plugin_ids = [p["id"] for p in data]
    assert "test_upload" not in plugin_ids
    assert not os.path.exists(os.path.join(settings.plugins_dir, "test_upload.py"))
