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

    # Anti-phantom assertion: no `nodes` row at generate-join (see migration 006).
    # The row is only created by the Worker enrollment handshake.
    node_id = data["node_id"]
    async with db.execute("SELECT state FROM nodes WHERE id = ?", (node_id,)) as cursor:
        row = await cursor.fetchone()
        assert row is None, "Phantom node row created before Worker enrollment"

    # The join_token IS persisted, with the right node_id and ip_prefix.
    token_hash = SecurityManager.join_token_hash(None, data["token"])  # Static method
    async with db.execute(
        "SELECT consumed, expires_at, node_id FROM join_tokens WHERE token_hash = ?", (token_hash,)
    ) as cursor:
        token_row = await cursor.fetchone()
    assert token_row is not None
    assert token_row["consumed"] == 0
    assert token_row["node_id"] == node_id

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
async def test_generate_join_no_phantom_node(client: AsyncClient, db, auth_headers):
    """Generate-join must NOT create a `nodes` row before the Worker enrolls."""
    response = await client.post(
        "/api/nodes/generate-join",
        headers=auth_headers("admin"),
        json={"name": "phantom-test", "ip_prefix": "10.0.0."},
    )
    assert response.status_code == status.HTTP_201_CREATED
    node_id = response.json()["node_id"]

    async with db.execute("SELECT COUNT(*) FROM nodes WHERE id = ?", (node_id,)) as cursor:
        count = (await cursor.fetchone())[0]
    assert count == 0, "Phantom node persisted before Worker enrollment"


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
async def test_get_kickstart_ps1_script(client: AsyncClient):
    response = await client.get("/api/nodes/kickstart.ps1")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("text/plain")
    assert "Windows PowerShell Kickstart Script for Vigile Worker Node" in response.text


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
async def test_delete_node(client: AsyncClient, db, auth_headers):
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('n-4', 'node-4', 'CONNECTED', ?, ?)",
        (time.time(), time.time()),
    )
    await db.commit()

    # Admin is required to delete
    response = await client.delete("/api/nodes/n-4", headers=auth_headers("admin"))
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verify node row is gone (hard delete)
    async with db.execute("SELECT id FROM nodes WHERE id = 'n-4'") as cursor:
        row = await cursor.fetchone()
        assert row is None

    # Deleting an already-deleted node -> 404 (idempotent in semantic)
    response_404 = await client.delete("/api/nodes/n-4", headers=auth_headers("admin"))
    assert response_404.status_code == status.HTTP_404_NOT_FOUND

    # Non-existent node -> 404
    response_404b = await client.delete("/api/nodes/nonexistent", headers=auth_headers("admin"))
    assert response_404b.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_delete_node_cascades_to_dependent_rows(client: AsyncClient, db, auth_headers):
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('n-casc', 'casc-node', 'CONNECTED', ?, ?)",
        (time.time(), time.time()),
    )
    await db.execute(
        "INSERT INTO worker_tokens (id, node_id, token_hash, issued_at, rotation_due, expires_at, revoked) "
        "VALUES ('wt-casc', 'n-casc', 'hash-casc', ?, ?, ?, 0)",
        (time.time(), time.time() + 3600, time.time() + 7200),
    )
    await db.execute(
        "INSERT INTO metrics_snapshots (id, node_id, collected_at, created_at, cpu_percent, mem_total_bytes, mem_used_bytes, mem_percent, swap_total_bytes, swap_used_bytes, disk_total_bytes, disk_used_bytes, disk_percent, uptime_seconds) "
        "VALUES ('s-casc', 'n-casc', ?, ?, 10.0, 1000, 500, 50.0, 0, 0, 1000, 100, 10.0, 100.0)",
        (time.time(), time.time()),
    )
    await db.commit()

    response = await client.delete("/api/nodes/n-casc", headers=auth_headers("admin"))
    assert response.status_code == status.HTTP_204_NO_CONTENT

    async with db.execute("SELECT id FROM worker_tokens WHERE node_id = 'n-casc'") as cursor:
        assert await cursor.fetchone() is None
    async with db.execute("SELECT id FROM metrics_snapshots WHERE node_id = 'n-casc'") as cursor:
        assert await cursor.fetchone() is None


@pytest.mark.asyncio
async def test_delete_node_keeps_audit_entry(client: AsyncClient, db, auth_headers):
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('n-aud', 'audit-node', 'CONNECTED', ?, ?)",
        (time.time(), time.time()),
    )
    await db.commit()

    await client.delete("/api/nodes/n-aud", headers=auth_headers("admin"))

    async with db.execute(
        "SELECT action FROM audit_log WHERE node_id = 'n-aud' AND action = 'NODE_DELETED'"
    ) as cursor:
        row = await cursor.fetchone()
        assert row is not None


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


# ---------------------------------------------------------------------------
# New endpoints: PATCH, configure, regenerate-token, DELETE ENROLLING guard,
# NodeResponse group/disabled/enrolled_recently, generate-join with group
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_rename(client: AsyncClient, db, auth_headers):
    """Operator renames a node — returns 200 and persists the new name."""
    now = time.time()
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('n-patch-1', 'old-name', 'CONNECTED', ?, ?)",
        (now, now),
    )
    await db.commit()

    response = await client.patch(
        "/api/nodes/n-patch-1",
        headers=auth_headers("operator"),
        json={"name": "new-name"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == "n-patch-1"
    assert data["name"] == "new-name"

    async with db.execute("SELECT name FROM nodes WHERE id = 'n-patch-1'") as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row["name"] == "new-name"


@pytest.mark.asyncio
async def test_patch_disable_by_operator_is_403(client: AsyncClient, db, auth_headers):
    """Operator attempting to disable a node must get 403."""
    now = time.time()
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('n-patch-2', 'n2', 'CONNECTED', ?, ?)",
        (now, now),
    )
    await db.commit()

    response = await client.patch(
        "/api/nodes/n-patch-2",
        headers=auth_headers("operator"),
        json={"disabled": True},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN

    response_admin = await client.patch(
        "/api/nodes/n-patch-2",
        headers=auth_headers("admin"),
        json={"disabled": True},
    )
    assert response_admin.status_code == status.HTTP_200_OK
    data = response_admin.json()
    assert data["disabled"] is True
    assert data["state"] == "DISABLED"


@pytest.mark.asyncio
async def test_configure_unconfigured_to_connected(client: AsyncClient, db, auth_headers):
    """Full flow: PENDING -> UNCONFIGURED -> /configure -> CONNECTED."""
    now = time.time()
    node_id = "n-cfg-1"
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES (?, 'pending-name', 'UNCONFIGURED', ?, ?)",
        (node_id, now, now),
    )
    await db.commit()

    response = await client.post(
        f"/api/nodes/{node_id}/configure",
        headers=auth_headers("operator"),
        json={"name": "configured-name", "group": "production"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == node_id
    assert data["name"] == "configured-name"
    assert data["state"] == "CONNECTED"
    assert data["group"] == "production"

    async with db.execute(
        "SELECT state, name, node_group FROM nodes WHERE id = ?", (node_id,)
    ) as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row["state"] == "CONNECTED"
        assert row["name"] == "configured-name"
        assert row["node_group"] == "production"


@pytest.mark.asyncio
async def test_configure_wrong_state_is_409(client: AsyncClient, db, auth_headers):
    """Configure on a CONNECTED node must be rejected with 409."""
    now = time.time()
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('n-cfg-2', 'n2', 'CONNECTED', ?, ?)",
        (now, now),
    )
    await db.commit()

    response = await client.post(
        "/api/nodes/n-cfg-2/configure",
        headers=auth_headers("operator"),
        json={"name": "x", "group": None},
    )
    assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_regenerate_token_admin_only(client: AsyncClient, db, auth_headers):
    """Only admin can regenerate a JOIN_TOKEN; non-admin gets 403."""
    now = time.time()
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('n-reg-1', 'n1', 'PENDING', ?, ?)",
        (now, now),
    )
    await db.commit()

    response_op = await client.post(
        "/api/nodes/n-reg-1/regenerate-token",
        headers=auth_headers("operator"),
    )
    assert response_op.status_code == status.HTTP_403_FORBIDDEN

    response_admin = await client.post(
        "/api/nodes/n-reg-1/regenerate-token",
        headers=auth_headers("admin"),
    )
    assert response_admin.status_code == status.HTTP_201_CREATED
    data = response_admin.json()
    assert data["node_id"] == "n-reg-1"
    assert "token" in data
    assert "curl" in data["curl_command"]


@pytest.mark.asyncio
async def test_regenerate_token_already_enrolled_409(client: AsyncClient, db, auth_headers):
    """Regenerating on a CONNECTED node must be 409."""
    now = time.time()
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('n-reg-2', 'n2', 'CONNECTED', ?, ?)",
        (now, now),
    )
    await db.commit()

    response = await client.post(
        "/api/nodes/n-reg-2/regenerate-token",
        headers=auth_headers("admin"),
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "already enrolled" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_enrolling_succeeds(client: AsyncClient, db, auth_headers):
    """Deleting a node in ENROLLING state must succeed (hard delete is unconditional)."""
    now = time.time()
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('n-enr-1', 'n1', 'ENROLLING', ?, ?)",
        (now, now),
    )
    await db.commit()

    response = await client.delete(
        "/api/nodes/n-enr-1",
        headers=auth_headers("admin"),
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    async with db.execute("SELECT id FROM nodes WHERE id = 'n-enr-1'") as cursor:
        assert await cursor.fetchone() is None


@pytest.mark.asyncio
async def test_node_response_includes_group_disabled_enrolled_recently(
    client: AsyncClient, db, auth_headers
):
    """NodeResponse exposes group, disabled, enrolled_recently fields."""
    now = time.time()
    recent_ts = time.time() - 60
    await db.execute(
        "INSERT INTO nodes (id, name, state, node_group, disabled, enrolled_at, created_at, updated_at) "
        "VALUES ('n-resp-1', 'n1', 'CONNECTED', 'prod', 1, ?, ?, ?)",
        (recent_ts, now, now),
    )
    await db.commit()

    response = await client.get(
        "/api/nodes/n-resp-1",
        headers=auth_headers("operator"),
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["group"] == "prod"
    assert data["disabled"] is True
    assert data["enrolled_recently"] is True


@pytest.mark.asyncio
async def test_generate_join_with_group(client: AsyncClient, db, auth_headers):
    """generate-join accepts an optional `group`. It is carried in the JOIN_TOKEN
    payload and applied to the `nodes` row at enrollment time (anti-phantom)."""
    response = await client.post(
        "/api/nodes/generate-join",
        headers=auth_headers("admin"),
        json={"name": "grp-node", "group": "homelab"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    node_id = data["node_id"]

    # No `nodes` row at generate-join time (anti-phantom).
    async with db.execute("SELECT name FROM nodes WHERE id = ?", (node_id,)) as cursor:
        row = await cursor.fetchone()
    assert row is None

    # The `name` and `group` are embedded in the join_token payload.
    token_hash = SecurityManager.join_token_hash(None, data["token"])
    async with db.execute(
        "SELECT payload_b64 FROM join_tokens WHERE token_hash = ?", (token_hash,)
    ) as cursor:
        token_row = await cursor.fetchone()
    assert token_row is not None
    import base64
    import json as _json

    payload = _json.loads(base64.urlsafe_b64decode(token_row["payload_b64"] + "=="))
    assert payload["name"] == "grp-node"
    assert payload["group"] == "homelab"


@pytest.mark.asyncio
async def test_update_worker_success(client: AsyncClient, db, auth_headers):
    # Insert a node in connected state
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('n-update-1', 'n-update', 'CONNECTED', 1234567, 1234567)"
    )
    await db.commit()

    # Mock node manager's send_intent to return success
    with mock.patch.object(node_manager, "send_intent", return_value={"success": True, "output": "updated successfully"}) as mock_send:
        response = await client.post(
            "/api/nodes/n-update-1/update",
            headers=auth_headers("admin"),
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"success": True, "output": "updated successfully"}
        mock_send.assert_called_once_with(
            "n-update-1",
            {"action": "UPDATE_WORKER", "params": {}},
            timeout=30.0,
        )


@pytest.mark.asyncio
async def test_update_worker_requires_admin(client: AsyncClient, auth_headers):
    # Operator is not allowed
    response = await client.post(
        "/api/nodes/n-update-1/update",
        headers=auth_headers("operator"),
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
