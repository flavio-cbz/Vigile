#!/usr/bin/env python3
"""
Vigile — Services & Containers API Unit Tests
Tests the GET/POST /api/nodes/{node_id}/services and /containers endpoints.
"""

import asyncio
import json
import os
import sys
import tempfile

import pathlib
PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent.parent)
sys.path.insert(0, PROJECT_ROOT)

tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_PATH"] = os.path.join(tmpdir, "test_svc.db")
os.environ["MASTER_KEY_PATH"] = os.path.join(tmpdir, "master_svc.key")
os.environ["SERVER_SECRET_KEY"] = "test_secret_svc"
os.environ["JWT_SECRET_KEY"] = "test_jwt_svc"

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
from master.main import app
from master.api import deps


def _make_token(role: str = "admin") -> str:
    return security.create_access_token("test-user", "test_user", role)


# ---------------------------------------------------------------------------
# Mock send_intent responses
# ---------------------------------------------------------------------------

SERVICES_JSON = json.dumps([
    {"name": "ssh.service", "state": "active", "status": "running"},
    {"name": "nginx.service", "state": "active", "status": "running"},
    {"name": "docker.service", "state": "active", "status": "running"},
])

STATUS_JSON = json.dumps({
    "service": "nginx.service",
    "active": "active",
    "enabled": "enabled",
})

CONTAINERS_JSON = json.dumps([
    {"id": "a1b2c3d4e5f6", "name": "web", "image": "nginx:latest",
     "state": "running", "ports": ["0.0.0.0:80->80"]},
    {"id": "f6e5d4c3b2a1", "name": "db", "image": "postgres:15",
     "state": "running", "ports": ["5432"]},
])


async def mock_list_services(node_id, intent, *, timeout=30.0):
    return {"intent_id": "s-1", "success": True, "output": SERVICES_JSON, "error": ""}

async def mock_status_service(node_id, intent, *, timeout=30.0):
    return {"intent_id": "s-2", "success": True, "output": STATUS_JSON, "error": ""}

async def mock_restart_service(node_id, intent, *, timeout=30.0):
    return {"intent_id": "s-3", "success": True, "output": "Service nginx.service restarted", "error": ""}

async def mock_list_containers(node_id, intent, *, timeout=30.0):
    return {"intent_id": "c-1", "success": True, "output": CONTAINERS_JSON, "error": ""}

async def mock_restart_container(node_id, intent, *, timeout=30.0):
    return {"intent_id": "c-2", "success": True, "output": "Container a1b2c3d4e5f6 restarted", "error": ""}

async def mock_intent_fail(node_id, intent, *, timeout=30.0):
    return {"intent_id": "x-1", "success": False, "output": "",
            "error": f"action {intent['action']} failed"}

async def mock_intent_not_connected(node_id, intent, *, timeout=30.0):
    raise RuntimeError(f"Node {node_id} is not connected")

async def mock_intent_timeout(node_id, intent, *, timeout=30.0):
    raise TimeoutError("Worker did not respond")


async def _setup_node(db, name: str = "test-svc") -> str:
    node_id = await node_manager.create_node(db, name=name)
    await node_manager.transition_state(db, node_id, NodeState.ENROLLING)
    await node_manager.transition_state(db, node_id, NodeState.CONNECTED)
    return node_id


async def _run_test(description: str, test_fn):
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


async def _request(method, path, token=None):
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, headers=headers)


print("\n\U0001f4bb Services & Containers API")


# ── LIST_SERVICES ─────────────────────────────────────────────────


async def test_list_services_success():
    async def _test(db):
        node_id = await _setup_node(db, "svc-list")
        orig = node_manager.send_intent
        node_manager.send_intent = mock_list_services
        try:
            token = _make_token()
            resp = await _request("GET", f"/api/nodes/{node_id}/services", token)
            check("list_services: returns 200", resp.status_code == 200)
            if resp.status_code == 200:
                d = resp.json()
                check("list_services: node_id matches", d["node_id"] == node_id)
                check("list_services: has services", len(d["services"]) == 3)
                if len(d["services"]) > 0:
                    check("list_services: first service has name",
                          d["services"][0].get("name") == "ssh.service")
                    check("list_services: first service has state",
                          d["services"][0].get("state") == "active")
        finally:
            node_manager.send_intent = orig
    await _run_test("list_services success", _test)


async def test_list_services_not_found():
    async def _test(db):
        token = _make_token()
        resp = await _request("GET", "/api/nodes/nonexistent/services", token)
        check("list_services: 404", resp.status_code == 404)
    await _run_test("list_services 404", _test)


async def test_list_services_not_connected():
    async def _test(db):
        node_id = await node_manager.create_node(db, name="svc-offline")
        orig = node_manager.send_intent
        node_manager.send_intent = mock_intent_not_connected
        try:
            token = _make_token()
            resp = await _request("GET", f"/api/nodes/{node_id}/services", token)
            check("list_services: 503", resp.status_code == 503)
        finally:
            node_manager.send_intent = orig
    await _run_test("list_services 503", _test)


async def test_list_services_timeout():
    async def _test(db):
        node_id = await _setup_node(db, "svc-timeout")
        orig = node_manager.send_intent
        node_manager.send_intent = mock_intent_timeout
        try:
            token = _make_token()
            resp = await _request("GET", f"/api/nodes/{node_id}/services", token)
            check("list_services: 504", resp.status_code == 504)
        finally:
            node_manager.send_intent = orig
    await _run_test("list_services 504", _test)


# ── STATUS_SERVICE ────────────────────────────────────────────────


async def test_service_status_success():
    async def _test(db):
        node_id = await _setup_node(db, "svc-status")
        orig = node_manager.send_intent
        node_manager.send_intent = mock_status_service
        try:
            token = _make_token()
            resp = await _request("GET", f"/api/nodes/{node_id}/services/nginx.service", token)
            check("service_status: returns 200", resp.status_code == 200)
            if resp.status_code == 200:
                d = resp.json()
                check("service_status: node_id matches", d["node_id"] == node_id)
                check("service_status: service name", d["service"] == "nginx.service")
                check("service_status: active", d["active"] == "active")
                check("service_status: enabled", d["enabled"] == "enabled")
        finally:
            node_manager.send_intent = orig
    await _run_test("service_status success", _test)


async def test_service_status_fail():
    async def _test(db):
        node_id = await _setup_node(db, "svc-status-fail")
        orig = node_manager.send_intent
        node_manager.send_intent = mock_intent_fail
        try:
            token = _make_token()
            resp = await _request("GET", f"/api/nodes/{node_id}/services/unknown.service", token)
            check("service_status: fail returns 200", resp.status_code == 200)
            if resp.status_code == 200:
                d = resp.json()
                check("service_status: fallback active=unknown",
                      d.get("active") == "unknown")
                check("service_status: fallback enabled=unknown",
                      d.get("enabled") == "unknown")
        finally:
            node_manager.send_intent = orig
    await _run_test("service_status fail", _test)


# ── RESTART_SERVICE ───────────────────────────────────────────────


async def test_restart_service_success():
    async def _test(db):
        node_id = await _setup_node(db, "svc-restart")
        orig = node_manager.send_intent
        node_manager.send_intent = mock_restart_service
        try:
            token = _make_token()
            resp = await _request("POST", f"/api/nodes/{node_id}/services/nginx.service/restart", token)
            check("restart_service: returns 200", resp.status_code == 200)
            if resp.status_code == 200:
                d = resp.json()
                check("restart_service: node_id matches", d["node_id"] == node_id)
                check("restart_service: service name", d["service"] == "nginx.service")
                check("restart_service: output present", "restarted" in d.get("output", ""))
                check("restart_service: no error", d.get("error") is None)
        finally:
            node_manager.send_intent = orig
    await _run_test("restart_service success", _test)


async def test_restart_service_admin_required():
    async def _test(db):
        node_id = await _setup_node(db, "svc-restart-auth")
        orig = node_manager.send_intent
        node_manager.send_intent = mock_restart_service
        try:
            token = _make_token(role="operator")
            resp = await _request("POST", f"/api/nodes/{node_id}/services/nginx.service/restart", token)
            check("restart_service: operator gets 403", resp.status_code == 403)
        finally:
            node_manager.send_intent = orig
    await _run_test("restart_service admin required", _test)


# ── LIST_CONTAINERS ───────────────────────────────────────────────


async def test_list_containers_success():
    async def _test(db):
        node_id = await _setup_node(db, "c-list")
        orig = node_manager.send_intent
        node_manager.send_intent = mock_list_containers
        try:
            token = _make_token()
            resp = await _request("GET", f"/api/nodes/{node_id}/containers", token)
            check("list_containers: returns 200", resp.status_code == 200)
            if resp.status_code == 200:
                d = resp.json()
                check("list_containers: node_id matches", d["node_id"] == node_id)
                check("list_containers: has containers", len(d["containers"]) == 2)
                if len(d["containers"]) > 0:
                    c = d["containers"][0]
                    check("list_containers: container has id", c.get("id") == "a1b2c3d4e5f6")
                    check("list_containers: container has name", c.get("name") == "web")
                    check("list_containers: container has state", c.get("state") == "running")
        finally:
            node_manager.send_intent = orig
    await _run_test("list_containers success", _test)


async def test_list_containers_not_found():
    async def _test(db):
        token = _make_token()
        resp = await _request("GET", "/api/nodes/nonexistent/containers", token)
        check("list_containers: 404", resp.status_code == 404)
    await _run_test("list_containers 404", _test)


# ── RESTART_CONTAINER ─────────────────────────────────────────────


async def test_restart_container_success():
    async def _test(db):
        node_id = await _setup_node(db, "c-restart")
        orig = node_manager.send_intent
        node_manager.send_intent = mock_restart_container
        try:
            token = _make_token()
            resp = await _request("POST", f"/api/nodes/{node_id}/containers/a1b2c3d4e5f6/restart", token)
            check("restart_container: returns 200", resp.status_code == 200)
            if resp.status_code == 200:
                d = resp.json()
                check("restart_container: node_id matches", d["node_id"] == node_id)
                check("restart_container: container_id",
                      d.get("container_id") == "a1b2c3d4e5f6")
                check("restart_container: output present",
                      "restarted" in d.get("output", ""))
                check("restart_container: no error", d.get("error") is None)
        finally:
            node_manager.send_intent = orig
    await _run_test("restart_container success", _test)


# ── AUTH ──────────────────────────────────────────────────────────


async def test_unauthorized():
    async def _test(db):
        resp = await _request("GET", "/api/nodes/some-id/services")
        check("no auth: 401", resp.status_code == 401)
    await _run_test("unauthorized", _test)


async def test_viewer_forbidden():
    async def _test(db):
        token = _make_token(role="viewer")
        resp = await _request("GET", "/api/nodes/some-id/services", token)
        check("viewer: 403", resp.status_code == 403)
    await _run_test("viewer forbidden", _test)


# ── Run all tests ─────────────────────────────────────────────────

print("\n\U0001f4dd Services & Containers API Tests")
asyncio.run(test_list_services_success())
asyncio.run(test_list_services_not_found())
asyncio.run(test_list_services_not_connected())
asyncio.run(test_list_services_timeout())
asyncio.run(test_service_status_success())
asyncio.run(test_service_status_fail())
asyncio.run(test_restart_service_success())
asyncio.run(test_restart_service_admin_required())
asyncio.run(test_list_containers_success())
asyncio.run(test_list_containers_not_found())
asyncio.run(test_restart_container_success())
asyncio.run(test_unauthorized())
asyncio.run(test_viewer_forbidden())

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
