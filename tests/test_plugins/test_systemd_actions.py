"""
Tests for the systemd plugin service-action POST route (C2 hardened).

Contract under test:
- ``restart`` → dispatches ``RESTART_SERVICE`` (MEDIUM risk).
- ``start`` → dispatches ``START_SERVICE`` (LOW risk).
- ``stop`` → requires admin role; operator gets HTTP 403.
- ``stop`` on protected service (ssh, docker, systemd-resolved, etc.) → HTTP 403 even for admin.
- ``stop`` on unprotected service (nginx, redis) with admin → dispatches ``STOP_SERVICE`` (HIGH risk).
- invalid action (not in {stop, start, restart}) → HTTP 400.
- missing ``node_id`` in body → HTTP 400.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from master.core.plugin_base import PluginContext
from master.plugins.systemd import SystemdPlugin


def _make_plugin() -> SystemdPlugin:
    return SystemdPlugin(PluginContext(plugin_id="systemd", config={}, db=None))


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
        return {"success": True, "output": f"Service {params['service']} {action.lower()}"}


@pytest.mark.asyncio
async def test_service_action_restart_dispatches_intent():
    """restart → RESTART_SERVICE dispatched with node_id/service/user."""
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    result = await plugin.service_action_route(
        service_name="nginx.service",
        action="restart",
        body={"node_id": "node-1"},
        claims={"sub": "test-user", "role": "operator"},
        db=None,
        dispatcher=dispatcher,
    )

    assert len(dispatcher.calls) == 1
    node_id, intent, params, user_id, db, kwargs = dispatcher.calls[0]
    assert node_id == "node-1"
    assert intent == "RESTART_SERVICE"
    assert params == {"service": "nginx.service"}
    assert user_id == "test-user"
    assert db is None
    assert kwargs["intent_timeout"] == 15.0
    assert kwargs["risk_level"] == "MEDIUM"
    assert result["success"] is True


@pytest.mark.asyncio
async def test_service_action_start_dispatches_intent():
    """start → START_SERVICE dispatched with LOW risk."""
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    result = await plugin.service_action_route(
        service_name="nginx.service",
        action="start",
        body={"node_id": "node-1"},
        claims={"sub": "test-user", "role": "operator"},
        db=None,
        dispatcher=dispatcher,
    )

    assert len(dispatcher.calls) == 1
    node_id, intent, params, user_id, db, kwargs = dispatcher.calls[0]
    assert intent == "START_SERVICE"
    assert kwargs["risk_level"] == "LOW"
    assert result["success"] is True


@pytest.mark.asyncio
async def test_service_action_stop_requires_admin():
    """stop with role != admin → HTTP 403."""
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    with pytest.raises(HTTPException) as exc:
        await plugin.service_action_route(
            service_name="nginx.service",
            action="stop",
            body={"node_id": "node-1"},
            claims={"sub": "operator-user", "role": "operator"},
            db=None,
            dispatcher=dispatcher,
        )
    assert exc.value.status_code == 403
    assert "réservée aux administrateurs" in exc.value.detail
    assert dispatcher.calls == []


@pytest.mark.asyncio
async def test_service_action_stop_protected_services_blocked():
    """stop on protected services (ssh.service, sshd, docker, etc.) → HTTP 403 even for admin."""
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    protected_samples = [
        "ssh.service",
        "ssh",
        "sshd.service",
        "docker.service",
        "systemd-resolved.service",
        "NetworkManager.service",
        "vigile-worker.service",
    ]

    for svc in protected_samples:
        with pytest.raises(HTTPException) as exc:
            await plugin.service_action_route(
                service_name=svc,
                action="stop",
                body={"node_id": "node-1"},
                claims={"sub": "admin-user", "role": "admin"},
                db=None,
                dispatcher=dispatcher,
            )
        assert exc.value.status_code == 403
        assert "protégé" in exc.value.detail

    assert dispatcher.calls == []


@pytest.mark.asyncio
async def test_service_action_stop_unprotected_admin_success():
    """stop on unprotected service with admin role → STOP_SERVICE (HIGH risk)."""
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    result = await plugin.service_action_route(
        service_name="nginx.service",
        action="stop",
        body={"node_id": "node-1"},
        claims={"sub": "admin-user", "role": "admin"},
        db=None,
        dispatcher=dispatcher,
    )

    assert len(dispatcher.calls) == 1
    node_id, intent, params, user_id, db, kwargs = dispatcher.calls[0]
    assert intent == "STOP_SERVICE"
    assert params == {"service": "nginx.service"}
    assert kwargs["risk_level"] == "HIGH"
    assert result["success"] is True


@pytest.mark.asyncio
async def test_service_action_invalid_action_400():
    """Action hors de {stop, start, restart} → HTTP 400 (message français)."""
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    with pytest.raises(HTTPException) as exc:
        await plugin.service_action_route(
            service_name="nginx.service",
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
async def test_service_action_missing_node_id_400():
    """Corps sans node_id → HTTP 400 (message français), rien n'est dispatché."""
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    with pytest.raises(HTTPException) as exc:
        await plugin.service_action_route(
            service_name="nginx.service",
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
async def test_service_action_audit_security_incident_on_protected(db):
    """Attempting to stop ssh.service writes AuditAction.SECURITY_INCIDENT to audit_log."""
    import json
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    with pytest.raises(HTTPException) as exc:
        await plugin.service_action_route(
            service_name="ssh.service",
            action="stop",
            body={"node_id": "node-1"},
            claims={"sub": "admin-user", "role": "admin"},
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
    assert row[1] == "admin-user"
    assert row[2] == "node-1"
    details = json.loads(row[3])
    assert details["reason"] == "attempt_to_stop_protected_service"
    assert details["service"] == "ssh.service"


@pytest.mark.asyncio
async def test_service_action_stop_socket_units_blocked():
    """Stopping .socket, .timer, or .target of protected services is blocked with HTTP 403."""
    plugin = _make_plugin()
    dispatcher = _FakeDispatcher()

    socket_units = [
        "docker.socket",
        "ssh.socket",
        "systemd-journald.socket",
        "docker.timer",
        "docker.target",
        "docker.slice",
    ]
    for unit in socket_units:
        with pytest.raises(HTTPException) as exc:
            await plugin.service_action_route(
                service_name=unit,
                action="stop",
                body={"node_id": "node-1"},
                claims={"sub": "admin-user", "role": "admin"},
                db=None,
                dispatcher=dispatcher,
            )
        assert exc.value.status_code == 403
        assert "protégé" in exc.value.detail


@pytest.mark.asyncio
async def test_service_action_audit_on_failure(db):
    """Failed service action logs FAILED status to audit chain."""
    import json
    plugin = _make_plugin()

    class _FailingDispatcher:
        async def dispatch_admin_action(self, *args, **kwargs):
            return {"success": False, "error": "Job failed with result 'failed'"}

    result = await plugin.service_action_route(
        service_name="nginx.service",
        action="restart",
        body={"node_id": "node-1"},
        claims={"sub": "admin-user", "role": "admin"},
        db=db,
        dispatcher=_FailingDispatcher(),
    )
    assert result["success"] is False
    assert result["error"] == "Job failed with result 'failed'"

    async with db.execute(
        "SELECT action, details_json FROM audit_log WHERE action = 'RESTART_SERVICE' ORDER BY id DESC LIMIT 1"
    ) as cur:
        row = await cur.fetchone()

    assert row is not None
    details = json.loads(row[1])
    assert details["status"] == "FAILED"
    assert details["error"] == "Job failed with result 'failed'"