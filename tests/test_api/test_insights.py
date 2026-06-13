import time
import unittest.mock as mock

import pytest
from fastapi import status
from httpx import AsyncClient

from master.api import deps
from master.core.insights import DiagnosticReport, HeavyProcessConfig, NodeProfile
from master.core.node_manager import node_manager
from master.core.security_manager import SecurityManager
from master.main import app


@pytest.fixture
def auth_headers(security: SecurityManager):
    def _make(role: str = "admin", demo: bool = False):
        # In demo mode, the user ID is DEMO_USER_ID and username is DEMO_USERNAME
        sub = "demo-user-id" if demo else "test-user"
        username = "guest" if demo else "test_user"
        token = security.create_access_token(sub, username, role)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
async def client(db):
    from httpx import ASGITransport, AsyncClient

    app.dependency_overrides[deps.get_db] = lambda: db
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
async def test_get_node_insights_demo(client: AsyncClient, auth_headers):
    # Viewer cannot access insights, Operator or Admin is required
    response = await client.get(
        "/api/nodes/demo-node-99/insights", headers=auth_headers("viewer", demo=True)
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN

    # Operator role can access
    response = await client.get(
        "/api/nodes/demo-node-99/insights", headers=auth_headers("operator", demo=True)
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["node_id"] == "demo-node-99"
    assert "insights" in data
    assert len(data["insights"]) == 3
    assert data["insights"][0]["type"] == "disk"
    assert "1 semaine et 3j" in data["insights"][0]["headline"]
    assert data["insights"][1]["type"] == "cpu"
    assert "Transcodage Plex" in data["insights"][1]["headline"]


@pytest.mark.asyncio
async def test_get_node_insights_real(client: AsyncClient, db, auth_headers):
    # Insert node into DB
    node_id = "test-node-1"
    now = time.time()
    await db.execute(
        """
        INSERT INTO nodes (id, name, hostname, state, insight_profile, insight_profile_generated_at, created_at, updated_at)
        VALUES (?, 'Test Node 1', 'test-host', 'CONNECTED', ?, ?, ?, ?)
        """,
        (
            node_id,
            '{"node_id": "test-node-1", "known_heavy_processes": [], "baseline_ram_percent": 70.0, "context_label": "Serveur test"}',
            now,
            now,
            now,
        ),
    )
    # Insert a metrics snapshot
    await db.execute(
        """
        INSERT INTO metrics_snapshots (id, node_id, collected_at, created_at, cpu_percent, mem_total_bytes, mem_used_bytes, mem_percent, swap_total_bytes, swap_used_bytes, disk_total_bytes, disk_used_bytes, disk_percent, uptime_seconds)
        VALUES ('snap-1', ?, ?, ?, 15.0, 8589934592, 4294967296, 50.0, 0, 0, 107374182400, 21474836480, 20.0, 1000)
        """,
        (node_id, now, now),
    )
    await db.commit()

    response = await client.get(f"/api/nodes/{node_id}/insights", headers=auth_headers("operator"))
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["node_id"] == node_id
    assert len(data["insights"]) == 3  # Disk, CPU, RAM
    assert data["insights"][0]["type"] == "disk"
    assert data["insights"][0]["headline"] == "Disque stable"


@pytest.mark.asyncio
async def test_regenerate_profile_demo(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/nodes/demo-node-99/profile/regenerate", headers=auth_headers("operator", demo=True)
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["node_id"] == "demo-node-99"
    assert data["context_label"] == "Serveur homelab"


@pytest.mark.asyncio
async def test_regenerate_profile_real(client: AsyncClient, db, auth_headers):
    node_id = "test-node-2"
    now = time.time()
    await db.execute(
        "INSERT INTO nodes (id, name, hostname, state, created_at, updated_at) "
        "VALUES (?, 'Test Node 2', 'test-host-2', 'CONNECTED', ?, ?)",
        (node_id, now, now),
    )
    await db.commit()

    response = await client.post(
        f"/api/nodes/{node_id}/profile/regenerate", headers=auth_headers("operator")
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["node_id"] == node_id
    assert "baseline_ram_percent" in data

    # Check that profile was updated in DB
    async with db.execute("SELECT insight_profile FROM nodes WHERE id = ?", (node_id,)) as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row["insight_profile"] is not None


@pytest.mark.asyncio
async def test_analyze_anomaly_demo(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/nodes/demo-node-99/insights/analyze", headers=auth_headers("operator", demo=True)
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "Plex" in data["headline"]
    assert "transcodage" in data["explanation"].lower()


@pytest.mark.asyncio
async def test_analyze_anomaly_real(client: AsyncClient, db, auth_headers):
    node_id = "test-node-3"
    now = time.time()
    await db.execute(
        "INSERT INTO nodes (id, name, hostname, state, created_at, updated_at) "
        "VALUES (?, 'Test Node 3', 'test-host-3', 'CONNECTED', ?, ?)",
        (node_id, now, now),
    )
    await db.execute(
        """
        INSERT INTO metrics_snapshots (id, node_id, collected_at, created_at, cpu_percent, mem_total_bytes, mem_used_bytes, mem_percent, swap_total_bytes, swap_used_bytes, disk_total_bytes, disk_used_bytes, disk_percent, uptime_seconds)
        VALUES ('snap-3', ?, ?, ?, 95.0, 8589934592, 8000000000, 93.0, 0, 0, 107374182400, 21474836480, 20.0, 1000)
        """,
        (node_id, now, now),
    )
    await db.commit()

    # Stub the structured LLM or let it fall back
    response = await client.post(
        f"/api/nodes/{node_id}/insights/analyze", headers=auth_headers("operator")
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "headline" in data
    assert "explanation" in data
    assert "suggested_action" in data
