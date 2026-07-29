"""
Vigile — WorkerQueryPort (Read-Only Worker Query Port)

Provides a safe, read-only interface to query connected Workers
via whitelisted intents. Only exposes LIST_STATS, LIST_SERVICES,
LIST_CONTAINERS, and READ_LOGS actions — no mutation intents allowed.

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
    "LIST_SERVICES",
    "LIST_CONTAINERS",
    "READ_LOGS",
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

    Usage::

        port = WorkerQueryPort(node_manager)
        services = await port.list_services("node-uuid-1234")
        containers = await port.list_containers("node-uuid-5678")
    """

    # Class-level constant for action allowlist (also accessible via is_allowed)
    ALLOWED_ACTIONS: frozenset[str] = ALLOWED_ACTIONS

    def __init__(self, node_manager: Any) -> None:
        """Initialize with NodeManager.

        Args:
            node_manager: The NodeManager instance used to dispatch intents.
                Strict DI — no settings/env/filesystem access.
        """
        self._node_manager = node_manager

    # ------------------------------------------------------------------
    # Allowlist check
    # ------------------------------------------------------------------

    @classmethod
    def is_allowed(cls, action: str) -> bool:
        """Check whether *action* is in the read-only whitelist.

        Returns:
            True if the action is a read-only query (LIST_STATS,
            LIST_SERVICES, LIST_CONTAINERS, READ_LOGS).
        """
        return action in cls.ALLOWED_ACTIONS

    # ------------------------------------------------------------------
    # Read-only query methods
    # ------------------------------------------------------------------

    async def get_stats(self, node_id: str) -> dict[str, Any]:
        """Send LIST_STATS intent to a connected Worker.

        Args:
            node_id: UUID of the target Worker.

        Returns:
            Dict with CPU / memory / disk metrics from the Worker.

        Raises:
            RuntimeError: If the node is not connected.
        """
        if not await self._node_manager.is_connected(node_id):
            raise RuntimeError(f"Node {node_id} is not connected")

        intent: dict[str, Any] = {
            "intent_id": str(uuid.uuid4()),
            "action": "LIST_STATS",
            "params": {},
        }
        return await self._node_manager._send_intent(node_id, intent)

    async def list_services(self, node_id: str) -> list[dict[str, Any]]:
        """Send LIST_SERVICES intent to a connected Worker.

        Args:
            node_id: UUID of the target Worker.

        Returns:
            List of service dicts (each with name, state, status, etc.).

        Raises:
            RuntimeError: If the node is not connected.
        """
        if not await self._node_manager.is_connected(node_id):
            raise RuntimeError(f"Node {node_id} is not connected")

        intent: dict[str, Any] = {
            "intent_id": str(uuid.uuid4()),
            "action": "LIST_SERVICES",
            "params": {},
        }
        result = await self._node_manager._send_intent(node_id, intent)
        return result.get("output", [])

    async def list_containers(self, node_id: str) -> list[dict[str, Any]]:
        """Send LIST_CONTAINERS intent to a connected Worker.

        Args:
            node_id: UUID of the target Worker.

        Returns:
            List of container dicts (each with id, name, image, state, ports, etc.).

        Raises:
            RuntimeError: If the node is not connected.
        """
        if not await self._node_manager.is_connected(node_id):
            raise RuntimeError(f"Node {node_id} is not connected")

        intent: dict[str, Any] = {
            "intent_id": str(uuid.uuid4()),
            "action": "LIST_CONTAINERS",
            "params": {},
        }
        result = await self._node_manager._send_intent(node_id, intent)
        return result.get("output", [])

    async def read_logs(
        self,
        node_id: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send READ_LOGS intent to a connected Worker.

        Args:
            node_id: UUID of the target Worker.
            params: Optional dict with log query parameters
                (e.g. ``{"service": "nginx", "lines": 50}``).

        Returns:
            Dict with log output from the Worker.

        Raises:
            RuntimeError: If the node is not connected.
        """
        if not await self._node_manager.is_connected(node_id):
            raise RuntimeError(f"Node {node_id} is not connected")

        intent: dict[str, Any] = {
            "intent_id": str(uuid.uuid4()),
            "action": "READ_LOGS",
            "params": params or {},
        }
        return await self._node_manager._send_intent(node_id, intent)
