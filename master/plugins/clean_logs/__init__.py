from __future__ import annotations

"""
Vigile — Clean Logs Plugin (folder format)

Monitors disk usage and auto-proposes log cleanup actions
(Human-in-the-Loop) if space is running low.
"""

import json
import sys
import time
import uuid
from typing import Any

from master.core.plugin_base import PluginBase, hook

# Default settings
DEFAULT_DISK_LIMIT = 85


class CleanLogsPlugin(PluginBase):
    """Class-based clean_logs plugin using PluginBase."""

    plugin_id = "clean_logs"

    # ------------------------------------------------------------------
    # Config schema (classmethod, no instance needed)
    # ------------------------------------------------------------------

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "name": "Clean Logs Utility",
            "description": "Monitors disk usage and auto-proposes log cleanup actions (Human-in-the-Loop) if space is running low.",
            "category": "Maintenance",
            "schema": {
                "disk_threshold": {
                    "type": "integer",
                    "title": "Disk Usage Threshold (%)",
                    "default": DEFAULT_DISK_LIMIT,
                    "description": "Trigger a cleanup proposal if disk usage exceeds this threshold.",
                },
                "cleanup_patterns": {
                    "type": "string",
                    "title": "Cleanup Glob Patterns",
                    "default": "/var/log/*.gz /var/log/*.1 /var/log/nginx/*.gz",
                    "description": "Space-separated list of file paths or patterns to clean up.",
                },
            },
        }

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    @hook("on_status_report")
    async def on_status_report(self, **kwargs: Any) -> None:
        node_id: str = kwargs.get("node_id", "")
        snapshot: dict = kwargs.get("snapshot", {})
        db = kwargs.get("db")

        if not db:
            return

        # 1. Fetch plugin config from DB
        try:
            cursor = await db.execute(
                "SELECT config_json FROM plugins WHERE id = 'clean_logs'"
            )
            row = await cursor.fetchone()
            if not row:
                return
            config = json.loads(row["config_json"])
        except Exception as e:
            print(f"clean_logs: Failed to query config: {e}", file=sys.stderr)
            return

        disk_threshold = config.get("disk_threshold", DEFAULT_DISK_LIMIT)
        cleanup_patterns = config.get("cleanup_patterns", "/var/log/*.gz /var/log/*.1")

        disk = snapshot.get("disk_percent", 0.0)
        if disk <= disk_threshold:
            return

        # 2. Check if there is already a PENDING proposal for this node and action
        try:
            cursor = await db.execute(
                "SELECT id FROM action_proposals WHERE node_id = ? AND action = 'RUN_COMMAND' AND status = 'PENDING'",
                (node_id,),
            )
            existing = await cursor.fetchone()
            if existing:
                # Proposal already exists, skip creating duplicate
                return
        except Exception as e:
            print(f"clean_logs: Failed to query pending proposals: {e}", file=sys.stderr)
            return

        # 3. Create a human-in-the-loop action proposal
        proposal_id = str(uuid.uuid4())
        now = time.time()
        reasoning = f"Disk usage is at {disk:.1f}% (limit: {disk_threshold}%). Proposed deletion of rotated/archived logs to free up space."

        # Shell command params
        params = {"command": f"rm -f {cleanup_patterns}"}
        params_json = json.dumps(params)

        try:
            await db.execute(
                """
                INSERT INTO action_proposals (
                    id, node_id, action, params_json, reasoning, risk_level, status,
                    created_by, created_at, updated_at
                ) VALUES (?, ?, 'RUN_COMMAND', ?, ?, 'LOW', 'PENDING', 'clean_logs_plugin', ?, ?)
                """,
                (proposal_id, node_id, params_json, reasoning, now, now),
            )
            await db.commit()
            print(
                f"clean_logs: Created cleanup proposal {proposal_id} for node {node_id} (Disk: {disk:.1f}%)",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"clean_logs: Failed to insert proposal: {e}", file=sys.stderr)

    @hook("get_supported_actions")
    def get_supported_actions(self, **kwargs: Any) -> list[str]:
        return []


def register(pm):
    from master.core.plugin_base import PluginContext
    ctx = PluginContext(plugin_id="clean_logs", config={}, db=None)
    instance = CleanLogsPlugin(ctx)
    pm.register("get_supported_actions", instance.get_supported_actions, plugin_name="clean_logs")
    pm.register("on_status_report", instance.on_status_report, plugin_name="clean_logs")




