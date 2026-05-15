#!/usr/bin/env python3
"""
YouCloud AI Admin — Logs API Unit Tests
Tests the GET /api/nodes/{id}/logs endpoint by overriding FastAPI dependencies.
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
from master.core.security_manager import security
from master.api.nodes import LogsResponse

# Override get_security dependency
from master.core.security_manager import SecurityManager
from master.api import deps

original_security = deps.get_security

def mock_security():
    return security

deps.get_security = mock_security

# We'll use fastapi TestClient
from fastapi.testclient import TestClient
from master.main import app

# Override the node_manager dependency
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


def _make_token(role: str = "admin") -> str:
    """Generate a valid JWT for testing."""
    return security.create_access_token("test-user", "test_user", role)


print("\n\u{1F4BB} Logs API — GET /api/nodes/{id}/logs")

async def setup_db():
    db = await init_db()
    await run_migrations(db)
    return db


def test_logs_success_file():
    """Service logs: send READ_LOGS with path param, get output."""
    async def _run():
        await reset_db()
        db = await setup_db()
        node_id = await node_manager.create_node(db, name="logs-test")
        # Mark as CONNECTED so get_node returns it
        await node_manager.transition_state(db, node_id, NodeState.CONNECTED)
        await close_db()

        original = node_manager.send_intent
        node_manager.send_intent = mock_send_intent_success
        try:
            token = _make_token()
            with TestClient(app) as client:
                resp = client.get(
                    f"/api/nodes/{node_id}/logs?path=/var/log/syslog&lines=10",
                    headers={"Authorization": f"Bearer {token}"},
                )
                check("GET logs file: returns 200", resp.status_code == 200)
                if resp.status_code == 200:
                    data = resp.json()
                    check("logs: node_id matches", data["node_id"] == node_id)
                    check("logs: output is non-empty", len(data["output"]) > 0)
                    check("logs: lines=10", data["lines"] == 10)
                    check("logs: path is present", data["path"] == "/var/log/syslog")
                    check("logs: error is None", data["error"] is None)
        finally:
            node_manager.send_intent = original
        await reset_db()

    asyncio.run(_run())


def test_logs_success_service():
    """Service logs: send READ_LOGS_SERVICE with service param, get output."""
    async def _run():
        await reset_db()
        db = await setup_db()
        node_id = await node_manager.create_node(db, name="logs-svc")
        await node_manager.transition_state(db, node_id, NodeState.CONNECTED)
        await close_db()

        original = node_manager.send_intent
        node_manager.send_intent = mock_send_intent_success
        try:
            token = _make_token()
            with TestClient(app) as client:
                resp = client.get(
                    f"/api/nodes/{node_id}/logs?service=nginx&lines=20",
                    headers={"Authorization": f"Bearer {token}"},
                )
                check("GET logs service: returns 200", resp.status_code == 200)
                if resp.status_code == 200:
                    data = resp.json()
                    check("logs service: node_id matches", data["node_id"] == node_id)
                    check("logs service: service is nginx", data["service"] == "nginx")
                    check("logs service: path is None", data["path"] is None)
        finally:
            node_manager.send_intent = original
        await reset_db()

    asyncio.run(_run())


def test_logs_default_path():
    """No service or path specified: defaults to /var/log/syslog."""
    async def _run():
        await reset_db()
        db = await setup_db()
        node_id = await node_manager.create_node(db, name="logs-default")
        await node_manager.transition_state(db, node_id, NodeState.CONNECTED)
        await close_db()

        original = node_manager.send_intent
        node_manager.send_intent = mock_send_intent_success
        try:
            token = _make_token()
            with TestClient(app) as client:
                resp = client.get(
                    f"/api/nodes/{node_id}/logs",
                    headers={"Authorization": f"Bearer {token}"},
                )
                check("GET logs default: returns 200", resp.status_code == 200)
                if resp.status_code == 200:
                    data = resp.json()
                    check("logs default: path is syslog", data["path"] == "/var/log/syslog")
                    check("logs default: default lines=50", data["lines"] == 50)
        finally:
            node_manager.send_intent = original
        await reset_db()

    asyncio.run(_run())


def test_logs_node_not_found():
    """Non-existent node id returns 404."""
    async def _run():
        token = _make_token()
        with TestClient(app) as client:
            resp = client.get(
                "/api/nodes/nonexistent-id/logs",
                headers={"Authorization": f"Bearer {token}"},
            )
            check("logs 404: non-existent node returns 404", resp.status_code == 404)
        await reset_db()

    asyncio.run(_run())


def test_logs_node_not_connected():
    """Node exists but no WebSocket → 503."""
    async def _run():
        await reset_db()
        db = await setup_db()
        node_id = await node_manager.create_node(db, name="logs-offline")
        await close_db()

        original = node_manager.send_intent
        node_manager.send_intent = mock_send_intent_not_connected
        try:
            token = _make_token()
            with TestClient(app) as client:
                resp = client.get(
                    f"/api/nodes/{node_id}/logs",
                    headers={"Authorization": f"Bearer {token}"},
                )
                check("logs 503: not connected returns 503", resp.status_code == 503)
                if resp.status_code == 503:
                    check("logs 503: detail mentions not connected",
                          "not connected" in resp.json()["detail"])
        finally:
            node_manager.send_intent = original
        await reset_db()

    asyncio.run(_run())


def test_logs_worker_timeout():
    """Worker doesn't respond → 504."""
    async def _run():
        await reset_db()
        db = await setup_db()
        node_id = await node_manager.create_node(db, name="logs-timeout")
        await node_manager.transition_state(db, node_id, NodeState.CONNECTED)
        await close_db()

        original = node_manager.send_intent
        node_manager.send_intent = mock_send_intent_timeout
        try:
            token = _make_token()
            with TestClient(app) as client:
                resp = client.get(
                    f"/api/nodes/{node_id}/logs",
                    headers={"Authorization": f"Bearer {token}"},
                )
                check("logs 504: timeout returns 504", resp.status_code == 504)
        finally:
            node_manager.send_intent = original
        await reset_db()

    asyncio.run(_run())


def test_logs_worker_error():
    """Worker returns error → 200 with error field set."""
    async def _run():
        await reset_db()
        db = await setup_db()
        node_id = await node_manager.create_node(db, name="logs-error")
        await node_manager.transition_state(db, node_id, NodeState.CONNECTED)
        await close_db()

        original = node_manager.send_intent
        node_manager.send_intent = mock_send_intent_fail
        try:
            token = _make_token()
            with TestClient(app) as client:
                resp = client.get(
                    f"/api/nodes/{node_id}/logs?path=/var/log/auth.log",
                    headers={"Authorization": f"Bearer {token}"},
                )
                check("logs worker error: returns 200", resp.status_code == 200)
                if resp.status_code == 200:
                    data = resp.json()
                    check("logs worker error: error field set",
                          data["error"] == "permission denied")
                    check("logs worker error: output is empty",
                          data["output"] == "")
        finally:
            node_manager.send_intent = original
        await reset_db()

    asyncio.run(_run())


def test_logs_unauthorized():
    """No auth token → 401."""
    async def _run():
        with TestClient(app) as client:
            resp = client.get("/api/nodes/some-id/logs")
            check("logs auth: missing token returns 401", resp.status_code == 401)
        await reset_db()

    asyncio.run(_run())


def test_logs_viewer_forbidden():
    """Viewer role cannot access logs (needs operator+)."""
    async def _run():
        token = _make_token(role="viewer")
        with TestClient(app) as client:
            resp = client.get(
                "/api/nodes/some-id/logs",
                headers={"Authorization": f"Bearer {token}"},
            )
            check("logs auth: viewer gets 403", resp.status_code == 403)
        await reset_db()

    asyncio.run(_run())


print("\n📝 Logs API Tests")
test_logs_success_file()
test_logs_success_service()
test_logs_default_path()
test_logs_node_not_found()
test_logs_node_not_connected()
test_logs_worker_timeout()
test_logs_worker_error()
test_logs_unauthorized()
test_logs_viewer_forbidden()

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
    print(" 🎉")

import shutil
shutil.rmtree(tmpdir, ignore_errors=True)
