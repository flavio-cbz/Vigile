import time
import unittest.mock as mock

import pytest
from fastapi import status
from httpx import AsyncClient

from master.api import deps
from master.core.node_manager import NodeState, node_manager
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
    # Set master_url on app state to ensure generate-join endpoint doesn't fail
    app.state.master_url = "http://test"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(deps.get_db, None)


@pytest.fixture(autouse=True)
def clear_rate_limiter():
    from master.core.rate_limiter import rate_limiter

    rate_limiter._buckets.clear()


@pytest.mark.asyncio
async def test_generate_join_token_success(client: AsyncClient, db, auth_headers):
    # Admin is required to generate join token
    response = await client.post(
        "/api/nodes/generate-join",
        headers=auth_headers("admin"),
        json={"name": "test-node", "ip_prefix": "192.168.1."},
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert "node_id" in data
    assert "token" in data
    assert data["expires_in"] > 0
    assert "curl" in data["curl_command"]

    # Verify node created in PENDING state in DB
    node_id = data["node_id"]
    async with db.execute("SELECT state, ip_prefix FROM nodes WHERE id = ?", (node_id,)) as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row["state"] == "PENDING"
        assert row["ip_prefix"] == "192.168.1."

    # Verify join token stored in DB
    token_hash = SecurityManager.join_token_hash(None, data["token"])  # Static method
    async with db.execute(
        "SELECT consumed, expires_at FROM join_tokens WHERE token_hash = ?", (token_hash,)
    ) as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row["consumed"] == 0
        assert row["expires_at"] > time.time()


@pytest.mark.asyncio
async def test_generate_join_token_insufficient_permissions(client: AsyncClient, auth_headers):
    # Operator cannot generate join token
    response = await client.post(
        "/api/nodes/generate-join", headers=auth_headers("operator"), json={"name": "test-node"}
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_get_kickstart_script(client: AsyncClient):
    response = await client.get("/api/nodes/kickstart.sh")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("text/x-sh")
    assert "Vigile — Worker Kickstart Script" in response.text


@pytest.mark.asyncio
async def test_list_nodes(client: AsyncClient, db, auth_headers):
    # Insert a couple of nodes
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('n-1', 'node-1', 'PENDING', ?, ?)",
        (time.time(), time.time()),
    )
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('n-2', 'node-2', 'CONNECTED', ?, ?)",
        (time.time(), time.time()),
    )
    await db.commit()

    # Operator role can list nodes
    response = await client.get("/api/nodes", headers=auth_headers("operator"))
    assert response.status_code == status.HTTP_200_OK
    nodes = response.json()
    assert len(nodes) >= 2

    # Filtering by state
    response_filtered = await client.get(
        "/api/nodes?state=CONNECTED", headers=auth_headers("operator")
    )
    assert response_filtered.status_code == status.HTTP_200_OK
    nodes_filtered = response_filtered.json()
    assert all(n["state"] == "CONNECTED" for n in nodes_filtered)

    # Viewer role can also list nodes? Wait!
    # list_nodes has claims: require_role("operator", "admin")
    # So viewer should be forbidden (403)
    response_viewer = await client.get("/api/nodes", headers=auth_headers("viewer"))
    assert response_viewer.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_get_node(client: AsyncClient, db, auth_headers):
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('n-3', 'node-3', 'PENDING', ?, ?)",
        (time.time(), time.time()),
    )
    await db.commit()

    response = await client.get("/api/nodes/n-3", headers=auth_headers("operator"))
    assert response.status_code == status.HTTP_200_OK
    node = response.json()
    assert node["id"] == "n-3"
    assert node["name"] == "node-3"

    # Non-existent node -> 404
    response_404 = await client.get("/api/nodes/nonexistent", headers=auth_headers("operator"))
    assert response_404.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_revoke_node(client: AsyncClient, db, auth_headers):
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('n-4', 'node-4', 'CONNECTED', ?, ?)",
        (time.time(), time.time()),
    )
    await db.commit()

    # Admin is required to revoke
    response = await client.delete("/api/nodes/n-4", headers=auth_headers("admin"))
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verify node state is now REVOKED
    async with db.execute("SELECT state FROM nodes WHERE id = 'n-4'") as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row["state"] == "REVOKED"

    # Revoking an already revoked node -> 409
    response_409 = await client.delete("/api/nodes/n-4", headers=auth_headers("admin"))
    assert response_409.status_code == status.HTTP_409_CONFLICT

    # Non-existent node -> 404
    response_404 = await client.delete("/api/nodes/nonexistent", headers=auth_headers("admin"))
    assert response_404.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_get_node_stats(client: AsyncClient, db, auth_headers):
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('n-5', 'node-5', 'CONNECTED', ?, ?)",
        (time.time(), time.time()),
    )
    await db.execute(
        "INSERT INTO metrics_snapshots (id, node_id, collected_at, created_at, cpu_percent, mem_total_bytes, mem_used_bytes, mem_percent, swap_total_bytes, swap_used_bytes, disk_total_bytes, disk_used_bytes, disk_percent, uptime_seconds) "
        "VALUES ('s-1', 'n-5', ?, ?, 15.5, 8000, 4000, 50.0, 1000, 100, 20000, 5000, 25.0, 500.0)",
        (time.time(), time.time()),
    )
    await db.commit()

    response = await client.get("/api/nodes/n-5/stats?limit=5", headers=auth_headers("operator"))
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["node_id"] == "n-5"
    assert len(data["snapshots"]) == 1
    assert data["snapshots"][0]["cpu_percent"] == 15.5

    # Non-existent node -> 404
    response_404 = await client.get(
        "/api/nodes/nonexistent/stats", headers=auth_headers("operator")
    )
    assert response_404.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_verify_chain(client: AsyncClient, auth_headers):
    # Admin required
    response = await client.get("/api/nodes/verify-chain", headers=auth_headers("admin"))
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert (
        "verified" in data
        or "valid" in data
        or "report" in data
        or "success" in data
        or "corrupted" in data
    )

    # Operator not allowed
    response_op = await client.get("/api/nodes/verify-chain", headers=auth_headers("operator"))
    assert response_op.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_get_node_logs(client: AsyncClient, db, auth_headers):
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('n-6', 'node-6', 'CONNECTED', ?, ?)",
        (time.time(), time.time()),
    )
    await db.commit()

    # Mock send_intent
    orig_send_intent = node_manager.send_intent

    async def mock_send_intent(node_id, intent, timeout=15.0):
        assert node_id == "n-6"
        assert intent["action"] == "READ_LOGS"
        assert intent["params"]["lines"] == 50
        return {"success": True, "output": "line 1\nline 2"}

    node_manager.send_intent = mock_send_intent
    try:
        response = await client.get(
            "/api/nodes/n-6/logs?lines=50", headers=auth_headers("operator")
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["node_id"] == "n-6"
        assert "line 1" in data["output"]
    finally:
        node_manager.send_intent = orig_send_intent


@pytest.mark.asyncio
async def test_get_node_logs_errors(client: AsyncClient, db, auth_headers):
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('n-7', 'node-7', 'CONNECTED', ?, ?)",
        (time.time(), time.time()),
    )
    await db.commit()

    orig_send_intent = node_manager.send_intent

    # 1. Test TimeoutError
    async def mock_send_intent_timeout(node_id, intent, timeout=15.0):
        raise TimeoutError("Timeout")

    node_manager.send_intent = mock_send_intent_timeout
    try:
        response = await client.get("/api/nodes/n-7/logs", headers=auth_headers("operator"))
        assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT
    finally:
        node_manager.send_intent = orig_send_intent

    # 2. Test RuntimeError (Service Unavailable)
    async def mock_send_intent_runtime(node_id, intent, timeout=15.0):
        raise RuntimeError("Worker not connected")

    node_manager.send_intent = mock_send_intent_runtime
    try:
        response = await client.get("/api/nodes/n-7/logs", headers=auth_headers("operator"))
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    finally:
        node_manager.send_intent = orig_send_intent


@pytest.mark.asyncio
async def test_get_bulk_status(client: AsyncClient, db, auth_headers, security: SecurityManager):
    # Insert node and metrics snapshot
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at, cached_containers_json) "
        "VALUES ('n-bulk', 'node-bulk', 'CONNECTED', ?, ?, ?)",
        (time.time(), time.time(), '["c1", "c2"]'),
    )
    await db.execute(
        "INSERT INTO metrics_snapshots (id, node_id, collected_at, created_at, cpu_percent, mem_total_bytes, mem_used_bytes, mem_percent, swap_total_bytes, swap_used_bytes, disk_total_bytes, disk_used_bytes, disk_percent, uptime_seconds) "
        "VALUES ('s-bulk', 'n-bulk', ?, ?, 25.5, 8000, 4000, 50.0, 1000, 100, 20000, 5000, 25.0, 600.0)",
        (time.time(), time.time()),
    )
    await db.commit()

    # 1. Test as operator (success)
    response = await client.get("/api/nodes/bulk/status", headers=auth_headers("operator"))
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "statuses" in data
    assert "n-bulk" in data["statuses"]
    status_node = data["statuses"]["n-bulk"]
    assert status_node["cpu"] == 26
    assert status_node["mem"] == 50
    assert status_node["disk"] == 25
    assert status_node["uptime"] == 600.0
    assert status_node["containers_count"] == 2

    # 2. Test as viewer (403 forbidden)
    response_viewer = await client.get("/api/nodes/bulk/status", headers=auth_headers("viewer"))
    assert response_viewer.status_code == status.HTTP_403_FORBIDDEN

    # 3. Test demo mode
    # Inject a demo user token
    token = security.create_access_token("demo-user", "guest", "operator")
    headers = {"Authorization": f"Bearer {token}"}
    response_demo = await client.get("/api/nodes/bulk/status", headers=headers)
    assert response_demo.status_code == status.HTTP_200_OK
    data_demo = response_demo.json()
    assert "statuses" in data_demo
    assert "demo-node-01" in data_demo["statuses"]
