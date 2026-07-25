from __future__ import annotations

"""
Vigile — Integration Tests for DISK_SCAN Endpoint

Exercises the Master path and the real Go Worker connection.
"""

import asyncio
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
import httpx
import uvicorn
from fastapi import status
from httpx import ASGITransport, AsyncClient

from master.api import deps
from master.core.enums import WorkerAction
from master.core.audit import AuditAction
from master.db.disk_scan_cache import get_cached_disk_scan, set_cached_disk_scan
from master.schemas.disk_scan import DiskScanResult
from master.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NODE_ID = "node-001"


def _disk_scan_json(
    name: str = "/",
    path: str = "/",
    size: int = 1024,
    is_dir: bool = True,
    *,
    walked_count: int = 5,
    truncated: bool = False,
) -> str:
    """Build a valid DiskScanResult JSON string."""
    return json.dumps(
        {
            "root": {"name": name, "path": path, "size": size, "is_dir": is_dir},
            "truncated": truncated,
            "scanned_at": int(time.time()),
            "walked_count": walked_count,
            "skipped_perm": 0,
        }
    )


def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---------------------------------------------------------------------------
# Stub NodeManager (for mock API tests)
# ---------------------------------------------------------------------------


class StubNodeManager:
    """Minimal NodeManager stub that intercepts get_node + send_intent."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict] = {}
        self._intent_handler = None
        self.intent_calls: list[dict] = []

    async def get_node(self, db, node_id: str) -> dict | None:  # noqa: ANN001
        return self._nodes.get(node_id)

    async def send_intent(  # noqa: ANN201
        self, node_id: str, intent: dict, *, timeout: float = 30.0
    ):
        self.intent_calls.append(intent)
        if self._intent_handler:
            return self._intent_handler(intent)
        action = intent.get("action", "")
        if action == "GET_STATS":
            return {"success": True, "disks": [{"mount_point": "/"}]}
        return {"success": True, "output": _disk_scan_json()}


# ---------------------------------------------------------------------------
# Fixtures (for mock API tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_nm():
    nm = StubNodeManager()
    nm._nodes[NODE_ID] = {
        "id": NODE_ID,
        "name": "test-node",
        "state": "CONNECTED",
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    return nm


@pytest.fixture
def auth_headers(security):
    def _make(role: str = "admin"):
        token = security.create_access_token("test-user", "test_user", role)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
async def client(db, stub_nm):
    now = time.time()
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES (?, ?, 'CONNECTED', ?, ?)",
        (NODE_ID, "test-node", now, now),
    )
    await db.commit()

    app.dependency_overrides[deps.get_db] = lambda: db
    app.dependency_overrides[deps.get_node_manager] = lambda: stub_nm
    app.state.master_url = "http://test"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(deps.get_db, None)
    app.dependency_overrides.pop(deps.get_node_manager, None)


@pytest.fixture(autouse=True)
def clear_rate_limiter():
    from master.core.rate_limiter import rate_limiter

    rate_limiter._buckets.clear()


# ---------------------------------------------------------------------------
# Mock API Tests (No Go Worker binary needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disk_scan_cache_then_force(
    client: AsyncClient, db, auth_headers, stub_nm  # noqa: ANN001
):
    """Cache miss → intent → return+cache. force=false → cached. force=true → re-scan."""
    scan_count = 0
    output_a = _disk_scan_json(size=1000, walked_count=5)
    output_b = _disk_scan_json(size=2000, walked_count=10)

    def handler(intent):
        nonlocal scan_count
        action = intent.get("action", "")
        if action == "GET_STATS":
            return {"success": True, "disks": [{"mount_point": "/"}]}
        scan_count += 1
        out = output_a if scan_count == 1 else output_b
        return {"success": True, "output": out}

    stub_nm._intent_handler = handler

    # 1. Cache miss → sends intent → returns + caches
    resp = await client.get(
        f"/api/nodes/{NODE_ID}/disk-scan",
        headers=auth_headers("admin"),
        params={"path": "/"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["root"]["size"] == 1000
    assert scan_count == 1

    # 2. force=false → returns cached (no new DISK_SCAN intent)
    prev_count = scan_count
    resp = await client.get(
        f"/api/nodes/{NODE_ID}/disk-scan",
        headers=auth_headers("admin"),
        params={"path": "/"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["root"]["size"] == 1000  # still cached
    assert scan_count == prev_count  # no new intent sent

    # 3. force=true → re-scans (fresh intent dispatched)
    resp = await client.get(
        f"/api/nodes/{NODE_ID}/disk-scan",
        headers=auth_headers("admin"),
        params={"path": "/", "force": "true"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["root"]["size"] == 2000  # fresh scan result
    assert scan_count == prev_count + 1


@pytest.mark.asyncio
async def test_disk_scan_path_not_allowed(
    client: AsyncClient, db, auth_headers, stub_nm  # noqa: ANN001
):
    """Worker returns {success: false, error: 'path not allowed'} → Master 502."""

    def handler(intent):
        action = intent.get("action", "")
        if action == "GET_STATS":
            return {"success": True, "disks": [{"mount_point": "/data"}]}
        return {"success": False, "error": "path not allowed"}

    stub_nm._intent_handler = handler

    resp = await client.get(
        f"/api/nodes/{NODE_ID}/disk-scan",
        headers=auth_headers("admin"),
        params={"path": "/etc/shadow"},
    )
    assert resp.status_code == 502
    assert "path not allowed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_disk_scan_intent_timeout(
    client: AsyncClient, db, auth_headers, stub_nm  # noqa: ANN001
):
    """Worker hangs → Master returns 504 after timeout."""

    def handler(intent):
        action = intent.get("action", "")
        if action == "GET_STATS":
            return {"success": True, "disks": [{"mount_point": "/"}]}
        raise TimeoutError("timed out")

    stub_nm._intent_handler = handler

    resp = await client.get(
        f"/api/nodes/{NODE_ID}/disk-scan",
        headers=auth_headers("admin"),
        params={"path": "/"},
    )
    assert resp.status_code == 504
    assert "disk-scan request in time" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_disk_scan_invalid_json_from_worker(
    client: AsyncClient, db, auth_headers, stub_nm  # noqa: ANN001
):
    """Worker returns malformed JSON → Master returns 502 (schema validation)."""

    def handler(intent):
        action = intent.get("action", "")
        if action == "GET_STATS":
            return {"success": True, "disks": [{"mount_point": "/"}]}
        return {"success": True, "output": "NOT_VALID_JSON{{{"}

    stub_nm._intent_handler = handler

    resp = await client.get(
        f"/api/nodes/{NODE_ID}/disk-scan",
        headers=auth_headers("admin"),
        params={"path": "/"},
    )
    assert resp.status_code == 502
    assert "invalid scan result" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_disk_scan_audit_logged(
    client: AsyncClient, db, auth_headers, stub_nm  # noqa: ANN001
):
    """After a successful scan, audit log has a DISK_SCAN entry."""
    resp = await client.get(
        f"/api/nodes/{NODE_ID}/disk-scan",
        headers=auth_headers("admin"),
        params={"path": "/var"},
    )
    assert resp.status_code == 200

    # Verify audit log entry
    async with db.execute(
        "SELECT * FROM audit_log WHERE action = 'DISK_SCAN' AND node_id = ?",
        (NODE_ID,),
    ) as cursor:
        rows = await cursor.fetchall()
    assert len(rows) >= 1
    entry = dict(rows[0])
    assert entry["node_id"] == NODE_ID
    details = json.loads(entry["details_json"])
    assert details["path"] == "/var"
    assert details["max_depth"] == 4


# ---------------------------------------------------------------------------
# Real Integration Test Fixtures (Compiles Go Worker & starts real Master)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def worker_binary_path(tmp_path_factory):
    """Session-scoped fixture to build the Go worker binary."""
    bin_dir = tmp_path_factory.mktemp("bin")
    bin_path = os.path.join(bin_dir, "vigile-worker")
    if os.name == "nt":
        bin_path += ".exe"

    subprocess.run(
        ["go", "build", "-o", bin_path, "."],
        cwd=os.path.abspath("worker"),
        check=True,
    )
    return bin_path


# ---------------------------------------------------------------------------
# Real Integration Test
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_disk_scan_real_integration(db, temp_dir, worker_binary_path):
    """
    True integration test spinning up a real uvicorn Master process and a real
    Go Worker process, connecting them over local websockets, and executing a scan.
    """
    import sys
    port = get_free_port()

    from master.config import settings

    original_port = settings.port
    original_allow_insecure = settings.allow_insecure
    original_enforce_https = settings.enforce_https
    original_cookie_secure = settings.cookie_secure
    original_db = settings.database_path

    settings.port = port
    settings.allow_insecure = True
    settings.enforce_https = False
    settings.cookie_secure = False
    settings.database_path = os.path.join(temp_dir, "test_integration.db")

    # Copy schema and data from the active SQLite database to test_integration.db
    # This keeps our seeder admin users intact
    shutil.copyfile(original_db, settings.database_path)

    # Start the Master as a subprocess to completely isolate its database lifecycle from pytest's connection
    master_env = os.environ.copy()
    master_env["ALLOW_INSECURE"] = "true"
    master_env["ENFORCE_HTTPS"] = "false"
    master_env["COOKIE_SECURE"] = "false"
    master_env["DATABASE_PATH"] = settings.database_path
    master_env["JWT_SECRET_KEY"] = "test_jwt"
    master_env["SERVER_SECRET_KEY"] = "test_secret"
    master_env["MASTER_KEY_PATH"] = os.path.join(temp_dir, "master_ed25519.key")
    master_env["TESTING"] = "true"

    master_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "master.main:app",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--log-level", "info",
        ],
        env=master_env,
        cwd=os.path.abspath("."),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    master_base_url = f"http://127.0.0.1:{port}"

    # Poll until ready
    ready = False
    async with httpx.AsyncClient() as client:
        for _ in range(50):
            try:
                r = await client.get(f"{master_base_url}/health")
                if r.status_code == 200:
                    ready = True
                    break
            except Exception:
                pass
            await asyncio.sleep(0.1)

    if not ready:
        stdout_data, stderr_data = master_proc.communicate(timeout=2.0)
        raise RuntimeError(
            f"Master uvicorn failed to start on port {port}.\n"
            f"STDOUT:\n{stdout_data.decode()}\n"
            f"STDERR:\n{stderr_data.decode()}"
        )

    proc = None
    try:
        # Fetch the dynamically generated admin user UUID from the seeded database file
        import aiosqlite
        async with aiosqlite.connect(settings.database_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT id FROM users WHERE username = 'admin'") as cursor:
                row = await cursor.fetchone()
                assert row is not None, "Seeded admin user not found in database"
                admin_uuid = row["id"]

        # Create administrative JWT token using the SecurityManager instance
        from master.core.security_manager import get_security_instance

        sec = get_security_instance()
        admin_token = sec.create_access_token(admin_uuid, "admin", "admin")
        auth_headers_dict = {"Authorization": f"Bearer {admin_token}"}

        # 1. Ask Master for a JOIN_TOKEN
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{master_base_url}/api/nodes/generate-join",
                headers=auth_headers_dict,
                json={"name": "integration-node", "group": "test-group"},
            )
            assert r.status_code == 201, f"failed to generate join token: {r.text}"
            join_data = r.json()
            node_id = join_data["node_id"]
            join_token = join_data["token"]

        # 2. Launch Go Worker process
        worker_key_dir = os.path.join(temp_dir, "worker_keys")
        os.makedirs(worker_key_dir, exist_ok=True)

        env = os.environ.copy()
        env["ALLOW_INSECURE"] = "true"

        proc = subprocess.Popen(
            [
                worker_binary_path,
                "--master",
                master_base_url,
                "--token",
                join_token,
                "--key-dir",
                worker_key_dir,
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 3. Wait until the node state becomes CONNECTED
        node_connected = False
        for _ in range(100):
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.get(
                    f"{master_base_url}/api/nodes", headers=auth_headers_dict
                )
                if r.status_code == 200:
                    nodes = r.json()
                    node = next((n for n in nodes if n["id"] == node_id), None)
                    if node and node["state"] == "CONNECTED":
                        node_connected = True
                        break
            await asyncio.sleep(0.1)

        if not node_connected:
            worker_stdout, worker_stderr = proc.communicate(timeout=2.0)
            master_proc.terminate()
            master_stdout, master_stderr = master_proc.communicate(timeout=2.0)
            raise AssertionError(
                f"Worker failed to connect/enroll.\n"
                f"WORKER STDOUT:\n{worker_stdout.decode()}\n"
                f"WORKER STDERR:\n{worker_stderr.decode()}\n"
                f"MASTER STDOUT:\n{master_stdout.decode()}\n"
                f"MASTER STDERR:\n{master_stderr.decode()}\n"
                f"Nodes list: {nodes if 'nodes' in locals() else None}"
            )

        # 4. Populate a target directory tree with ~500 files and 30 dirs
        scan_dir = Path(temp_dir) / "scan_target"
        scan_dir.mkdir()
        dirs = [scan_dir]
        for i in range(30):
            d = scan_dir / f"dir_{i}"
            d.mkdir(exist_ok=True)
            dirs.append(d)
        for i in range(500):
            parent = dirs[i % len(dirs)]
            f = parent / f"file_{i}.txt"
            f.write_text(f"content_{i}")

        # 5. Execute Disk Scan via Master endpoint
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(
                f"{master_base_url}/api/nodes/{node_id}/disk-scan",
                headers=auth_headers_dict,
                params={
                    "path": str(scan_dir),
                    "max_depth": 3,
                    "min_size_bytes": 0,
                    "force": "true",
                },
            )
            assert r.status_code == 200, f"DISK_SCAN failed: {r.text}"
            scan_res = r.json()

        # 6. Verify schema & correctness
        assert "root" in scan_res
        assert "walked_count" in scan_res
        assert "truncated" in scan_res
        assert scan_res["walked_count"] >= 531  # 500 files + 30 dirs + root

        root_node = scan_res["root"]
        assert root_node["name"] == scan_dir.name
        assert root_node["path"] == str(scan_dir)
        assert root_node["size"] >= 0
        assert root_node["is_dir"] is True
        assert len(root_node["children"]) > 0

        # 7. Verify cache hit (even if we delete the source directory, cache returns it)
        shutil.rmtree(scan_dir)
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(
                f"{master_base_url}/api/nodes/{node_id}/disk-scan",
                headers=auth_headers_dict,
                params={
                    "path": str(scan_dir),
                    "max_depth": 3,
                    "min_size_bytes": 0,
                    "force": "false",
                },
            )
            assert r.status_code == 200, f"Cache hit failed: {r.text}"
            cached_res = r.json()
            assert cached_res["walked_count"] == scan_res["walked_count"]



    except Exception as e:
        # Capture outputs for general exceptions
        w_out, w_err = b"", b""
        if proc:
            try:
                proc.terminate()
                w_out, w_err = proc.communicate(timeout=2.0)
            except Exception:
                pass
        m_out, m_err = b"", b""
        try:
            master_proc.terminate()
            m_out, m_err = master_proc.communicate(timeout=2.0)
        except Exception:
            pass
        raise RuntimeError(
            f"Test failed with exception: {e}\n"
            f"WORKER STDOUT:\n{w_out.decode()}\n"
            f"WORKER STDERR:\n{w_err.decode()}\n"
            f"MASTER STDOUT:\n{m_out.decode()}\n"
            f"MASTER STDERR:\n{m_err.decode()}"
        ) from e

    finally:
        # Shut down worker
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()

        # Shut down Master uvicorn subprocess
        if master_proc:
            master_proc.terminate()
            try:
                master_proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                master_proc.kill()

        # Restore global configuration
        settings.port = original_port
        settings.allow_insecure = original_allow_insecure
        settings.enforce_https = original_enforce_https
        settings.cookie_secure = original_cookie_secure
        settings.database_path = original_db


