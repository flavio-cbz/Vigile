#!/usr/bin/env python3
"""
Vigile — Logs API Unit Tests
Tests the GET /api/nodes/{id}/logs endpoint logic using httpx AsyncClient.
"""

import asyncio
import os
import sys
import tempfile
import time

import pathlib
PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent.parent)
sys.path.insert(0, PROJECT_ROOT)

tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_PATH"] = os.path.join(tmpdir, "test_logs.db")
os.environ["MASTER_KEY_PATH"] = os.path.join(tmpdir, "master_logs.key")
os.environ["SERVER_SECRET_KEY"] = "test_secret_logs"
os.environ["JWT_SECRET_KEY"] = "test_jwt_logs"

PASS = "\033[92m\u2713\033[0m"
FAIL = "\033[91m\u2717\033[0m"
results = []

def check(name: str, condition: bool, detail: str = ""):
    icon = PASS if condition else FAIL
    print(f"  {icon} {name}" + (f" ({detail})" if detail else ""))
    results.append((name, condition))
    return condition

from master.db.database import init_db, close_db, reset_db
from master.db.migrations import run_migrations
from master.core.node_manager import node_manager, NodeState
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from master.core.security_manager import init_security, get_security_instance
from master.main import app
from master.api import deps


init_security(
    server_secret=os.environ["SERVER_SECRET_KEY"],
    jwt_secret=os.environ["JWT_SECRET_KEY"],
    master_private_key=Ed25519PrivateKey.generate(),
)
security = get_security_instance()


def _make_token(role: str = "admin") -> str:
    return security.create_access_token("test-user", "test_user", role)


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


async def _run_test(description: str, test_fn):
    """Run an individual test with fresh DB state."""
    await reset_db()
    db = await init_db()
    await run_migrations(db)
    app.dependency_overrides[deps.get_db] = lambda: db
    try:
        await test_fn(db)
    finally:
        app.dependency_overrides.pop(deps.get_db, None)
        await close_db()
        await reset_db()


print("\n\U0001f4bb Logs API — GET /api/nodes/{id}/logs")


async def test_logs_success_file():
    async def _test(db):
        node_id = await _setup_node(db, "logs-file")
        original = node_manager.send_intent
        node_manager.send_intent = mock_send_intent_success
        try:
            from httpx import AsyncClient, ASGITransport
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                token = _make_token()
                resp = await client.get(
                    f"/api/nodes/{node_id}/logs?path=/var/log/syslog&lines=10",
                    headers={"Authorization": f"Bearer {token}"},
                )
                check("File logs: returns 200", resp.status_code == 200)
                if resp.status_code == 200:
                    d = resp.json()
                    check("File logs: node_id matches", d["node_id"] == node_id)
                    check("File logs: output non-empty", len(d["output"]) > 0)
                    check("File logs: lines=10", d["lines"] == 10)
                    check("File logs: path is /var/log/syslog", d["path"] == "/var/log/syslog")
                    check("File logs: error is None", d["error"] is None)
        finally:
            node_manager.send_intent = original

    await _run_test("logs success file", _test)


async def test_logs_success_service():
    async def _test(db):
        node_id = await _setup_node(db, "logs-svc")
        original = node_manager.send_intent
        node_manager.send_intent = mock_send_intent_success
        try:
            from httpx import AsyncClient, ASGITransport
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                token = _make_token()
                resp = await client.get(
                    f"/api/nodes/{node_id}/logs?service=nginx&lines=20",
                    headers={"Authorization": f"Bearer {token}"},
                )
                check("Service logs: returns 200", resp.status_code == 200)
                if resp.status_code == 200:
                    d = resp.json()
                    check("Service logs: node_id matches", d["node_id"] == node_id)
                    check("Service logs: service is nginx", d["service"] == "nginx")
                    check("Service logs: path is None", d["path"] is None)
        finally:
            node_manager.send_intent = original

    await _run_test("logs success service", _test)


async def test_logs_default_path():
    async def _test(db):
        node_id = await _setup_node(db, "logs-default")
        original = node_manager.send_intent
        node_manager.send_intent = mock_send_intent_success
        try:
            from httpx import AsyncClient, ASGITransport
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                token = _make_token()
                resp = await client.get(
                    f"/api/nodes/{node_id}/logs",
                    headers={"Authorization": f"Bearer {token}"},
                )
                check("Default logs: returns 200", resp.status_code == 200)
                if resp.status_code == 200:
                    d = resp.json()
                    check("Default logs: path is syslog", d["path"] == "/var/log/syslog")
                    check("Default logs: default lines=50", d["lines"] == 50)
        finally:
            node_manager.send_intent = original

    await _run_test("logs default path", _test)


async def test_logs_node_not_found():
    async def _test(db):
        from httpx import AsyncClient, ASGITransport
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            token = _make_token()
            resp = await client.get(
                "/api/nodes/nonexistent-id/logs",
                headers={"Authorization": f"Bearer {token}"},
            )
            check("Node not found: returns 404", resp.status_code == 404)

    await _run_test("logs not found", _test)


async def test_logs_node_not_connected():
    async def _test(db):
        node_id = await node_manager.create_node(db, name="logs-offline")
        # Don't transition to CONNECTED — node exists but no WS
        original = node_manager.send_intent
        node_manager.send_intent = mock_send_intent_not_connected
        try:
            from httpx import AsyncClient, ASGITransport
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                token = _make_token()
                resp = await client.get(
                    f"/api/nodes/{node_id}/logs",
                    headers={"Authorization": f"Bearer {token}"},
                )
                check("Not connected: returns 503", resp.status_code == 503)
                if resp.status_code == 503:
                    check("Not connected: detail mentions not connected",
                          "not connected" in resp.json()["detail"].lower())
        finally:
            node_manager.send_intent = original

    await _run_test("logs not connected", _test)


async def test_logs_worker_timeout():
    async def _test(db):
        node_id = await _setup_node(db, "logs-timeout")
        original = node_manager.send_intent
        node_manager.send_intent = mock_send_intent_timeout
        try:
            from httpx import AsyncClient, ASGITransport
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                token = _make_token()
                resp = await client.get(
                    f"/api/nodes/{node_id}/logs",
                    headers={"Authorization": f"Bearer {token}"},
                )
                check("Worker timeout: returns 504", resp.status_code == 504)
        finally:
            node_manager.send_intent = original

    await _run_test("logs timeout", _test)


async def test_logs_worker_error():
    async def _test(db):
        node_id = await _setup_node(db, "logs-error")
        original = node_manager.send_intent
        node_manager.send_intent = mock_send_intent_fail
        try:
            from httpx import AsyncClient, ASGITransport
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                token = _make_token()
                resp = await client.get(
                    f"/api/nodes/{node_id}/logs?path=/var/log/auth.log",
                    headers={"Authorization": f"Bearer {token}"},
                )
                check("Worker error: returns 200", resp.status_code == 200)
                if resp.status_code == 200:
                    d = resp.json()
                    check("Worker error: error field set", d["error"] == "permission denied")
                    check("Worker error: output is empty", d["output"] == "")
        finally:
            node_manager.send_intent = original

    await _run_test("logs worker error", _test)


async def test_logs_unauthorized():
    async def _test(db):
        from httpx import AsyncClient, ASGITransport
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/nodes/some-id/logs")
            check("No auth: returns 401", resp.status_code == 401)

    await _run_test("logs unauthorized", _test)


async def test_logs_viewer_forbidden():
    async def _test(db):
        from httpx import AsyncClient, ASGITransport
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            token = _make_token(role="viewer")
            resp = await client.get(
                "/api/nodes/some-id/logs",
                headers={"Authorization": f"Bearer {token}"},
            )
            check("Viewer forbidden: returns 403", resp.status_code == 403)

    await _run_test("logs viewer forbidden", _test)


# ── Run all tests ──────────────────────────────────────────────────

print("\n\U0001f4dd Logs API Tests")
asyncio.run(test_logs_success_file())
asyncio.run(test_logs_success_service())
asyncio.run(test_logs_default_path())
asyncio.run(test_logs_node_not_found())
asyncio.run(test_logs_node_not_connected())
asyncio.run(test_logs_worker_timeout())
asyncio.run(test_logs_worker_error())
asyncio.run(test_logs_unauthorized())
asyncio.run(test_logs_viewer_forbidden())

print("\n" + "=" * 60)
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
total = len(results)
print(f"Results: {passed}/{total} passed", end="")
if failed:
    print(f"  ({failed} FAILED)")
    for name, ok in results:
        if not ok:
            print(f"  {FAIL} {name}")
    sys.exit(1)
else:
    print(" \U0001f389")

import shutil
shutil.rmtree(tmpdir, ignore_errors=True)
