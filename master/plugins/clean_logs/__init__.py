from __future__ import annotations

"""
Vigile — Clean Logs Plugin (Package format)

Monitors disk usage and auto-proposes log cleanup actions
(Human-in-the-Loop) if space is running low.
"""

import json
import logging
import re
import time
import uuid
from typing import Any

from master.core.plugin_base import PluginBase, hook

logger = logging.getLogger(__name__)

# Default settings
DEFAULT_DISK_LIMIT = 85
DEFAULT_CLEANUP_PATTERNS = "/var/log/*.gz /var/log/*.1 /var/log/nginx/*.gz"

# Disallow dangerous shell characters in glob patterns
_UNSAFE_PATTERN_REGEX = re.compile(r"[;&|`$()<>\n\r\t]")


def sanitize_cleanup_patterns(patterns: str) -> str:
    """Sanitize space-separated glob patterns to prevent shell injection."""
    if _UNSAFE_PATTERN_REGEX.search(patterns):
        logger.warning("Unsafe shell characters detected in cleanup_patterns: %r. Falling back to default.", patterns)
        return "/var/log/*.gz /var/log/*.1"

    tokens = [t.strip() for t in patterns.split() if t.strip()]
    safe_tokens = []
    for token in tokens:
        # Enforce safe path prefixes (e.g. /var/log/, /var/tmp/, /tmp/) and prevent path traversal
        if token.startswith(("/var/log/", "/var/tmp/", "/tmp/")) and ".." not in token:
            safe_tokens.append(token)
        else:
            logger.warning("Disallowed path token in cleanup_patterns: %r", token)

    return " ".join(safe_tokens) if safe_tokens else "/var/log/*.gz /var/log/*.1"


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
                    "default": DEFAULT_CLEANUP_PATTERNS,
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
        db = kwargs.get("db") or self.db

        if not db or not node_id:
            return

        # 1. Read configuration from PluginContext
        config = self.config or {}
        disk_threshold = config.get("disk_threshold", DEFAULT_DISK_LIMIT)
        raw_patterns = config.get("cleanup_patterns", DEFAULT_CLEANUP_PATTERNS)
        cleanup_patterns = sanitize_cleanup_patterns(str(raw_patterns))

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
                return
        except Exception as e:
            logger.error("clean_logs: Failed to query pending proposals: %s", e)
            return

        # 3. Create a human-in-the-loop action proposal
        proposal_id = str(uuid.uuid4())
        now = time.time()
        reasoning = f"Disk usage is at {disk:.1f}% (limit: {disk_threshold}%). Proposed deletion of rotated/archived logs."

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
            logger.info(
                "clean_logs: Created cleanup proposal %s for node %s (Disk: %.1f%%)",
                proposal_id,
                node_id,
                disk,
            )
        except Exception as e:
            logger.error("clean_logs: Failed to insert proposal: %s", e)

    @hook("get_supported_actions")
    def get_supported_actions(self, **kwargs: Any) -> list[str]:
        return []





