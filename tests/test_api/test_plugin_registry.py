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
def setup_temp_plugins_dir(tmp_path):
    old_plugins_dir = settings.plugins_dir
    temp_dir = tmp_path / "plugins"
    temp_dir.mkdir()
    settings.plugins_dir = str(temp_dir)
    try:
        import master.api.admin
        master.api.admin.settings.plugins_dir = str(temp_dir)
    except Exception:
        pass

    plugin_manager._loaded_plugins.clear()
    plugin_manager._hooks.clear()

    yield temp_dir

    settings.plugins_dir = old_plugins_dir
    try:
        import master.api.admin
        master.api.admin.settings.plugins_dir = old_plugins_dir
    except Exception:
        pass


@pytest.mark.asyncio
async def test_get_registry_fallback_on_network_error(client: AsyncClient, auth_headers, monkeypatch):
    import httpx
    
    original_get = httpx.AsyncClient.get

    async def mock_get(self, url, *args, **kwargs):
        if "registry.json" in str(url) or "raw.githubusercontent.com" in str(url):
            raise httpx.RequestError("Network down")
        return await original_get(self, url, *args, **kwargs)
        
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = await client.get("/api/admin/plugins/registry", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert "plugins" in data
    assert len(data["plugins"]) >= 3
    plugin_ids = [p["id"] for p in data["plugins"]]
    assert "discord_alert" in plugin_ids
    assert "slack_alert" in plugin_ids


@pytest.mark.asyncio
async def test_get_registry_success_mock(client: AsyncClient, auth_headers, monkeypatch):
    import httpx
    
    mock_data = {
        "plugins": [
            {
                "id": "my_test_plugin",
                "name": "My Test Plugin",
                "description": "A registry test plugin.",
                "author": "Tester",
                "version": "1.2.3",
                "download_url": "http://test-url/my_test_plugin.py",
            }
        ]
    }

    class MockResponse:
        status_code = 200
        def json(self):
            return mock_data

    original_get = httpx.AsyncClient.get

    async def mock_get(self, url, *args, **kwargs):
        if "registry.json" in str(url) or "raw.githubusercontent.com" in str(url):
            return MockResponse()
        return await original_get(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = await client.get("/api/admin/plugins/registry", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert len(data["plugins"]) == 1
    assert data["plugins"][0]["id"] == "my_test_plugin"


@pytest.mark.asyncio
async def test_install_plugin_success(client: AsyncClient, auth_headers, monkeypatch, db):
    import httpx

    # 1. Mock registry fetch
    registry_data = {
        "plugins": [
            {
                "id": "test_install",
                "name": "Test Install",
                "description": "Test Install Plugin",
                "author": "Tester",
                "version": "1.0.0",
                "download_url": "http://test-url/test_install.py",
            }
        ]
    }

    # 2. Mock target source code (valid python with register() function)
    valid_source = """
def register(pm):
    pass
"""

    class MockResponse:
        def __init__(self, url):
            self.url = url
            if "registry.json" in url or "raw.githubusercontent.com" in url:
                self.status_code = 200
            else:
                self.status_code = 200
                self.text = valid_source

        def json(self):
            return registry_data

    original_get = httpx.AsyncClient.get

    async def mock_get(self, url, *args, **kwargs):
        url_str = str(url)
        if "registry.json" in url_str or "raw.githubusercontent.com" in url_str or "test_install.py" in url_str:
            return MockResponse(url_str)
        return await original_get(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = await client.post("/api/admin/plugins/registry/test_install/install", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["status"] == "success"

    # Verify file is written to settings.plugins_dir
    file_path = os.path.join(settings.plugins_dir, "test_install.py")
    assert os.path.isfile(file_path)

    # Verify database insertion
    async with db.execute("SELECT enabled FROM plugin_configs WHERE plugin_id = ?", ("test_install",)) as cur:
        row = await cur.fetchone()
        assert row is not None
        assert row[0] == 1

    # Verify audit log contains UPLOAD_PLUGIN
    async with db.execute("SELECT action, details_json FROM audit_log WHERE action = ?", ("UPLOAD_PLUGIN",)) as cur:
        row = await cur.fetchone()
        assert row is not None
        details = json.loads(row[1])
        assert details["plugin_id"] == "test_install"


@pytest.mark.asyncio
async def test_install_plugin_invalid_ast(client: AsyncClient, auth_headers, monkeypatch):
    import httpx

    registry_data = {
        "plugins": [
            {
                "id": "invalid_ast",
                "name": "Invalid AST",
                "description": "Missing register contract",
                "author": "Tester",
                "version": "1.0.0",
                "download_url": "http://test-url/invalid_ast.py",
            }
        ]
    }

    # Python code without register() function
    invalid_source = "print('Hello world')"

    class MockResponse:
        def __init__(self, url):
            self.url = url
            if "registry.json" in url or "raw.githubusercontent.com" in url:
                self.status_code = 200
            else:
                self.status_code = 200
                self.text = invalid_source

        def json(self):
            return registry_data

    original_get = httpx.AsyncClient.get

    async def mock_get(self, url, *args, **kwargs):
        url_str = str(url)
        if "registry.json" in url_str or "raw.githubusercontent.com" in url_str or "invalid_ast.py" in url_str:
            return MockResponse(url_str)
        return await original_get(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = await client.post("/api/admin/plugins/registry/invalid_ast/install", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "register" in res.json()["detail"]


@pytest.mark.asyncio
async def test_install_plugin_demo_mode_blocked(client: AsyncClient, auth_headers, security):
    # Set jwt payload to look like demo using the security manager fixture
    token = security.create_access_token("guest", "guest", "admin")
    demo_headers = {"Authorization": f"Bearer {token}"}

    res = await client.post("/api/admin/plugins/registry/test_install/install", headers=demo_headers)
    assert res.status_code == status.HTTP_403_FORBIDDEN
