from __future__ import annotations

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
async def setup_temp_plugins_dir(tmp_path):
    import sys
    saved_modules = dict(sys.modules)

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

    (temp_dir / "metrics.py").write_text(
        'def register(pm):\n'
        '    pm.register("get_supported_actions", lambda: ["GET_STATS"], plugin_name="metrics")\n'
        '    pm.register("normalize_status_report", lambda raw_report: raw_report, plugin_name="metrics")\n'
        '    pm.register("on_status_report", lambda node_id, snapshot, db=None: None, plugin_name="metrics")\n'
        '\n'
        'def get_config_schema():\n'
        '    return {"name": "Metrics", "category": "Monitoring", "schema": {}}\n'
    )
    (temp_dir / "systemd.py").write_text(
        'def register(pm):\n'
        '    pm.register("get_supported_actions", lambda: ["LIST_SERVICES", "RESTART_SERVICE"], plugin_name="systemd")\n'
        '\n'
        'def get_config_schema():\n'
        '    return {"name": "Systemd", "category": "System", "schema": {}}\n'
    )
    (temp_dir / "docker.py").write_text(
        'def register(pm):\n'
        '    pm.register("get_supported_actions", lambda: ["LIST_CONTAINERS", "RESTART_CONTAINER"], plugin_name="docker")\n'
        '\n'
        'def get_config_schema():\n'
        '    return {"name": "Docker", "category": "Virtualization", "schema": {}}\n'
    )

    # Fully reset plugin_manager singleton so tests are order-independent.
    # A prior test's app lifespan (e.g. test_main) may have left _engine set and
    # _sandbox=True on the shared singleton, which makes `loaded_plugins` delegate
    # to the engine (unaware of these fixture loads) and makes load_plugin use the
    # subprocess branch. Reset to a clean standalone state before each test.
    plugin_manager._engine = None
    plugin_manager._sandbox = False
    plugin_manager._enabled_plugins = None
    plugin_manager._wrappers = {}
    plugin_manager._draining_plugins = set()
    plugin_manager._active_calls = {}
    plugin_manager._loaded_plugins.clear()
    plugin_manager._hooks.clear()
    await plugin_manager.load_plugins_from_dir(str(temp_dir))

    yield temp_dir

    # Restore settings and sys.modules
    settings.plugins_dir = old_plugins_dir
    try:
        import master.api.admin

        master.api.admin.settings.plugins_dir = old_plugins_dir
    except Exception:
        pass

    for k in list(sys.modules.keys()):
        if k not in saved_modules:
            del sys.modules[k]
    sys.modules.update(saved_modules)



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
    valid_code = """from __future__ import annotations

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


@pytest.mark.asyncio
async def test_toggle_plugin_stem_canonicalization(client: AsyncClient, auth_headers, setup_temp_plugins_dir):
    # Create docker_plugin.py stem in temp dir
    (setup_temp_plugins_dir / "docker_plugin.py").write_text(
        'def register(pm):\n'
        '    pm.register("get_supported_actions", lambda: ["LIST_CONTAINERS"], plugin_name="docker")\n'
    )
    await plugin_manager.load_plugin("docker_plugin", str(setup_temp_plugins_dir))

    # Toggle using 'docker_plugin'
    res = await client.post("/api/admin/plugins/docker_plugin/toggle", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK

    # Check list plugins - canonical ID 'docker' should have no 'Plugin not loaded' error when disabled
    res = await client.get("/api/admin/plugins", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK
    data = res.json()["plugins"]
    docker_plugin = next(p for p in data if p["id"] == "docker")
    assert docker_plugin["enabled"] is False
    assert docker_plugin["loaded"] is False
    assert docker_plugin["error"] is None


@pytest.mark.asyncio
async def test_package_directory_plugin_toggle_and_delete(
    client: AsyncClient, auth_headers, setup_temp_plugins_dir
):
    # 1. Create a package directory plugin (no root .py)
    pkg_dir = setup_temp_plugins_dir / "test_pkg_plugin"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    manifest_content = json.dumps({
        "id": "test_pkg_plugin",
        "name": "Test Package Plugin",
        "version": "1.0.0",
        "description": "Package directory test",
        "trusted": True
    })
    (pkg_dir / "manifest.json").write_text(manifest_content)
    (pkg_dir / "__init__.py").write_text(
        'def register(pm):\n'
        '    pm.register("get_supported_actions", lambda: ["PKG_ACTION"], plugin_name="test_pkg_plugin")\n'
    )

    await plugin_manager.load_plugin("test_pkg_plugin", str(setup_temp_plugins_dir))

    # 2. Configure package plugin
    res = await client.post(
        "/api/admin/plugins/test_pkg_plugin/config",
        headers=auth_headers("admin"),
        json={"setting1": "val1"},
    )
    assert res.status_code == status.HTTP_200_OK

    # 3. Toggle off package plugin
    res = await client.post("/api/admin/plugins/test_pkg_plugin/toggle", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["status"] == "success"

    # 4. Toggle back on
    res = await client.post("/api/admin/plugins/test_pkg_plugin/toggle", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK

    # 5. Delete package plugin
    res = await client.delete("/api/admin/plugins/test_pkg_plugin", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["status"] == "success"

    # 6. Verify directory removed from disk
    assert not pkg_dir.exists()


