import asyncio
import json

import pytest
from httpx import AsyncClient

from master.api import deps
from master.core.node_manager import NodeState, node_manager
from master.core.security_manager import SecurityManager
from master.main import app

SERVICES_JSON = json.dumps(
    [
        {"name": "ssh.service", "state": "active", "status": "running"},
        {"name": "nginx.service", "state": "active", "status": "running"},
        {"name": "docker.service", "state": "active", "status": "running"},
    ]
)

STATUS_JSON = json.dumps(
    {
        "service": "nginx.service",
        "active": "active",
        "enabled": "enabled",
    }
)

CONTAINERS_JSON = json.dumps(
    [
        {
            "id": "a1b2c3d4e5f6",
            "name": "web",
            "image": "nginx:latest",
            "state": "running",
            "ports": ["0.0.0.0:80->80"],
        },
        {
            "id": "f6e5d4c3b2a1",
            "name": "db",
            "image": "postgres:15",
            "state": "running",
            "ports": ["5432"],
        },
    ]
)


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


async def mock_list_services(node_id, intent, *, timeout=30.0):
    return {"intent_id": "s-1", "success": True, "output": SERVICES_JSON, "error": ""}


async def mock_status_service(node_id, intent, *, timeout=30.0):
    return {"intent_id": "s-2", "success": True, "output": STATUS_JSON, "error": ""}


async def mock_restart_service(node_id, intent, *, timeout=30.0):
    return {
        "intent_id": "s-3",
        "success": True,
        "output": "Service nginx.service restarted",
        "error": "",
    }


async def mock_list_containers(node_id, intent, *, timeout=30.0):
    return {"intent_id": "c-1", "success": True, "output": CONTAINERS_JSON, "error": ""}


async def mock_restart_container(node_id, intent, *, timeout=30.0):
    return {
        "intent_id": "c-2",
        "success": True,
        "output": "Container a1b2c3d4e5f6 restarted",
        "error": "",
    }


async def mock_intent_fail(node_id, intent, *, timeout=30.0):
    return {
        "intent_id": "x-1",
        "success": False,
        "output": "",
        "error": f"action {intent['action']} failed",
    }


async def mock_intent_not_connected(node_id, intent, *, timeout=30.0):
    raise RuntimeError(f"Node {node_id} is not connected")


async def mock_intent_timeout(node_id, intent, *, timeout=30.0):
    raise TimeoutError("Worker did not respond")


async def _setup_node(db, name: str = "test-svc") -> str:
    node_id = await node_manager.create_node(db, name=name)
    await node_manager.transition_state(db, node_id, NodeState.ENROLLING)
    await node_manager.transition_state(db, node_id, NodeState.UNCONFIGURED)
    await node_manager.transition_state(db, node_id, NodeState.CONNECTED)
    return node_id


@pytest.mark.asyncio
async def test_list_services_success(db, client, auth_headers):
    node_id = await _setup_node(db, "svc-list")
    orig = node_manager.send_intent
    node_manager.send_intent = mock_list_services
    try:
        resp = await client.get(f"/api/nodes/{node_id}/services", headers=auth_headers("admin"))
        assert resp.status_code == 200
        d = resp.json()
        assert d["node_id"] == node_id
        assert len(d["services"]) == 3
        assert d["services"][0].get("name") == "ssh.service"
        assert d["services"][0].get("state") == "active"
    finally:
        node_manager.send_intent = orig


@pytest.mark.asyncio
async def test_list_services_not_found(client, auth_headers):
    resp = await client.get("/api/nodes/nonexistent/services", headers=auth_headers("admin"))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_services_not_connected(db, client, auth_headers):
    node_id = await node_manager.create_node(db, name="svc-offline")
    orig = node_manager.send_intent
    node_manager.send_intent = mock_intent_not_connected
    try:
        resp = await client.get(f"/api/nodes/{node_id}/services", headers=auth_headers("admin"))
        assert resp.status_code == 503
    finally:
        node_manager.send_intent = orig


@pytest.mark.asyncio
async def test_list_services_timeout(db, client, auth_headers):
    node_id = await _setup_node(db, "svc-timeout")
    orig = node_manager.send_intent
    node_manager.send_intent = mock_intent_timeout
    try:
        resp = await client.get(f"/api/nodes/{node_id}/services", headers=auth_headers("admin"))
        assert resp.status_code == 504
    finally:
        node_manager.send_intent = orig


@pytest.mark.asyncio
async def test_service_status_success(db, client, auth_headers):
    node_id = await _setup_node(db, "svc-status")
    orig = node_manager.send_intent
    node_manager.send_intent = mock_status_service
    try:
        resp = await client.get(
            f"/api/nodes/{node_id}/services/nginx.service", headers=auth_headers("admin")
        )
        assert resp.status_code == 200
        d = resp.json()
        assert d["node_id"] == node_id
        assert d["service"] == "nginx.service"
        assert d["active"] == "active"
        assert d["enabled"] == "enabled"
    finally:
        node_manager.send_intent = orig


@pytest.mark.asyncio
async def test_service_status_fail(db, client, auth_headers):
    node_id = await _setup_node(db, "svc-status-fail")
    orig = node_manager.send_intent
    node_manager.send_intent = mock_intent_fail
    try:
        resp = await client.get(
            f"/api/nodes/{node_id}/services/unknown.service", headers=auth_headers("admin")
        )
        assert resp.status_code == 200
        d = resp.json()
        assert d.get("active") == "unknown"
        assert d.get("enabled") == "unknown"
    finally:
        node_manager.send_intent = orig


@pytest.mark.asyncio
async def test_restart_service_success(db, client, auth_headers):
    node_id = await _setup_node(db, "svc-restart")
    orig = node_manager.send_intent
    node_manager.send_intent = mock_restart_service
    try:
        resp = await client.post(
            f"/api/nodes/{node_id}/services/nginx.service/restart", headers=auth_headers("admin")
        )
        assert resp.status_code == 200
        d = resp.json()
        assert d["node_id"] == node_id
        assert d["service"] == "nginx.service"
        assert "restarted" in d.get("output", "")
        assert d.get("error") is None
    finally:
        node_manager.send_intent = orig


@pytest.mark.asyncio
async def test_restart_service_admin_required(db, client, auth_headers):
    node_id = await _setup_node(db, "svc-restart-auth")
    orig = node_manager.send_intent
    node_manager.send_intent = mock_restart_service
    try:
        resp = await client.post(
            f"/api/nodes/{node_id}/services/nginx.service/restart", headers=auth_headers("operator")
        )
        assert resp.status_code == 403
    finally:
        node_manager.send_intent = orig


@pytest.mark.asyncio
async def test_list_containers_success(db, client, auth_headers):
    node_id = await _setup_node(db, "c-list")
    orig = node_manager.send_intent
    node_manager.send_intent = mock_list_containers
    try:
        resp = await client.get(f"/api/nodes/{node_id}/containers", headers=auth_headers("admin"))
        assert resp.status_code == 200
        d = resp.json()
        assert d["node_id"] == node_id
        assert len(d["containers"]) == 2
        assert d["containers"][0].get("id") == "a1b2c3d4e5f6"
        assert d["containers"][0].get("name") == "web"
        assert d["containers"][0].get("state") == "running"
    finally:
        node_manager.send_intent = orig


@pytest.mark.asyncio
async def test_list_containers_not_found(client, auth_headers):
    resp = await client.get("/api/nodes/nonexistent/containers", headers=auth_headers("admin"))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_restart_container_success(db, client, auth_headers):
    node_id = await _setup_node(db, "c-restart")
    orig = node_manager.send_intent
    node_manager.send_intent = mock_restart_container
    try:
        resp = await client.post(
            f"/api/nodes/{node_id}/containers/a1b2c3d4e5f6/restart", headers=auth_headers("admin")
        )
        assert resp.status_code == 200
        d = resp.json()
        assert d["node_id"] == node_id
        assert d.get("container_id") == "a1b2c3d4e5f6"
        assert "restarted" in d.get("output", "")
        assert d.get("error") is None
    finally:
        node_manager.send_intent = orig


@pytest.mark.asyncio
async def test_unauthorized(client):
    resp = await client.get("/api/nodes/some-id/services")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_viewer_forbidden(client, auth_headers):
    resp = await client.get("/api/nodes/some-id/services", headers=auth_headers("viewer"))
    assert resp.status_code == 403
