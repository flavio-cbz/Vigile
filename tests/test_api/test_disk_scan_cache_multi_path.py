from __future__ import annotations

import json
import time

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from master.api import deps
from master.core.node_manager import NodeManager
from master.db.disk_scan_cache import (
    get_cached_disk_scan,
    get_node_disk_mounts,
    invalidate_cached_disk_scan,
    set_cached_disk_scan,
    set_node_disk_mounts,
)
from master.main import app


@pytest.fixture
def auth_headers(security):
    def _make(role: str = "admin"):
        token = security.create_access_token("test-user", "test_user", role)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
async def client(db):
    app.dependency_overrides[deps.get_db] = lambda: db
    app.state.master_url = "http://test"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(deps.get_db, None)


@pytest.mark.asyncio
async def test_multi_path_cache_isolation(db):
    """Verify that scans for / and /mnt/data are cached independently in disk_scans_cache."""
    node_id = "node-iso-1"
    now = time.time()
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) VALUES (?, 'iso-node', 'CONNECTED', ?, ?)",
        (node_id, now, now),
    )
    await db.commit()

    scan_root = json.dumps({"root": {"name": "/", "path": "/", "size": 100, "is_dir": True}})
    scan_data = json.dumps({"root": {"name": "data", "path": "/mnt/data", "size": 500, "is_dir": True}})

    await set_cached_disk_scan(db, node_id, "/", scan_root, now)
    await set_cached_disk_scan(db, node_id, "/mnt/data", scan_data, now)

    ret_root, ts_root = await get_cached_disk_scan(db, node_id, "/")
    ret_data, ts_data = await get_cached_disk_scan(db, node_id, "/mnt/data")
    ret_other, ts_other = await get_cached_disk_scan(db, node_id, "/var")

    assert ret_root == scan_root
    assert ret_data == scan_data
    assert ret_other is None
    assert ts_other is None

    # Invalidate /mnt/data only
    await invalidate_cached_disk_scan(db, node_id, "/mnt/data")
    ret_root_after, _ = await get_cached_disk_scan(db, node_id, "/")
    ret_data_after, _ = await get_cached_disk_scan(db, node_id, "/mnt/data")

    assert ret_root_after == scan_root  # / is untouched
    assert ret_data_after is None  # /mnt/data is gone


@pytest.mark.asyncio
async def test_get_and_set_node_disk_mounts_dual_format(db):
    """Verify support for both string lists and dict lists with mount_point."""
    node_id = "node-mounts-1"
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) VALUES (?, 'test', 'CONNECTED', ?, ?)",
        (node_id, time.time(), time.time()),
    )
    await db.commit()

    # 1. Set as string list
    await set_node_disk_mounts(db, node_id, ["/", "/mnt/usb", "/home"])
    res1 = await get_node_disk_mounts(db, node_id)
    assert "/" in res1
    assert "/mnt/usb" in res1
    assert "/home" in res1

    # 2. Set as dict list
    await set_node_disk_mounts(db, node_id, [{"mount_point": "/"}, {"mount_point": "/data"}])
    res2 = await get_node_disk_mounts(db, node_id)
    assert res2 == ["/", "/data"]

    # 3. Handle raw string list directly in cached_disks_json column (legacy DB state)
    await db.execute(
        "UPDATE nodes SET cached_disks_json = ? WHERE id = ?",
        (json.dumps(["/", "/mnt/storage"]), node_id),
    )
    await db.commit()
    res3 = await get_node_disk_mounts(db, node_id)
    assert res3 == ["/", "/mnt/storage"]


@pytest.mark.asyncio
async def test_disk_scan_path_traversal_rejected(client: AsyncClient, db, auth_headers):
    """Verify path traversal attempts are rejected fail-closed."""
    node_id = "node-traversal-1"
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) VALUES (?, 'test', 'CONNECTED', ?, ?)",
        (node_id, time.time(), time.time()),
    )
    await db.commit()

    # Relative path
    resp1 = await client.get(
        f"/api/nodes/{node_id}/disk-scan",
        headers=auth_headers("admin"),
        params={"path": "etc/shadow"},
    )
    assert resp1.status_code == status.HTTP_400_BAD_REQUEST

    # Null byte injection
    resp2 = await client.get(
        f"/api/nodes/{node_id}/disk-scan",
        headers=auth_headers("admin"),
        params={"path": "/var" + chr(0) + "/secret"},
    )
    assert resp2.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_disk_scan_unauthorized_mount_rejected(client: AsyncClient, db, auth_headers):
    """Verify clean_path must strictly equal an allowed mount point; otherwise 400."""
    node_id = "node-strict-mount-1"
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) VALUES (?, 'test', 'CONNECTED', ?, ?)",
        (node_id, time.time(), time.time()),
    )
    await db.commit()
    await set_node_disk_mounts(db, node_id, ["/", "/mnt/data"])

    # Path /var is not in allowed mounts
    resp = await client.get(
        f"/api/nodes/{node_id}/disk-scan",
        headers=auth_headers("admin"),
        params={"path": "/var"},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.json()["detail"] == "Path is not an allowed mount point"

    # Subpath /mnt/data/subdir is not strictly an allowed mount point
    resp_sub = await client.get(
        f"/api/nodes/{node_id}/disk-scan",
        headers=auth_headers("admin"),
        params={"path": "/mnt/data/subdir"},
    )
    assert resp_sub.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_sub.json()["detail"] == "Path is not an allowed mount point"


@pytest.mark.asyncio
async def test_disk_scan_force_preserves_cache_on_failure(client: AsyncClient, db, auth_headers):
    """Verify that force=true does not pre-delete cache if worker scan fails."""
    node_id = "node-force-preserve"
    now = time.time()
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) VALUES (?, 'test', 'CONNECTED', ?, ?)",
        (node_id, now, now),
    )
    await db.commit()
    await set_node_disk_mounts(db, node_id, ["/"])

    cached_data = json.dumps({
        "root": {"name": "/", "path": "/", "size": 1024, "is_dir": True, "children": []},
        "truncated": False,
        "scanned_at": int(now),
        "walked_count": 1,
    })
    await set_cached_disk_scan(db, node_id, "/", cached_data, now)

    # force=true on an offline/unmocked worker will fail, but must not delete the cache
    resp = await client.get(
        f"/api/nodes/{node_id}/disk-scan",
        headers=auth_headers("admin"),
        params={"path": "/", "force": "true"},
    )
    assert resp.status_code != status.HTTP_200_OK

    # Verify cache is still preserved
    cached_after, ts_after = await get_cached_disk_scan(db, node_id, "/")
    assert cached_after == cached_data
    assert ts_after == now

