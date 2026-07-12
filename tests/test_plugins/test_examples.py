"""
Tests for example plugins (Discord Alert, Slack Alert, Clean Logs).
"""

import json
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from master.core.plugin_manager import PluginManager
from master.plugins.clean_logs import register as register_clean_logs
from master.plugins.discord_alert import register as register_discord
from master.plugins.slack_alert import register as register_slack


@pytest.mark.asyncio
async def test_discord_alert_plugin(db: aiosqlite.Connection):
    # 1. Enable the plugin in the database first
    await db.execute(
        "INSERT OR IGNORE INTO plugins (id, enabled, config_json) VALUES (?, 1, ?)",
        (
            "discord_alert",
            json.dumps(
                {
                    "webhook_url": "https://discord.com/api/webhooks/mock-url",
                    "cpu_threshold": 80,
                    "mem_threshold": 80,
                }
            ),
        ),
    )
    await db.commit()

    pm = PluginManager()
    await pm.initialize(db, sandbox=False)
    register_discord(pm)

    # 2. Trigger with CPU above threshold
    snapshot = {"cpu_percent": 95.0, "mem_percent": 50.0}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 204

        await pm.async_call("on_status_report", node_id="test-node", snapshot=snapshot, db=db)

        assert mock_post.called
        call_args = mock_post.call_args[1]
        assert "CPU critical" in call_args["json"]["content"]


@pytest.mark.asyncio
async def test_slack_alert_plugin(db: aiosqlite.Connection):
    # 1. Enable the plugin in the database first
    await db.execute(
        "INSERT OR IGNORE INTO plugins (id, enabled, config_json) VALUES (?, 1, ?)",
        (
            "slack_alert",
            json.dumps(
                {
                    "webhook_url": "https://hooks.slack.com/services/mock-url",
                    "cpu_threshold": 80,
                    "mem_threshold": 80,
                }
            ),
        ),
    )
    await db.commit()

    pm = PluginManager()
    await pm.initialize(db, sandbox=False)
    register_slack(pm)

    # Trigger with memory above threshold
    snapshot = {"cpu_percent": 40.0, "mem_percent": 90.0}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200

        await pm.async_call("on_status_report", node_id="test-node", snapshot=snapshot, db=db)

        assert mock_post.called
        call_args = mock_post.call_args[1]
        assert "blocks" in call_args["json"]
        assert "Mémoire critique" in call_args["json"]["blocks"][1]["text"]["text"]


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
