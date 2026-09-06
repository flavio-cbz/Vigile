from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from master.api import deps
from master.main import app


pytestmark = pytest.mark.asyncio


# ────────────────────────── Fixtures ──────────────────────────

@pytest.fixture
def auth_headers(security):
    def _make(role: str = "admin"):
        token = security.create_access_token("test-user", "test_user", role)
        return {"Authorization": f"Bearer {token}"}
    return _make


@pytest.fixture
async def client(db):
    app.dependency_overrides[deps.get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(deps.get_db, None)


@pytest.fixture(autouse=True)
def clear_rate_limiter():
    from master.core.rate_limiter import rate_limiter
    rate_limiter._buckets.clear()


@pytest.fixture
def kill_switch_engine():
    from master.core.plugin_manager import plugin_engine
    original = dict(plugin_engine._kill_switch)
    plugin_engine._kill_switch.clear()
    yield plugin_engine
    plugin_engine._kill_switch.clear()
    plugin_engine._kill_switch.update(original)


# ────────────────────────── Async Mock DB ──────────────────────────

class FakeCursor:
    """aiosqlite-like cursor: awaitable AND async context manager."""

    def __init__(self):
        self.rowcount = 0
        self.lastrowid = None

    async def fetchone(self):
        return None

    async def fetchall(self):
        return []

    async def close(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    def __await__(self):
        async def _resolve():
            return self
        return _resolve().__await__()


class FakeDB:
    """Minimal aiosqlite-compatible DB mock via _explicit_db property override."""

    def __init__(self):
        self._connection = MagicMock()
        self.in_transaction = False

    def execute(self, sql, params=()):
        return FakeCursor()

    async def commit(self):
        pass


@pytest.fixture
def mock_engine_db(kill_switch_engine):
    """Attach a FakeDB to the engine via _explicit_db."""
    kill_switch_engine._explicit_db = FakeDB()
    yield kill_switch_engine._explicit_db
    kill_switch_engine._explicit_db = None


@pytest.fixture
def patched_engine(kill_switch_engine, mock_engine_db):
    """Patch external deps of disable_plugin / enable_plugin and force _get_engine."""
    with patch.object(kill_switch_engine, "unload_plugin", new_callable=AsyncMock), \
         patch.object(kill_switch_engine, "_swap_registry", new_callable=AsyncMock), \
         patch("master.core.event_bus.event_bus.publish", new_callable=AsyncMock), \
         patch("master.core.audit.log_action", new_callable=AsyncMock), \
         patch("master.api.plugins._get_engine", return_value=kill_switch_engine):
        yield kill_switch_engine


# ────────────────────────── Tests ──────────────────────────

async def test_kill_switch_soft_mode(client, auth_headers, patched_engine):
    engine = patched_engine
    headers = auth_headers("admin")

    response = await client.post(
        "/api/plugins/test-plugin/disable",
        json={"hard": False, "reason": "maintenance"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disabled"
    assert body["mode"] == "maintenance"
    assert engine.is_kill_switched("test-plugin")
    entry = engine._kill_switch["test-plugin"]
    assert entry["hard"] is False
    assert entry["reason"] == "maintenance"


async def test_kill_switch_hard_mode_requires_reason(client, auth_headers, patched_engine, mock_engine_db):
    headers = auth_headers("admin")

    response = await client.post(
        "/api/plugins/test-plugin/disable",
        json={"hard": True, "reason": None},
        headers=headers,
    )

    assert response.status_code == 422
    assert "reason" in response.json()["detail"].lower()


async def test_kill_switch_hard_mode(client, auth_headers, patched_engine):
    engine = patched_engine
    headers = auth_headers("admin")

    response = await client.post(
        "/api/plugins/test-plugin/disable",
        json={"hard": True, "reason": "security compromise suspected"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disabled"
    assert body["mode"] == "hard"
    assert engine.is_kill_switched("test-plugin")
    assert engine._kill_switch["test-plugin"]["hard"] is True
    assert engine._kill_switch["test-plugin"]["reason"] == "security compromise suspected"


async def test_kill_switch_rejects_non_admin(client, auth_headers, patched_engine):
    headers = auth_headers("viewer")
    response = await client.post(
        "/api/plugins/test-plugin/disable",
        json={"hard": False, "reason": "maintenance"},
        headers=headers,
    )
    assert response.status_code == 403


async def test_enable_plugin_reverses_kill_switch(client, auth_headers, kill_switch_engine, mock_engine_db):
    engine = kill_switch_engine
    headers = auth_headers("admin")

    engine._kill_switch["test-plugin"] = {
        "hard": True, "disabled_at": 1234567890.0,
        "reason": "compromised", "user_id": "admin",
    }

    with patch.object(engine, "load_plugin", new_callable=AsyncMock), \
         patch.object(engine, "_swap_registry", new_callable=AsyncMock), \
         patch("master.core.event_bus.event_bus.publish", new_callable=AsyncMock), \
         patch("master.core.audit.log_action", new_callable=AsyncMock), \
         patch("master.api.plugins._get_engine", return_value=engine):
        response = await client.post(
            "/api/plugins/test-plugin/enable",
            headers=headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "enabled"
    assert not engine.is_kill_switched("test-plugin")


async def test_enable_non_kill_switched_returns_404(client, auth_headers, kill_switch_engine, mock_engine_db):
    headers = auth_headers("admin")

    response = await client.post(
        "/api/plugins/nonexistent/enable",
        headers=headers,
    )

    assert response.status_code == 404


async def test_kill_switch_blocks_dispatch(kill_switch_engine, db):
    from master.core.command_registry import CommandEntry
    from master.api.plugins import _dispatch_one
    from master.core.node_manager import NodeManager

    engine = kill_switch_engine
    engine._kill_switch["test-plugin"] = {
        "hard": True,
        "disabled_at": 1234567890.0,
        "reason": "compromised",
        "user_id": "admin",
    }

    entry = CommandEntry(
        name="test.command", roles=("viewer",), mutation=False,
        plugin_id="test-plugin", method="GET", path_template="/test",
        resource_contract="test-plugin",
    )
    handler = MagicMock()
    dispatch = {"test.command": (entry, handler)}

    nm = NodeManager()
    claims = {"role": "admin", "sub": "test-user"}

    class FakeSub:
        command = "test.command"
        params = {}

    result = await _dispatch_one(
        request=MagicMock(),
        db=db,
        nm=nm,
        claims=claims,
        dispatch=dispatch,
        sub=FakeSub(),
    )

    assert result["status"] == 403
    assert "kill switch" in result["error"]
