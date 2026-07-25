from __future__ import annotations

import json
import time

import pytest
from fastapi import status
from httpx import AsyncClient

from master.api import deps
from master.main import app


@pytest.fixture
def auth_headers(security):
    def _make(role: str = "admin"):
        token = security.create_access_token("test-user", "test_user", role)
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
async def test_get_disk_scan_cache_hit(client: AsyncClient, db, auth_headers):
    """Cached disk-scan result is returned directly without sending intent."""
    node_id = "test-node-cache"
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES (?, ?, 'CONNECTED', ?, ?)",
        (node_id, "cache-node", time.time(), time.time()),
    )
    await db.commit()

    cached_data = json.dumps({
        "root": {"name": "/", "path": "/", "size": 1024, "is_dir": True, "children": []},
        "truncated": False,
        "scanned_at": int(time.time()),
        "walked_count": 1,
    })
    now = time.time()
    await db.execute(
        "UPDATE nodes SET cached_disk_scan_json = ?, cached_disk_scan_at = ? WHERE id = ?",
        (cached_data, now, node_id),
    )
    await db.commit()

    response = await client.get(
        f"/api/nodes/{node_id}/disk-scan",
        headers=auth_headers("admin"),
        params={"path": "/"},
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["root"]["name"] == "/"
    assert body["truncated"] is False
    assert body["walked_count"] == 1


@pytest.mark.asyncio
async def test_get_disk_scan_force_requires_admin(client: AsyncClient, db, auth_headers):
    """force=true with operator role is rejected."""
    node_id = "test-node-force"
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES (?, ?, 'CONNECTED', ?, ?)",
        (node_id, "force-node", time.time(), time.time()),
    )
    await db.commit()

    response = await client.get(
        f"/api/nodes/{node_id}/disk-scan",
        headers=auth_headers("operator"),
        params={"force": "true"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_get_disk_scan_force_admin_passes(client: AsyncClient, db, auth_headers):
    """force=true with admin role passes RBAC check (may fail on intent, but not on auth)."""
    node_id = "test-node-force-admin"
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES (?, ?, 'CONNECTED', ?, ?)",
        (node_id, "force-admin-node", time.time(), time.time()),
    )
    await db.commit()

    response = await client.get(
        f"/api/nodes/{node_id}/disk-scan",
        headers=auth_headers("admin"),
        params={"force": "true"},
    )
    assert response.status_code != status.HTTP_403_FORBIDDEN
