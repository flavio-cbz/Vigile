"""
Tests for Automation Rules REST API.

Covers:
  - GET  /api/admin/automations       → list
  - POST /api/admin/automations       → create
  - GET  /api/admin/automations/{id}  → get
  - PATCH /api/admin/automations/{id} → update
  - DELETE /api/admin/automations/{id}→ delete
  - POST /api/admin/automations/{id}/toggle → toggle
  - GET  /api/admin/automations/{id}/logs   → logs
"""

import json
import time
import uuid

import pytest
from fastapi import status
from httpx import AsyncClient

from master.api import deps
from master.core.automation_engine import AutomationEngine, automation_engine
from master.core.security_manager import SecurityManager
from master.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_headers(security: SecurityManager):
    def _make(role: str = "admin"):
        token = security.create_access_token("test-user", "test_user", role)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
async def client(db):
    from httpx import ASGITransport

    # Override DB dependency
    app.dependency_overrides[deps.get_db] = lambda: db

    # Initialize the engine with the test DB so reload_rules works
    await automation_engine.initialize(db)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(deps.get_db, None)


def make_rule_payload(**overrides) -> dict:
    base = {
        "name": "Test Rule",
        "description": "A test automation rule",
        "trigger_type": "metric_threshold",
        "trigger_config": {"metric": "cpu_percent", "operator": "gt", "threshold": 90},
        "conditions": [],
        "actions": [{"type": "log_message", "message": "CPU critical!"}],
        "cooldown_seconds": 60,
        "target_node_id": None,
        "target_group": None,
    }
    base.update(overrides)
    return base


async def create_rule_in_db(db, name="DB Rule", trigger_type="metric_threshold") -> str:
    rule_id = str(uuid.uuid4())
    now = time.time()
    await db.execute(
        """INSERT INTO automation_rules
           (id, name, description, enabled, trigger_type, trigger_config_json,
            conditions_json, actions_json, cooldown_seconds, created_by, created_at, updated_at)
           VALUES (?, ?, '', 1, ?, '{}', '[]', '[{"type":"log_message","message":"ok"}]', 300, 'test-user', ?, ?)""",
        (rule_id, name, trigger_type, now, now),
    )
    await db.commit()
    return rule_id


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_rules_empty(client: AsyncClient, auth_headers):
    res = await client.get("/api/admin/automations", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == []


@pytest.mark.asyncio
async def test_list_rules_returns_rules(client: AsyncClient, auth_headers, db):
    await create_rule_in_db(db, name="Rule A")
    await create_rule_in_db(db, name="Rule B")
    res = await client.get("/api/admin/automations", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert len(data) == 2
    names = {r["name"] for r in data}
    assert "Rule A" in names
    assert "Rule B" in names


@pytest.mark.asyncio
async def test_list_rules_requires_auth(client: AsyncClient):
    res = await client.get("/api/admin/automations")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_list_rules_operator_allowed(client: AsyncClient, auth_headers, db):
    await create_rule_in_db(db)
    res = await client.get("/api/admin/automations", headers=auth_headers("operator"))
    assert res.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rule_success(client: AsyncClient, auth_headers):
    payload = make_rule_payload()
    res = await client.post("/api/admin/automations", json=payload, headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()
    assert data["name"] == "Test Rule"
    assert data["trigger_type"] == "metric_threshold"
    assert data["enabled"] is True
    assert "id" in data


@pytest.mark.asyncio
async def test_create_rule_operator_forbidden(client: AsyncClient, auth_headers):
    payload = make_rule_payload()
    res = await client.post("/api/admin/automations", json=payload, headers=auth_headers("operator"))
    assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_create_rule_node_state_trigger(client: AsyncClient, auth_headers):
    payload = make_rule_payload(
        trigger_type="node_state",
        trigger_config={"state": "LOST"},
    )
    res = await client.post("/api/admin/automations", json=payload, headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_201_CREATED
    assert res.json()["trigger_type"] == "node_state"


@pytest.mark.asyncio
async def test_create_rule_missing_name_fails(client: AsyncClient, auth_headers):
    payload = make_rule_payload(name="")
    res = await client.post("/api/admin/automations", json=payload, headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_create_rule_invalid_target_node(client: AsyncClient, auth_headers):
    payload = make_rule_payload(target_node_id="00000000-0000-0000-0000-000000000000")
    res = await client.post("/api/admin/automations", json=payload, headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# Get single
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_rule_found(client: AsyncClient, auth_headers, db):
    rule_id = await create_rule_in_db(db, name="Specific Rule")
    res = await client.get(f"/api/admin/automations/{rule_id}", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["id"] == rule_id
    assert res.json()["name"] == "Specific Rule"


@pytest.mark.asyncio
async def test_get_rule_not_found(client: AsyncClient, auth_headers):
    res = await client.get("/api/admin/automations/nonexistent-id", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Update (PATCH)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_rule_name(client: AsyncClient, auth_headers, db):
    rule_id = await create_rule_in_db(db, name="Old Name")
    res = await client.patch(
        f"/api/admin/automations/{rule_id}",
        json={"name": "New Name"},
        headers=auth_headers("admin"),
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["name"] == "New Name"


@pytest.mark.asyncio
async def test_update_rule_cooldown(client: AsyncClient, auth_headers, db):
    rule_id = await create_rule_in_db(db)
    res = await client.patch(
        f"/api/admin/automations/{rule_id}",
        json={"cooldown_seconds": 600},
        headers=auth_headers("admin"),
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["cooldown_seconds"] == 600


@pytest.mark.asyncio
async def test_update_rule_not_found(client: AsyncClient, auth_headers):
    res = await client.patch(
        "/api/admin/automations/nonexistent",
        json={"name": "X"},
        headers=auth_headers("admin"),
    )
    assert res.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_rule(client: AsyncClient, auth_headers, db):
    rule_id = await create_rule_in_db(db)
    res = await client.delete(f"/api/admin/automations/{rule_id}", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_204_NO_CONTENT

    # Verify it's gone
    res2 = await client.get(f"/api/admin/automations/{rule_id}", headers=auth_headers("admin"))
    assert res2.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_delete_rule_operator_forbidden(client: AsyncClient, auth_headers, db):
    rule_id = await create_rule_in_db(db)
    res = await client.delete(f"/api/admin/automations/{rule_id}", headers=auth_headers("operator"))
    assert res.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Toggle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_rule_disables(client: AsyncClient, auth_headers, db):
    rule_id = await create_rule_in_db(db)
    res = await client.post(f"/api/admin/automations/{rule_id}/toggle", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["enabled"] is False


@pytest.mark.asyncio
async def test_toggle_rule_twice_re_enables(client: AsyncClient, auth_headers, db):
    rule_id = await create_rule_in_db(db)
    await client.post(f"/api/admin/automations/{rule_id}/toggle", headers=auth_headers("admin"))
    res = await client.post(f"/api/admin/automations/{rule_id}/toggle", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["enabled"] is True


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_logs_empty(client: AsyncClient, auth_headers, db):
    rule_id = await create_rule_in_db(db)
    res = await client.get(f"/api/admin/automations/{rule_id}/logs", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == []


@pytest.mark.asyncio
async def test_get_logs_with_entry(client: AsyncClient, auth_headers, db):
    rule_id = await create_rule_in_db(db)
    # Insert a log entry
    now = time.time()
    log_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO automation_logs
           (id, rule_id, node_id, triggered_at, status, trigger_data_json, result_json)
           VALUES (?, ?, NULL, ?, 'SUCCESS', '{}', '{}')""",
        (log_id, rule_id, now),
    )
    await db.commit()

    res = await client.get(f"/api/admin/automations/{rule_id}/logs", headers=auth_headers("admin"))
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert len(data) == 1
    assert data[0]["status"] == "SUCCESS"
    assert data[0]["rule_id"] == rule_id


@pytest.mark.asyncio
async def test_get_logs_pagination(client: AsyncClient, auth_headers, db):
    rule_id = await create_rule_in_db(db)
    now = time.time()
    for i in range(5):
        await db.execute(
            "INSERT INTO automation_logs (id, rule_id, triggered_at, status, trigger_data_json, result_json) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), rule_id, now + i, "SUCCESS", "{}", "{}"),
        )
    await db.commit()

    res = await client.get(
        f"/api/admin/automations/{rule_id}/logs?limit=3&offset=0",
        headers=auth_headers("admin"),
    )
    assert res.status_code == status.HTTP_200_OK
    assert len(res.json()) == 3
