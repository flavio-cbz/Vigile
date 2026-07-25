from __future__ import annotations

"""
Tests for example plugins (Clean Logs).
"""

import json
import aiosqlite
import pytest

from master.core.plugin_manager import PluginManager
from master.plugins.clean_logs import register as register_clean_logs


@pytest.mark.asyncio
async def test_clean_logs_plugin(db: aiosqlite.Connection):
    # 1. Enable the plugin in the database first
    await db.execute(
        "INSERT OR IGNORE INTO plugins (id, enabled, config_json) VALUES (?, 1, ?)",
        ("clean_logs", json.dumps({"disk_threshold": 75, "cleanup_patterns": "/var/log/*.1"})),
    )
    # Ensure test-node exists in nodes
    await db.execute(
        "INSERT OR IGNORE INTO nodes (id, name, hostname, state, created_at, updated_at) VALUES (?, ?, ?, 'CONNECTED', 0, 0)",
        ("test-node-clean", "Clean Node", "clean-host"),
    )
    await db.commit()

    pm = PluginManager()
    await pm.initialize(db, sandbox=False)
    register_clean_logs(pm)

    # Trigger with disk above threshold (80% > 75%)
    snapshot = {"disk_percent": 80.0}
    await pm.async_call("on_status_report", node_id="test-node-clean", snapshot=snapshot, db=db)

    # Verify a PENDING proposal was created in the DB
    async with db.execute(
        "SELECT reasoning, params_json FROM action_proposals WHERE node_id = 'test-node-clean' AND status = 'PENDING'"
    ) as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert "Disk usage is at 80.0%" in row["reasoning"]
        params = json.loads(row["params_json"])
        assert params["command"] == "rm -f /var/log/*.1"
