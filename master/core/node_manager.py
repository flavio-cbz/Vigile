"""
Vigile — Node Manager

Manages the lifecycle of all Worker Nodes:
  - State machine (PENDING → ENROLLING → CONNECTED → LOST → STALE → REVOKED)
  - In-memory registry of active WebSocket connections
  - Background heartbeat monitor task
  - Intent routing to connected Workers

State transitions (allowed):
  PENDING      → ENROLLING   (token validated, handshake started)
  ENROLLING    → CONNECTED   (Ed25519 handshake complete)
  ENROLLING    → PENDING     (handshake failed/timeout)
  CONNECTED    → LOST        (heartbeat missed > threshold)
  CONNECTED    → REVOKED     (manual revocation)
  LOST         → CONNECTED   (Worker reconnected)
  LOST         → STALE       (lost for > 24h)
  STALE        → CONNECTED   (Worker reconnected)
  STALE        → REVOKED     (manual revocation)
  REVOKED      → (terminal)  (no transitions out)
"""

import asyncio
import json
import logging
import time
import uuid
from enum import Enum
from typing import Any

import aiosqlite
from fastapi import WebSocket

from master.db.database import get_db_conn

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node state enum
# ---------------------------------------------------------------------------


class NodeState(str, Enum):
    PENDING = "PENDING"           # Token generated, Worker not yet connected
    ENROLLING = "ENROLLING"       # Handshake in progress
    CONNECTED = "CONNECTED"       # Fully enrolled, WSS active, heartbeat OK
    RECONNECTING = "RECONNECTING" # Connection dropped, Worker attempting reconnect
    LOST = "LOST"                 # No heartbeat for > heartbeat_lost_threshold
    STALE = "STALE"               # LOST for > heartbeat_stale_threshold
    REVOKED = "REVOKED"           # Manually revoked, all connections refused


# Allowed transitions: (from_state, to_state)
VALID_TRANSITIONS: set[tuple[NodeState, NodeState]] = {
    (NodeState.PENDING, NodeState.ENROLLING),
    (NodeState.ENROLLING, NodeState.CONNECTED),
    (NodeState.ENROLLING, NodeState.PENDING),       # handshake failed
    (NodeState.CONNECTED, NodeState.LOST),
    (NodeState.CONNECTED, NodeState.REVOKED),
    (NodeState.CONNECTED, NodeState.RECONNECTING),
    (NodeState.RECONNECTING, NodeState.CONNECTED),
    (NodeState.RECONNECTING, NodeState.LOST),
    (NodeState.LOST, NodeState.CONNECTED),          # Worker came back
    (NodeState.LOST, NodeState.STALE),
    (NodeState.LOST, NodeState.REVOKED),
    (NodeState.STALE, NodeState.CONNECTED),         # Worker came back
    (NodeState.STALE, NodeState.REVOKED),
}


# ---------------------------------------------------------------------------
# Active connection entry
# ---------------------------------------------------------------------------


class ActiveConnection:
    """Wraps an active WebSocket with metadata."""

    def __init__(self, node_id: str, websocket: WebSocket) -> None:
        self.node_id = node_id
        self.websocket = websocket
        self.connected_at = time.time()
        self.last_heartbeat = time.time()
        self.remote_address: str = ""

    def touch(self) -> None:
        """Update the heartbeat timestamp."""
        self.last_heartbeat = time.time()

    def heartbeat_age(self) -> float:
        """Seconds since last heartbeat."""
        return time.time() - self.last_heartbeat


# ---------------------------------------------------------------------------
# NodeManager
# ---------------------------------------------------------------------------


# Valid column names for safe SQL updates in transition_state
_VALID_NODE_FIELDS: set[str] = {
    "state", "hostname", "machine_id", "arch", "os",
    "public_key", "ip_prefix", "last_heartbeat",
    "enrolled_at", "name",
}


class NodeManager:
    """
    Central registry for all Worker Nodes.
    Single-process async FastAPI app — asyncio lock protects shared state.
    """

    def __init__(self) -> None:
        # node_id → ActiveConnection (only for CONNECTED nodes)
        self._connections: dict[str, ActiveConnection] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        # Pending intent futures: intent_id → asyncio.Future
        self._pending_intents: dict[str, asyncio.Future] = {}
        # Track which node owns each pending intent (for cleanup on disconnect)
        self._intent_nodes: dict[str, str] = {}
        self._monitor_task: asyncio.Task | None = None

    # -----------------------------------------------------------------------
    # Startup / Shutdown
    # -----------------------------------------------------------------------

    async def start(
        self,
        heartbeat_interval: int = 30,
        lost_threshold: int = 300,
        stale_threshold: int = 86400,
    ) -> None:
        """Start the background heartbeat monitor. Called at app startup.
        Thresholds are injected here — no config coupling inside the loop."""
        self._monitor_task = asyncio.create_task(
            self._heartbeat_monitor(heartbeat_interval, lost_threshold, stale_threshold),
            name="heartbeat_monitor",
        )
        logger.info("NodeManager started. Heartbeat monitor running.")

    async def stop(self) -> None:
        """Stop the heartbeat monitor. Called at app shutdown."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        async with self._lock:
            for conn in list(self._connections.values()):
                try:
                    await conn.websocket.close(code=1001, reason="Server shutting down")
                except Exception:
                    pass
            self._connections.clear()
        logger.info("NodeManager stopped.")

    # -----------------------------------------------------------------------
    # Node creation (called when Admin generates a join token)
    # -----------------------------------------------------------------------

    async def create_node(
        self,
        db: aiosqlite.Connection,
        *,
        name: str,
        ip_prefix: str = "",
    ) -> str:
        """
        Pre-create a node entry in PENDING state.
        Returns the node_id (UUID).
        """
        node_id = str(uuid.uuid4())
        now = time.time()

        await db.execute(
            """
            INSERT INTO nodes
                (id, name, ip_prefix, state, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (node_id, name, ip_prefix, NodeState.PENDING.value, now, now),
        )
        await db.commit()
        logger.info("Node pre-created: id=%s name=%s", node_id, name)
        return node_id

    # -----------------------------------------------------------------------
    # State transitions
    # -----------------------------------------------------------------------

    async def transition_state(
        self,
        db: aiosqlite.Connection,
        node_id: str,
        new_state: NodeState,
        *,
        extra_fields: dict[str, Any] | None = None,
    ) -> None:
        """
        Transition a node to a new state with validation.

        Args:
            db          : active DB connection
            node_id     : target node
            new_state   : desired new state
            extra_fields: optional DB column updates (e.g. {"hostname": "web-01"})

        Raises:
            ValueError  : if the transition is not allowed or node doesn't exist
        """
        async with db.execute(
            "SELECT state FROM nodes WHERE id = ?", (node_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            raise ValueError(f"Node not found: {node_id}")

        current_state = NodeState(row["state"])
        if (current_state, new_state) not in VALID_TRANSITIONS:
            raise ValueError(
                f"Invalid transition {current_state} → {new_state} for node {node_id}"
            )

        now = time.time()
        fields: dict[str, Any] = {"state": new_state.value, "updated_at": now}
        if extra_fields:
            for k in extra_fields:
                if k not in _VALID_NODE_FIELDS:
                    raise ValueError(f"Invalid node field: {k}")
            fields.update(extra_fields)

        updates = {k: v for k, v in fields.items()}
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [node_id]

        await db.execute(
            f"UPDATE nodes SET {set_clause} WHERE id = ?",
            values,
        )
        await db.commit()
        logger.info("Node %s: %s → %s", node_id, current_state.value, new_state.value)

    async def revoke_node(
        self,
        db: aiosqlite.Connection,
        node_id: str,
        revoked_by: str,
    ) -> None:
        """
        Revoke a node: update state, disconnect active WebSocket, revoke all tokens.
        """
        now = time.time()

        await db.execute(
            "UPDATE nodes SET state = ?, updated_at = ? WHERE id = ?",
            (NodeState.REVOKED.value, now, node_id),
        )
        await db.execute(
            "UPDATE worker_tokens SET revoked = 1, revoked_at = ?, revoked_by = ? WHERE node_id = ?",
            (now, revoked_by, node_id),
        )
        await db.commit()

        async with self._lock:
            conn = self._connections.pop(node_id, None)
        if conn is not None:
            try:
                await conn.websocket.close(code=4403, reason="Node revoked")
            except Exception:
                pass

        logger.warning("Node REVOKED: id=%s by=%s", node_id, revoked_by)

    # -----------------------------------------------------------------------
    # Connection management (called from WebSocket handler)
    # -----------------------------------------------------------------------

    async def register_connection(self, node_id: str, websocket: WebSocket) -> ActiveConnection:
        """Register an active WebSocket connection for a node.
        If a connection already exists, closes the old one before replacing."""
        async with self._lock:
            old = self._connections.get(node_id)
            if old is not None:
                logger.warning(
                    "SECURITY: node %s already has an active connection — replacing old one",
                    node_id,
                )
                try:
                    await old.websocket.close(code=4400, reason="Replaced by new connection")
                except Exception:
                    pass
            conn = ActiveConnection(node_id, websocket)
            self._connections[node_id] = conn
        logger.info("Node %s WebSocket registered.", node_id)
        return conn

    async def unregister_connection(self, node_id: str) -> None:
        """Remove a node from the active connections registry.
        Also cancels any pending intents for this node to prevent memory leaks."""
        async with self._lock:
            self._connections.pop(node_id, None)
        # Clean up pending intents for this node
        # Iterate a copy to avoid mutation during iteration
        for intent_id, nid in list(self._intent_nodes.items()):
            if nid == node_id:
                self._intent_nodes.pop(intent_id, None)
                future = self._pending_intents.pop(intent_id, None)
                if future is not None and not future.done():
                    future.cancel()
        logger.info("Node %s WebSocket unregistered.", node_id)

    async def get_connection(self, node_id: str) -> ActiveConnection | None:
        """Return the active connection for a node, or None if not connected."""
        async with self._lock:
            return self._connections.get(node_id)

    async def touch_heartbeat(self, node_id: str) -> None:
        """Update the heartbeat timestamp for a connected node."""
        async with self._lock:
            if conn := self._connections.get(node_id):
                conn.touch()

    async def is_connected(self, node_id: str) -> bool:
        """Return True if the node has an active WebSocket."""
        async with self._lock:
            return node_id in self._connections

    def connected_node_ids(self) -> list[str]:
        """Return the list of currently connected node IDs.
        Note: snapshot without lock — safe for debugging/admin display only."""
        return list(self._connections.keys())

    async def resolve_intent(self, intent_id: str, result: dict[str, Any]) -> None:
        """Resolve a pending intent with the Worker's response."""
        self._intent_nodes.pop(intent_id, None)
        future = self._pending_intents.pop(intent_id, None)
        if future is not None and not future.done():
            future.set_result(result)

    # -----------------------------------------------------------------------
    # Intent dispatch
    # -----------------------------------------------------------------------

    async def send_intent(
        self,
        node_id: str,
        intent: dict[str, Any],
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """
        Send an approved Intent to a connected Worker and wait for the result.

        Uses a Future-based pattern: stores a pending future, sends the intent
        over WebSocket, and waits for the Worker's response (delivered via
        resolve_intent() from the operational loop).

        Args:
            node_id : target node
            intent  : dict with keys: {intent_id, action, params}
            timeout : seconds to wait for response

        Returns:
            The result dict from the Worker.

        Raises:
            RuntimeError: if the node is not connected
            TimeoutError: if the Worker doesn't respond in time
        """
        async with self._lock:
            conn = self._connections.get(node_id)
            if conn is None:
                raise RuntimeError(f"Node {node_id} is not connected")

            intent_id = intent.get("intent_id") or str(uuid.uuid4())
            intent["intent_id"] = intent_id

            future: asyncio.Future = asyncio.get_running_loop().create_future()
            self._pending_intents[intent_id] = future
            self._intent_nodes[intent_id] = node_id

            # Send type last to prevent intent dict from overwriting the message type
            await conn.websocket.send_json({**intent, "type": "INTENT"})
            logger.info("Intent sent to node %s: action=%s id=%s",
                        node_id, intent.get("action"), intent_id)

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._intent_nodes.pop(intent_id, None)
            self._pending_intents.pop(intent_id, None)
            raise TimeoutError(
                f"Node {node_id} did not respond to intent {intent_id} within {timeout}s"
            )

    # -----------------------------------------------------------------------
    # Background heartbeat monitor
    # -----------------------------------------------------------------------

    async def _heartbeat_monitor(
        self, interval: int, lost_threshold: int, stale_threshold: int
    ) -> None:
        """
        Background task that runs every `interval` seconds.
        Thresholds are injected — no config coupling inside the loop.
        """

        logger.info(
            "Heartbeat monitor: interval=%ds lost=%ds stale=%ds",
            interval, lost_threshold, stale_threshold,
        )

        while True:
            try:
                await asyncio.sleep(interval)
                await self._check_heartbeats(lost_threshold, stale_threshold)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Heartbeat monitor error (will retry)")

    async def _check_heartbeats(
        self, lost_threshold: float, stale_threshold: float
    ) -> None:
        """Check all nodes in the DB and update states based on heartbeat age."""
        db = get_db_conn()
        now = time.time()

        async with self._lock:
            connected = list(self._connections.items())

        for node_id, conn in connected:
            age = conn.heartbeat_age()
            if age > lost_threshold:
                logger.warning(
                    "Node %s: no heartbeat for %.0fs — marking LOST", node_id, age
                )
                await self.unregister_connection(node_id)
                try:
                    await self.transition_state(db, node_id, NodeState.LOST)
                except Exception:
                    logger.exception("Failed to transition node %s to LOST", node_id)

        async with db.execute(
            "SELECT id, last_heartbeat FROM nodes WHERE state = ? AND last_heartbeat IS NOT NULL",
            (NodeState.LOST.value,),
        ) as cursor:
            async for row in cursor:
                node_id = row["id"]
                age = now - (row["last_heartbeat"] or 0)
                if age > stale_threshold:
                    try:
                        await self.transition_state(db, node_id, NodeState.STALE)
                        logger.warning("Node %s marked STALE (offline %.0fh)", node_id, age / 3600)
                    except Exception:
                        logger.exception("Failed to transition node %s to STALE", node_id)

    # -----------------------------------------------------------------------
    # Query helpers
    # -----------------------------------------------------------------------

    async def get_node(
        self, db: aiosqlite.Connection, node_id: str
    ) -> dict[str, Any] | None:
        """Fetch a single node by ID. Returns None if not found."""
        async with db.execute(
            "SELECT * FROM nodes WHERE id = ?", (node_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        d = dict(row)
        d["online"] = node_id in self._connections
        return d

    async def list_nodes(
        self, db: aiosqlite.Connection, *, state: str | None = None
    ) -> list[dict[str, Any]]:
        """List all nodes, optionally filtered by state."""
        if state:
            sql = "SELECT * FROM nodes WHERE state = ? ORDER BY created_at DESC"
            params = (state,)
        else:
            sql = "SELECT * FROM nodes ORDER BY created_at DESC"
            params = ()

        rows = []
        async with db.execute(sql, params) as cursor:
            async for row in cursor:
                d = dict(row)
                d["online"] = d["id"] in self._connections
                rows.append(d)
        return rows


# Module-level singleton
node_manager = NodeManager()
