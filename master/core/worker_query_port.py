"""
Vigile — WorkerQueryPort (Read-Only Worker Query Port)

Provides a safe, read-only interface to query connected Workers
via whitelisted intents. Only exposes read-only query actions
(GET_STATS, LIST_SERVICES, LIST_CONTAINERS, READ_LOGS, LIST_LOG_SOURCES,
LOG_HISTOGRAM, DISK_SCAN, etc.) — no mutation intents allowed.

Strict DI: receives NodeManager in constructor, never reads settings
or os.getenv.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Read-only intent whitelist
# ---------------------------------------------------------------------------

ALLOWED_ACTIONS: frozenset[str] = frozenset({
    "LIST_STATS",
    "GET_STATS",
    "LIST_SERVICES",
    "LIST_CONTAINERS",
    "READ_LOGS",
    "READ_LOGS_SERVICE",
    "STATUS_SERVICE",
    "DISK_SCAN",
    "LIST_LOG_FILES",
    "LIST_LOG_SOURCES",
    "LOG_HISTOGRAM",
})


# ---------------------------------------------------------------------------
# WorkerQueryPort
# ---------------------------------------------------------------------------

class WorkerQueryPort:
    """Read-only port for querying connected Workers via whitelisted intents.

    Every method:
      - Validates the node is connected before sending the intent
      - Wraps the intent in the standard format with a uuid4 intent_id
      - Calls the private ``_send_intent`` on NodeManager (no mutation pathway)
      - Returns the result from the Worker (typed per method)
    """

    def __init__(self, node_manager: Any) -> None:
        self._node_manager = node_manager

    async def query(
        self,
        node_id: str,
        action: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send a read-only query intent to a connected Worker.

        Args:
            node_id: UUID of the target Worker.
            action: Intent action name — must be in ``ALLOWED_ACTIONS``.
            params: Optional parameters for the query.
            timeout: Optional per-query timeout in seconds.

        Returns:
            The raw result dict returned by the Worker.

        Raises:
            ValueError: If the action is not in the read-only whitelist.
            RuntimeError: If the node is not currently connected.
            TimeoutError: If the Worker does not respond within the timeout.
        """
        action_str = str(action)
        if action_str not in ALLOWED_ACTIONS:
            raise ValueError(
                f"Action {action!r} is not allowed via WorkerQueryPort. "
                f"Allowed actions: {sorted(ALLOWED_ACTIONS)}"
            )

        if not await self._node_manager.is_connected(node_id):
            raise RuntimeError(f"Node {node_id} is not connected")

        intent: dict[str, Any] = {
            "intent_id": str(uuid.uuid4()),
            "action": action_str,
            "params": params or {},
        }
        kwargs: dict[str, Any] = {}
        if timeout is not None:
            kwargs["timeout"] = timeout
        return await self._node_manager._send_intent(node_id, intent, **kwargs)

    async def get_stats(self, node_id: str) -> dict[str, Any]:
        """Send GET_STATS intent to a connected Worker."""
        return await self.query(node_id, "GET_STATS")

    async def list_services(self, node_id: str) -> list[dict[str, Any]]:
        """Send LIST_SERVICES intent to a connected Worker."""
        result = await self.query(node_id, "LIST_SERVICES")
        return result.get("output", [])

    async def list_containers(self, node_id: str) -> list[dict[str, Any]]:
        """Send LIST_CONTAINERS intent to a connected Worker."""
        result = await self.query(node_id, "LIST_CONTAINERS")
        return result.get("output", [])

    async def read_logs(
        self,
        node_id: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send READ_LOGS intent to a connected Worker."""
        return await self.query(node_id, "READ_LOGS", params)

    async def list_log_files(
        self,
        node_id: str,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send LIST_LOG_FILES intent to a connected Worker."""
        return await self.query(node_id, "LIST_LOG_FILES", timeout=timeout)
