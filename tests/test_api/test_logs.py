import pytest
import asyncio
from httpx import AsyncClient
from master.main import app
from master.api import deps
from master.core.node_manager import node_manager, NodeState
from master.core.security_manager import SecurityManager

@pytest.fixture
def auth_headers(security: SecurityManager):
    def _make(role: str = "admin"):
        token = security.create_access_token("test-user", "test_user", role)
        return {"Authorization": f"Bearer {token}"}
    return _make

@pytest.fixture
async def client(db):
    from httpx import AsyncClient, ASGITransport
    app.dependency_overrides[deps.get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(deps.get_db, None)

async def mock_send_intent_success(node_id, intent, *, timeout=30.0):
    return {
        "intent_id": "test-intent-001",
        "success": True,
        "output": "Jun  1 10:00:00 server sshd[1234]: Accepted publickey\nJun  1 10:00:05 server sshd[1235]: session opened",
        "error": "",
    }

async def mock_send_intent_fail(node_id, intent, *, timeout=30.0):
    return {
        "intent_id": "test-intent-002",
        "success": False,
        "output": "",
        "error": "permission denied",
    }

async def mock_send_intent_not_connected(node_id, intent, *, timeout=30.0):
    raise RuntimeError(f"Node {node_id} is not connected")

async def mock_send_intent_timeout(node_id, intent, *, timeout=30.0):
    raise TimeoutError("Worker did not respond in time")

async def _setup_node(db, name: str = "test-logs") -> str:
    """Create a CONNECTED node for testing."""
    node_id = await node_manager.create_node(db, name=name)
    await node_manager.transition_state(db, node_id, NodeState.ENROLLING)
    await node_manager.transition_state(db, node_id, NodeState.CONNECTED)
    return node_id

@pytest.mark.asyncio
async def test_logs_success_file(db, client, auth_headers):
    node_id = await _setup_node(db, "logs-file")
    original = node_manager.send_intent
    node_manager.send_intent = mock_send_intent_success
    try:
        resp = await client.get(
            f"/api/nodes/{node_id}/logs?path=/var/log/syslog&lines=10",
            headers=auth_headers("admin"),
        )
        assert resp.status_code == 200
        d = resp.json()
        assert d["node_id"] == node_id
        assert len(d["output"]) > 0
        assert d["lines"] == 10
        assert d["path"] == "/var/log/syslog"
        assert d["error"] is None
    finally:
        node_manager.send_intent = original

@pytest.mark.asyncio
async def test_logs_success_service(db, client, auth_headers):
    node_id = await _setup_node(db, "logs-svc")
    original = node_manager.send_intent
    node_manager.send_intent = mock_send_intent_success
    try:
        resp = await client.get(
            f"/api/nodes/{node_id}/logs?service=nginx&lines=20",
            headers=auth_headers("admin"),
        )
        assert resp.status_code == 200
        d = resp.json()
        assert d["node_id"] == node_id
        assert d["service"] == "nginx"
        assert d["path"] is None
    finally:
        node_manager.send_intent = original

@pytest.mark.asyncio
async def test_logs_default_path(db, client, auth_headers):
    node_id = await _setup_node(db, "logs-default")
    original = node_manager.send_intent
    node_manager.send_intent = mock_send_intent_success
    try:
        resp = await client.get(
            f"/api/nodes/{node_id}/logs",
            headers=auth_headers("admin"),
        )
        assert resp.status_code == 200
        d = resp.json()
        assert d["path"] == "/var/log/syslog"
        assert d["lines"] == 50
    finally:
        node_manager.send_intent = original

@pytest.mark.asyncio
async def test_logs_node_not_found(client, auth_headers):
    resp = await client.get(
        "/api/nodes/nonexistent-id/logs",
        headers=auth_headers("admin"),
    )
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_logs_node_not_connected(db, client, auth_headers):
    node_id = await node_manager.create_node(db, name="logs-offline")
    original = node_manager.send_intent
    node_manager.send_intent = mock_send_intent_not_connected
    try:
        resp = await client.get(
            f"/api/nodes/{node_id}/logs",
            headers=auth_headers("admin"),
        )
        assert resp.status_code == 503
        assert "not connected" in resp.json()["detail"].lower()
    finally:
        node_manager.send_intent = original

@pytest.mark.asyncio
async def test_logs_worker_timeout(db, client, auth_headers):
    node_id = await _setup_node(db, "logs-timeout")
    original = node_manager.send_intent
    node_manager.send_intent = mock_send_intent_timeout
    try:
        resp = await client.get(
            f"/api/nodes/{node_id}/logs",
            headers=auth_headers("admin"),
        )
        assert resp.status_code == 504
    finally:
        node_manager.send_intent = original

@pytest.mark.asyncio
async def test_logs_worker_error(db, client, auth_headers):
    node_id = await _setup_node(db, "logs-error")
    original = node_manager.send_intent
    node_manager.send_intent = mock_send_intent_fail
    try:
        resp = await client.get(
            f"/api/nodes/{node_id}/logs?path=/var/log/auth.log",
            headers=auth_headers("admin"),
        )
        assert resp.status_code == 200
        d = resp.json()
        assert d["error"] == "permission denied"
        assert d["output"] == ""
    finally:
        node_manager.send_intent = original

@pytest.mark.asyncio
async def test_logs_unauthorized(client):
    resp = await client.get("/api/nodes/some-id/logs")
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_logs_viewer_forbidden(client, auth_headers):
    resp = await client.get(
        "/api/nodes/some-id/logs",
        headers=auth_headers("viewer"),
    )
    assert resp.status_code == 403
