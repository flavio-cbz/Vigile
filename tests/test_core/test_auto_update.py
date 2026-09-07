from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from master.auto_update import (
    _dispatch_node_update,
    _process_worker_updates,
    _wait_for_node_update,
    is_newer_version,
    parse_semver,
)
from master.core.audit import AuditAction
from master.core.enums import WorkerAction


def test_parse_semver():
    assert parse_semver("v1.1.0") == (1, 1, 0)
    assert parse_semver("1.2.3") == (1, 2, 3)
    assert parse_semver("v2.0.0-rc1") == (2, 0, 0)
    assert parse_semver("") == (0, 0, 0)
    assert parse_semver(None) == (0, 0, 0)
    assert parse_semver("invalid") == (0, 0, 0)


def test_is_newer_version():
    assert is_newer_version("1.2.0", "1.1.0") is True
    assert is_newer_version("v1.2.0", "1.1.0") is True
    assert is_newer_version("1.1.1", "1.1.0") is True
    assert is_newer_version("1.1.0", "1.1.0") is False
    assert is_newer_version("v1.1.0", "1.1.0") is False
    assert is_newer_version("1.0.9", "1.1.0") is False
    assert is_newer_version(None, "1.1.0") is False
    assert is_newer_version("1.1.0", "") is True
    assert is_newer_version("1.1.0", None) is True


@pytest.mark.asyncio
async def test_dispatch_node_update_success(db):
    nm = MagicMock()
    settings_obj = MagicMock()
    settings_obj.DEFAULT_TIMEOUT = 30.0

    node = {
        "id": "node-123",
        "name": "server-1",
        "os": "linux",
        "arch": "x86_64",
    }

    with patch("master.auto_update.ApprovedProposalDispatcher") as mock_dispatcher_cls, \
         patch("master.auto_update.log_action", new_callable=AsyncMock) as mock_log_action:

        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch_admin_action = AsyncMock(return_value={"success": True, "output": "ok"})
        mock_dispatcher_cls.return_value = mock_dispatcher

        success = await _dispatch_node_update(node, nm, settings_obj, db)
        assert success is True

        mock_dispatcher.dispatch_admin_action.assert_called_once()
        args, kwargs = mock_dispatcher.dispatch_admin_action.call_args
        assert args[0] == "node-123"
        assert args[1] == WorkerAction.UPDATE_WORKER
        assert args[2]["os"] == "linux"
        assert args[2]["arch"] == "amd64"
        assert args[2]["binary_url"] == "/api/nodes/binary/linux/amd64/worker"

        mock_log_action.assert_called_once()
        log_args, log_kwargs = mock_log_action.call_args
        assert log_kwargs["action"] == AuditAction.AUTO_UPDATE_WORKER.value
        assert log_kwargs["node_id"] == "node-123"


@pytest.mark.asyncio
async def test_process_worker_updates_up_to_date(db):
    nm = MagicMock()
    settings_obj = MagicMock()
    settings_obj.auto_update_workers = True

    now = 1700000000.0
    await db.execute(
        "INSERT INTO nodes (id, name, worker_version, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("node-1", "test-node", "1.2.0", "CONNECTED", now, now),
    )
    await db.commit()

    nm.is_connected = AsyncMock(return_value=True)

    with patch("master.auto_update._fetch_manifest", new_callable=AsyncMock) as mock_fetch, \
         patch("master.auto_update._dispatch_node_update", new_callable=AsyncMock) as mock_dispatch:

        mock_fetch.return_value = {"version": "v1.2.0"}
        await _process_worker_updates(db, nm, settings_obj)

        mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_process_worker_updates_canary_success(db):
    nm = MagicMock()
    settings_obj = MagicMock()
    settings_obj.auto_update_workers = True
    settings_obj.auto_update_canary = True

    now = 1700000000.0
    await db.execute(
        "INSERT INTO nodes (id, name, worker_version, state, os, arch, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("node-1", "node-one", "1.0.0", "CONNECTED", "linux", "amd64", now, now),
    )
    await db.execute(
        "INSERT INTO nodes (id, name, worker_version, state, os, arch, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("node-2", "node-two", "1.0.0", "CONNECTED", "linux", "arm64", now, now),
    )
    await db.commit()

    nm.is_connected = AsyncMock(return_value=True)

    with patch("master.auto_update._fetch_manifest", new_callable=AsyncMock) as mock_fetch, \
         patch("master.auto_update._dispatch_node_update", new_callable=AsyncMock) as mock_dispatch, \
         patch("master.auto_update._wait_for_node_update", new_callable=AsyncMock) as mock_wait, \
         patch("asyncio.sleep", new_callable=AsyncMock):

        mock_fetch.return_value = {"version": "v1.2.0"}
        mock_dispatch.return_value = True
        mock_wait.return_value = True  # Canary succeeds

        await _process_worker_updates(db, nm, settings_obj)

        # Both nodes should have been updated
        assert mock_dispatch.call_count == 2
        mock_wait.assert_called_once_with("node-1", nm, db, "v1.2.0", timeout=120.0)


@pytest.mark.asyncio
async def test_process_worker_updates_canary_failure_aborts(db):
    nm = MagicMock()
    settings_obj = MagicMock()
    settings_obj.auto_update_workers = True
    settings_obj.auto_update_canary = True

    now = 1700000000.0
    await db.execute(
        "INSERT INTO nodes (id, name, worker_version, state, os, arch, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("node-1", "node-one", "1.0.0", "CONNECTED", "linux", "amd64", now, now),
    )
    await db.execute(
        "INSERT INTO nodes (id, name, worker_version, state, os, arch, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("node-2", "node-two", "1.0.0", "CONNECTED", "linux", "arm64", now, now),
    )
    await db.commit()

    nm.is_connected = AsyncMock(return_value=True)

    with patch("master.auto_update._fetch_manifest", new_callable=AsyncMock) as mock_fetch, \
         patch("master.auto_update._dispatch_node_update", new_callable=AsyncMock) as mock_dispatch, \
         patch("master.auto_update._wait_for_node_update", new_callable=AsyncMock) as mock_wait:

        mock_fetch.return_value = {"version": "v1.2.0"}
        mock_dispatch.return_value = True
        mock_wait.return_value = False  # Canary fails or times out!

        await _process_worker_updates(db, nm, settings_obj)

        # Only the canary node was dispatched, 2nd node was spared
        assert mock_dispatch.call_count == 1
        call_args, _ = mock_dispatch.call_args
        assert call_args[0]["id"] == "node-1"
