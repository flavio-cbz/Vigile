"""
Tests for the docker plugin container-action POST route (C2 hardened).

Contract under test:
- ``restart`` → dispatches ``RESTART_CONTAINER`` (MEDIUM risk).
- ``start`` → dispatches ``START_CONTAINER`` (LOW risk).
- ``stop`` → requires admin role (HIGH risk); operator gets HTTP 403.
- ``delete`` → requires admin role (CRITICAL risk); operator gets HTTP 403;
  passes ``container_name`` when provided.
- invalid action (not in {stop, start, restart, delete}) → HTTP 400.
- missing ``node_id`` in body → HTTP 400.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from master.core.plugin_base import PluginContext
from master.plugins.docker import DockerPlugin


def _make_plugin() -> DockerPlugin:
    return DockerPlugin(PluginContext(plugin_id="docker", config={}, db=None))


class _FakeDispatcher:
    """ApprovedProposalDispatcher stand-in recording dispatch_admin_action calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    async def dispatch_admin_action(
        self,
        node_id: str,
        action: str,
        params: dict[str, Any],
        user_id: str,
        db: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append((node_id, action, params, user_id, db, kwargs))
        return {"success": True, "output": f"Container {params['container_id']} {action.lower()}"}


@pytest.mark.asyncio
async def test_container_action_restart_dispatches_intent():
    """restart → RESTART_CONTAINER dispatched with node_id/container_id/user."""
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    result = await plugin.container_action_route(
        container_id="abc123",
        action="restart",
        body={"node_id": "node-1"},
        claims={"sub": "test-user", "role": "operator"},
        db=None,
        dispatcher=dispatcher,
    )

    assert len(dispatcher.calls) == 1
    node_id, intent, params, user_id, db, kwargs = dispatcher.calls[0]
    assert node_id == "node-1"
    assert intent == "RESTART_CONTAINER"
    assert params == {"container_id": "abc123"}
    assert user_id == "test-user"
    assert db is None
    assert kwargs["intent_timeout"] == 15.0
    assert kwargs["risk_level"] == "MEDIUM"
    assert result["success"] is True


@pytest.mark.asyncio
async def test_container_action_start_dispatches_intent():
    """start → START_CONTAINER dispatched with LOW risk."""
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    result = await plugin.container_action_route(
        container_id="abc123",
        action="start",
        body={"node_id": "node-1"},
        claims={"sub": "test-user", "role": "operator"},
        db=None,
        dispatcher=dispatcher,
    )

    assert len(dispatcher.calls) == 1
    node_id, intent, params, user_id, db, kwargs = dispatcher.calls[0]
    assert intent == "START_CONTAINER"
    assert kwargs["risk_level"] == "LOW"
    assert result["success"] is True


@pytest.mark.asyncio
async def test_container_action_stop_requires_admin():
    """stop with role != admin → HTTP 403; admin → STOP_CONTAINER (HIGH risk)."""
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    # Operator rejected
    with pytest.raises(HTTPException) as exc:
        await plugin.container_action_route(
            container_id="abc123",
            action="stop",
            body={"node_id": "node-1"},
            claims={"sub": "operator-user", "role": "operator"},
            db=None,
            dispatcher=dispatcher,
        )
    assert exc.value.status_code == 403
    assert "réservée aux administrateurs" in exc.value.detail
    assert dispatcher.calls == []

    # Admin accepted
    result = await plugin.container_action_route(
        container_id="abc123",
        action="stop",
        body={"node_id": "node-1"},
        claims={"sub": "admin-user", "role": "admin"},
        db=None,
        dispatcher=dispatcher,
    )
    assert len(dispatcher.calls) == 1
    node_id, intent, params, user_id, db, kwargs = dispatcher.calls[0]
    assert intent == "STOP_CONTAINER"
    assert kwargs["risk_level"] == "HIGH"
    assert result["success"] is True


@pytest.mark.asyncio
async def test_container_action_delete_requires_admin_and_passes_name():
    """delete with role != admin → HTTP 403; admin → DELETE_CONTAINER (CRITICAL risk)."""
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    # Operator rejected
    with pytest.raises(HTTPException) as exc:
        await plugin.container_action_route(
            container_id="abc123",
            action="delete",
            body={"node_id": "node-1", "container_name": "web_nginx"},
            claims={"sub": "operator-user", "role": "operator"},
            db=None,
            dispatcher=dispatcher,
        )
    assert exc.value.status_code == 403
    assert dispatcher.calls == []

    # Admin accepted with container_name
    result = await plugin.container_action_route(
        container_id="abc123",
        action="delete",
        body={"node_id": "node-1", "container_name": "web_nginx"},
        claims={"sub": "admin-user", "role": "admin"},
        db=None,
        dispatcher=dispatcher,
    )
    assert len(dispatcher.calls) == 1
    node_id, intent, params, user_id, db, kwargs = dispatcher.calls[0]
    assert intent == "DELETE_CONTAINER"
    assert params == {"container_id": "abc123", "container_name": "web_nginx"}
    assert kwargs["risk_level"] == "CRITICAL"
    assert result["success"] is True


@pytest.mark.asyncio
async def test_container_action_invalid_action_400():
    """Action hors de {stop, start, restart, delete} → HTTP 400 (message français)."""
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    with pytest.raises(HTTPException) as exc:
        await plugin.container_action_route(
            container_id="abc123",
            action="destroy",
            body={"node_id": "node-1"},
            claims={"sub": "test-user", "role": "admin"},
            db=None,
            dispatcher=dispatcher,
        )
    assert exc.value.status_code == 400
    assert "invalide" in exc.value.detail
    assert dispatcher.calls == []


@pytest.mark.asyncio
async def test_container_action_missing_node_id_400():
    """Corps sans node_id → HTTP 400 (message français), rien n'est dispatché."""
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    with pytest.raises(HTTPException) as exc:
        await plugin.container_action_route(
            container_id="abc123",
            action="restart",
            body={},
            claims={"sub": "test-user", "role": "admin"},
            db=None,
            dispatcher=dispatcher,
        )
    assert exc.value.status_code == 400
    assert "node_id" in exc.value.detail
    assert dispatcher.calls == []


@pytest.mark.asyncio
async def test_container_action_audit_security_incident_on_rejection(db):
    """Rejection of delete by operator writes AuditAction.SECURITY_INCIDENT to audit_log."""
    import json
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    with pytest.raises(HTTPException) as exc:
        await plugin.container_action_route(
            container_id="abc123",
            action="delete",
            body={"node_id": "node-1"},
            claims={"sub": "operator-attacker", "role": "operator"},
            db=db,
            dispatcher=dispatcher,
        )
    assert exc.value.status_code == 403

    # Verify audit_log entry
    async with db.execute(
        "SELECT action, user_id, node_id, details_json FROM audit_log WHERE action = 'SECURITY_INCIDENT'"
    ) as cur:
        row = await cur.fetchone()

    assert row is not None
    assert row[0] == "SECURITY_INCIDENT"
    assert row[1] == "operator-attacker"
    assert row[2] == "node-1"
    details = json.loads(row[3])
    assert details["reason"] == "unauthorized_role_attempt"
    assert details["action"] == "delete"


@pytest.mark.asyncio
async def test_container_action_invalid_container_id_regex():
    """Invalid container_id format raises HTTP 400."""
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    invalid_ids = ["ab", "../../sh", "id with spaces", "semi;colon"]
    for cid in invalid_ids:
        with pytest.raises(HTTPException) as exc:
            await plugin.container_action_route(
                container_id=cid,
                action="restart",
                body={"node_id": "node-1"},
                claims={"sub": "admin-user", "role": "admin"},
                db=None,
                dispatcher=dispatcher,
            )
        assert exc.value.status_code == 400
        assert "Format de container_id invalide" in exc.value.detail


@pytest.mark.asyncio
async def test_container_action_delete_requires_container_name():
    """delete without container_name raises HTTP 400."""
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    with pytest.raises(HTTPException) as exc:
        await plugin.container_action_route(
            container_id="abc123",
            action="delete",
            body={"node_id": "node-1"},
            claims={"sub": "admin-user", "role": "admin"},
            db=None,
            dispatcher=dispatcher,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "container_name is required for delete"


@pytest.mark.asyncio
async def test_container_action_audit_on_failure(db):
    """Failed container action logs FAILED status to audit chain."""
    import json
    plugin = _make_plugin()

    class _FailingDispatcher:
        async def dispatch_admin_action(self, *args, **kwargs):
            return {"success": False, "error": "Docker socket timeout"}

    result = await plugin.container_action_route(
        container_id="abc123",
        action="restart",
        body={"node_id": "node-1"},
        claims={"sub": "admin-user", "role": "admin"},
        db=db,
        dispatcher=_FailingDispatcher(),
    )
    assert result["success"] is False
    assert result["error"] == "Docker socket timeout"

    async with db.execute(
        "SELECT action, details_json FROM audit_log WHERE action = 'RESTART_CONTAINER' ORDER BY id DESC LIMIT 1"
    ) as cur:
        row = await cur.fetchone()

    assert row is not None
    details = json.loads(row[1])
    assert details["status"] == "FAILED"
    assert details["error"] == "Docker socket timeout"