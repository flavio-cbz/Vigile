import asyncio
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from master.core.node_manager import NodeManager


class _DummyWS:
    def __init__(self):
        self.sent_messages = []
        self.closed = False

    async def send_json(self, data: dict):
        self.sent_messages.append(data)

    async def close(self, code: int = 1000, reason: str = ""):
        self.closed = True


@pytest.mark.asyncio
async def test_cache_update_creates_audit_entry(db: aiosqlite.Connection):
    """A CACHE_REFRESH audit entry should be created after a cache write."""
    nm = NodeManager()

    async def mock_send_intent(node_id, intent, *, timeout=30.0, intent_max_age=None):
        if intent["action"] == "LIST_SERVICES":
            return {
                "success": True,
                "output": '[{"name": "nginx.service", "state": "active", "status": "running"}]',
            }
        elif intent["action"] == "LIST_CONTAINERS":
            return {
                "success": True,
                "output": '[{"id": "abc123", "name": "web", "image": "nginx", "state": "running"}]',
            }
        return {"success": False}

    with (
        patch.object(nm, "send_intent", mock_send_intent),
        patch("master.core.node_manager.get_db_conn", return_value=db),
    ):
        ws = _DummyWS()
        await nm.register_connection("test-node-audit", ws)
        await nm.update_all_nodes_cache(node_id="test-node-audit")

        # Verify audit trail exists
        async with db.execute(
            "SELECT action, node_id, details_json FROM audit_log WHERE action = ?",
            ("CACHE_REFRESH",),
        ) as cursor:
            rows = await cursor.fetchall()
            assert len(rows) >= 1, "Expected at least one CACHE_REFRESH audit entry"
            row = rows[0]
            assert row["node_id"] == "test-node-audit"


@pytest.mark.asyncio
async def test_cache_update_audit_details(db: aiosqlite.Connection):
    """Audit entry should correctly reflect which cache fields were updated."""
    nm = NodeManager()
    call_count = 0

    async def mock_send_intent(node_id, intent, *, timeout=30.0, intent_max_age=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Services request returns valid data
            return {
                "success": True,
                "output": '[{"name": "nginx.service", "state": "active", "status": "running"}]',
            }
        # Container request fails
        return {"success": False}

    with (
        patch.object(nm, "send_intent", mock_send_intent),
        patch("master.core.node_manager.get_db_conn", return_value=db),
    ):
        ws = _DummyWS()
        await nm.register_connection("test-node-details", ws)
        await nm.update_all_nodes_cache(node_id="test-node-details")

        async with db.execute(
            "SELECT details_json FROM audit_log WHERE action = ? AND node_id = ?",
            ("CACHE_REFRESH", "test-node-details"),
        ) as cursor:
            rows = await cursor.fetchall()
            assert len(rows) >= 1
            import json

            details = json.loads(rows[0]["details_json"])
            assert details["services_updated"] is True
            assert details["containers_updated"] is False


@pytest.mark.asyncio
async def test_cache_update_no_write_no_audit(db: aiosqlite.Connection):
    """If no cache data was written, no CACHE_REFRESH audit entry should be created."""
    nm = NodeManager()

    async def mock_send_intent(node_id, intent, *, timeout=30.0, intent_max_age=None):
        # Return success but with no data (output not parseable JSON)
        return {"success": True, "output": "not-json"}

    with (
        patch.object(nm, "send_intent", mock_send_intent),
        patch("master.core.node_manager.get_db_conn", return_value=db),
    ):
        ws = _DummyWS()
        await nm.register_connection("test-node-no-cache", ws)
        await nm.update_all_nodes_cache(node_id="test-node-no-cache")

        async with db.execute(
            "SELECT COUNT(*) as cnt FROM audit_log WHERE action = ? AND node_id = ?",
            ("CACHE_REFRESH", "test-node-no-cache"),
        ) as cursor:
            row = await cursor.fetchone()
            assert row["cnt"] == 0, "No audit entry expected when no cache data was written"
