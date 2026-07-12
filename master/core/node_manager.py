"""
Vigile — Node Manager

Manages the lifecycle of all Worker Nodes:
  - State machine (PENDING → ENROLLING → UNCONFIGURED → CONNECTED → LOST → STALE → DISABLED)
  - In-memory registry of active WebSocket connections
  - Background heartbeat monitor task
  - Intent routing to connected Workers
  - Hard-delete on revoke (cascades to join_tokens, worker_tokens, metrics_snapshots, etc.)

State transitions (allowed):
  PENDING      → ENROLLING   (token validated, handshake started)
  ENROLLING    → CONNECTED   (Ed25519 handshake complete)
  ENROLLING    → PENDING     (handshake failed/timeout)
  CONNECTED    → LOST        (heartbeat missed > threshold)
  LOST         → CONNECTED   (Worker reconnected)
  LOST         → STALE       (lost for > 24h)
  STALE        → CONNECTED   (Worker reconnected)

Deletion:
  Any state → (row removed) via `delete_node()`. The FK ON DELETE CASCADE clauses
  on join_tokens, worker_tokens, metrics_snapshots, action_proposals, and
  chat_sessions clean up child rows automatically. The audit_log keeps the
  NODE_DELETED entry forever (it stores `node_id` as plain TEXT, no FK).

Note: `NodeState.REVOKED` is kept as an enum value for backward compatibility
with legacy rows, but the application no longer transitions to it — a revoked
node is hard-deleted from the nodes table.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any

import aiosqlite
from fastapi import WebSocket

from master.core.audit import AuditAction, log_action
from master.core.enums import NodeState
from master.core.lock import LoopBoundLock
from master.db.database import get_db_conn

logger = logging.getLogger(__name__)


# NodeState is imported from master.core.enums for canonical definition


VALID_TRANSITIONS: set[tuple[NodeState, NodeState]] = {
    (NodeState.PENDING, NodeState.ENROLLING),
    (NodeState.ENROLLING, NodeState.UNCONFIGURED),  # Ed25519 handshake done
    (NodeState.ENROLLING, NodeState.CONNECTED),  # legacy direct path
    (NodeState.ENROLLING, NodeState.PENDING),  # handshake failed
    (NodeState.UNCONFIGURED, NodeState.CONNECTED),  # operator confirmed
    (NodeState.UNCONFIGURED, NodeState.DISABLED),
    (NodeState.CONNECTED, NodeState.LOST),
    (NodeState.CONNECTED, NodeState.RECONNECTING),
    (NodeState.CONNECTED, NodeState.DISABLED),
    (NodeState.RECONNECTING, NodeState.CONNECTED),
    (NodeState.RECONNECTING, NodeState.LOST),
    (NodeState.LOST, NodeState.CONNECTED),  # Worker came back
    (NodeState.LOST, NodeState.STALE),
    (NodeState.LOST, NodeState.ENROLLING),  # Re-enrollment allowed
    (NodeState.STALE, NodeState.CONNECTED),  # Worker came back
    (NodeState.STALE, NodeState.ENROLLING),  # Re-enrollment allowed
    (NodeState.RECONNECTING, NodeState.ENROLLING),  # Re-enrollment allowed
    (NodeState.DISABLED, NodeState.CONNECTED),
    (NodeState.DISABLED, NodeState.LOST),
    (NodeState.DISABLED, NodeState.ENROLLING),
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
        self.last_heartbeat = time.time()

    def heartbeat_age(self) -> float:
        return time.time() - self.last_heartbeat


# ---------------------------------------------------------------------------
# NodeManager
# ---------------------------------------------------------------------------


# Valid column names for safe SQL updates in transition_state
_VALID_NODE_FIELDS: set[str] = {
    "state",
    "hostname",
    "machine_id",
    "arch",
    "os",
    "public_key",
    "ip_prefix",
    "last_heartbeat",
    "enrolled_at",
    "name",
    "node_group",
    "disabled",
}


class NodeManager:
    """
    Central registry for all Worker Nodes.
    Single-process async FastAPI app — asyncio lock protects shared state.
    """

    def __init__(self) -> None:
        # node_id → ActiveConnection (only for CONNECTED nodes)
        self._connections: dict[str, ActiveConnection] = {}
        self._lock: Any = LoopBoundLock()
        # Pending intent futures: intent_id → asyncio.Future
        self._pending_intents: dict[str, asyncio.Future] = {}
        self._intent_created_at: dict[str, float] = {}
        # Track which node owns each pending intent (for cleanup on disconnect)
        self._intent_nodes: dict[str, str] = {}
        self._intent_max_age: dict[str, float] = {}
        self._default_intent_max_age: float = 300.0
        self._monitor_task: asyncio.Task | None = None
        self._cache_task: asyncio.Task | None = None
        # Callbacks invoked after every successful state transition (e.g. automation engine)
        self._state_change_callbacks: list = []

    # -----------------------------------------------------------------------
    # Startup / Shutdown
    # -----------------------------------------------------------------------

    async def start(
        self,
        heartbeat_interval: int = 30,
        lost_threshold: int = 300,
        stale_threshold: int = 86400,
        default_intent_max_age: float = 300.0,
        cache_update_interval: int = 300,
    ) -> None:
        """Start the background heartbeat monitor and cache updater. Called at app startup.
        Thresholds are injected here — no config coupling inside the loop."""
        self.heartbeat_interval = heartbeat_interval
        self._default_intent_max_age = default_intent_max_age
        self._monitor_task = asyncio.create_task(
            self._heartbeat_monitor(heartbeat_interval, lost_threshold, stale_threshold),
            name="heartbeat_monitor",
        )
        self._cache_task = asyncio.create_task(
            self._cache_updater(cache_update_interval),
            name="cache_updater",
        )
        logger.info("NodeManager started. Heartbeat monitor and cache updater running.")

    def register_state_change_callback(self, callback) -> None:
        """Register an async callback(node_id, new_state, db) invoked after every state transition."""
        self._state_change_callbacks.append(callback)

    async def stop(self) -> None:
        """Stop the heartbeat monitor and cache updater. Called at app shutdown."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        if self._cache_task:
            self._cache_task.cancel()
            try:
                await self._cache_task
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

    async def _cache_updater(self, interval: int) -> None:
        logger.info("Cache updater task started. Interval: %ds", interval)
        while True:
            try:
                await asyncio.sleep(interval)
                await self.update_all_nodes_cache()
            except asyncio.CancelledError:
                break
            except aiosqlite.OperationalError as e:
                logger.warning("DB unavailable, reconnecting: %s", e)
                await asyncio.sleep(5)
                continue
            except Exception:
                logger.exception("Cache updater error (will retry)")
                await asyncio.sleep(30)

    async def update_all_nodes_cache(self, node_id: str | None = None) -> None:
        """Query and cache active services and Docker containers for online node(s)."""
        from master.core.plugin_helpers import parse_container_list, parse_service_list

        db = get_db_conn()
        connected = [node_id] if node_id else self.connected_node_ids()
        if not connected:
            return

        logger.debug("Cache updater: starting update for nodes: %s", connected)
        node_updates = []
        for nid in connected:
            try:
                # 1. Get services
                services_json = None
                try:
                    result = await self.send_intent(nid, {"action": "LIST_SERVICES"}, timeout=10.0)
                    if result.get("success"):
                        parsed = parse_service_list(result.get("output", ""))
                        if parsed is not None:
                            services_json = json.dumps(parsed)
                except Exception as ex:
                    logger.warning("Cache updater: failed to get services for node %s: %s", nid, ex)

                # 2. Get containers
                containers_json = None
                try:
                    result = await self.send_intent(
                        nid, {"action": "LIST_CONTAINERS"}, timeout=10.0
                    )
                    if result.get("success"):
                        parsed = parse_container_list(result.get("output", ""))
                        if parsed is not None:
                            containers_json = json.dumps(parsed)
                except Exception as ex:
                    logger.warning(
                        "Cache updater: failed to get containers for node %s: %s", nid, ex
                    )

                if services_json is not None or containers_json is not None:
                    node_updates.append((nid, services_json, containers_json))
            except Exception as ex:
                logger.warning(
                    "Cache updater: failed to process cache gathering for node %s: %s", nid, ex
                )

        # 3. Save cache to DB in a single transaction
        if node_updates:
            from master.db.database import transaction

            try:
                async with transaction(db) as tx_db:
                    for nid, services_json, containers_json in node_updates:
                        fields = []
                        params = []
                        if services_json is not None:
                            fields.append("cached_services_json = ?")
                            params.append(services_json)
                        if containers_json is not None:
                            fields.append("cached_containers_json = ?")
                            params.append(containers_json)

                        params.append(nid)
                        query = "UPDATE nodes SET " + ", ".join(fields) + " WHERE id = ?"
                        await tx_db.execute(query, params)
                        logger.debug("Cache updater: successfully updated cache for node %s", nid)
                        try:
                            await log_action(
                                tx_db,
                                user_id="system",
                                action=AuditAction.CACHE_REFRESH,
                                node_id=nid,
                                details={
                                    "services_updated": services_json is not None,
                                    "containers_updated": containers_json is not None,
                                },
                            )
                        except Exception:
                            logger.warning(
                                "Cache updater: failed to log audit trail for node %s", nid
                            )
            except Exception as ex:
                logger.error("Cache updater: transaction failed: %s", ex)

        # 4. Check profile expiration and new container detection for auto-regeneration
        containers_by_node = {nid: containers_json for nid, _, containers_json in node_updates}
        for nid in connected:
            try:
                async with db.execute(
                    "SELECT insight_profile, insight_profile_generated_at FROM nodes WHERE id = ?",
                    (nid,),
                ) as cursor:
                    row = await cursor.fetchone()

                if row and row["insight_profile"]:
                    profile_dict = json.loads(row["insight_profile"])
                    generated_at = row["insight_profile_generated_at"] or 0.0
                    now = time.time()

                    # 7-day expiration check
                    expired_time = (now - generated_at) > 7 * 86400

                    # New containers check (with 24h cooldown to avoid LLM spam)
                    new_apps_detected = False
                    cooldown_ok = (now - generated_at) > 86400

                    node_containers_json = containers_by_node.get(nid)
                    if cooldown_ok and not expired_time and node_containers_json:
                        fresh_conts = parse_container_list(json.loads(node_containers_json))
                        fresh_running = [
                            c.get("name")
                            for c in fresh_conts or []
                            if c.get("state") == "running" or "up" in c.get("status", "").lower()
                        ]
                        known_conts = [
                            p.get("container_name")
                            for p in profile_dict.get("known_heavy_processes", [])
                            if p.get("container_name")
                        ]
                        new_apps_detected = any(fc not in known_conts for fc in fresh_running)

                    if expired_time or new_apps_detected:
                        logger.info(
                            "Profile expiration / new apps detected for node %s (expired=%s, new_apps=%s). Regenerating profile...",
                            nid,
                            expired_time,
                            new_apps_detected,
                        )
                        from master.api.deps import get_insights_manager

                        im = get_insights_manager()
                        asyncio.create_task(im.generate_profile(nid, db, self, force=True))
            except Exception as ex:
                logger.warning(
                    "Cache updater: failed to check profile expiration for node %s: %s", nid, ex
                )
            except Exception as ex:
                logger.exception("Cache updater: error updating node %s: %s", nid, ex)

    # -----------------------------------------------------------------------
    # Node creation (called when Admin generates a join token)
    # -----------------------------------------------------------------------

    def generate_node_id(self) -> str:
        """
        Generate a new node_id (UUID) without persisting anything.

        The corresponding `nodes` row is only created when the Worker
        completes the enrollment handshake. Until then, only the
        `join_tokens` row references this id.
        """
        return str(uuid.uuid4())

    async def create_node(
        self,
        db: aiosqlite.Connection,
        *,
        name: str,
        ip_prefix: str = "",
        group: str = "",
    ) -> str:
        """
        Pre-create a node entry in PENDING state.
        Returns the node_id (UUID).

        NOTE: Prefer `generate_node_id()` in production flows. This method
        remains for tests and explicit pre-creation use cases. A node
        created here is a 'phantom' until the Worker enrolls — the row
        sits in PENDING state in the DB.
        """
        node_id = str(uuid.uuid4())
        now = time.time()

        await db.execute(
            """
            INSERT INTO nodes
                (id, name, ip_prefix, node_group, state, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (node_id, name, ip_prefix, group, NodeState.PENDING.value, now, now),
        )
        await db.commit()
        logger.info("Node pre-created: id=%s name=%s group=%s", node_id, name, group)
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
        async with db.execute("SELECT state FROM nodes WHERE id = ?", (node_id,)) as cursor:
            row = await cursor.fetchone()

        if row is None:
            raise ValueError(f"Node not found: {node_id}")

        current_state = NodeState(row["state"])
        if (current_state, new_state) not in VALID_TRANSITIONS:
            raise ValueError(f"Invalid transition {current_state} → {new_state} for node {node_id}")

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
            "UPDATE nodes SET " + set_clause + " WHERE id = ?",
            values,
        )
        await db.commit()
        logger.info("Node %s: %s → %s", node_id, current_state.value, new_state.value)

        try:
            from master.core.event_bus import get_event_bus

            await get_event_bus().publish(
                "node.state",
                {
                    "node_id": node_id,
                    "from_state": current_state.value,
                    "new_state": new_state.value,
                    "ts": now,
                },
            )
        except Exception:
            logger.exception("Failed to publish node.state event")

        # Notify registered callbacks (e.g. automation engine) without blocking
        for cb in self._state_change_callbacks:
            asyncio.create_task(cb(node_id, new_state, db))

    async def delete_node(
        self,
        db: aiosqlite.Connection,
        node_id: str,
        deleted_by: str,
    ) -> dict[str, Any] | None:
        """
        Hard-delete a node and all its dependent rows.

        Cascades (via FK ON DELETE CASCADE) clean up:
          - join_tokens
          - worker_tokens
          - metrics_snapshots
          - action_proposals
          - chat_sessions (node_id set to NULL via ON DELETE SET NULL)

        The audit_log keeps a NODE_DELETED entry forever (no FK on node_id).

        Returns the deleted node's last known state and name (for audit details),
        or None if the node was not found.
        """
        async with db.execute(
            "SELECT state, name, hostname FROM nodes WHERE id = ?", (node_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None

        previous_state = row["state"]
        previous_name = row["name"]
        previous_hostname = row["hostname"]
        now = time.time()

        await db.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        await db.commit()

        async with self._lock:
            conn = self._connections.pop(node_id, None)
        if conn is not None:
            try:
                await conn.websocket.close(code=4403, reason="Node deleted by operator")
            except Exception:
                pass

        logger.warning("Node DELETED: id=%s by=%s", node_id, deleted_by)

        try:
            from master.core.event_bus import get_event_bus

            bus = get_event_bus()
            await bus.publish(
                "node.deleted",
                {
                    "node_id": node_id,
                    "previous_state": previous_state,
                    "ts": now,
                },
            )
            await bus.publish(
                "node.state",
                {
                    "node_id": node_id,
                    "from_state": previous_state,
                    "new_state": NodeState.REVOKED.value,
                    "ts": now,
                },
            )
        except Exception:
            logger.exception("Failed to publish delete events")

        try:
            await log_action(
                db,
                user_id=deleted_by,
                action=AuditAction.NODE_DELETED,
                node_id=node_id,
                details={
                    "previous_state": previous_state,
                    "previous_name": previous_name,
                    "previous_hostname": previous_hostname,
                },
            )
        except Exception:
            logger.exception("Failed to log NODE_DELETED audit entry")

        return {
            "id": node_id,
            "state": previous_state,
            "name": previous_name,
            "hostname": previous_hostname,
        }

    async def configure_node(
        self,
        db: aiosqlite.Connection,
        node_id: str,
        *,
        name: str,
        group: str | None,
    ) -> None:
        """
        Operator confirmed name+group: transition UNCONFIGURED -> CONNECTED.
        """
        await self.transition_state(
            db,
            node_id,
            NodeState.CONNECTED,
            extra_fields={"name": name, "node_group": group or ""},
        )
        await log_action(
            db,
            user_id="system",
            action=AuditAction.CONFIGURE_NODE,
            node_id=node_id,
            details={"name": name, "group": group or ""},
        )

    async def set_disabled(
        self,
        db: aiosqlite.Connection,
        node_id: str,
        disabled: bool,
        by_user: str,
    ) -> None:
        """
        Toggle the `disabled` flag and transition to/from DISABLED accordingly.
        Closing the active WebSocket with code 4429 if disabling an active node.
        """
        async with db.execute(
            "SELECT state, disabled FROM nodes WHERE id = ?", (node_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise ValueError(f"Node not found: {node_id}")
        current_state = NodeState(row["state"])
        currently_disabled = bool(row["disabled"])

        if disabled == currently_disabled:
            return

        now = time.time()
        await db.execute(
            "UPDATE nodes SET disabled = ?, updated_at = ? WHERE id = ?",
            (1 if disabled else 0, now, node_id),
        )
        await db.commit()

        target_state: NodeState | None = None
        if disabled and current_state != NodeState.DISABLED:
            target_state = NodeState.DISABLED
        elif not disabled and current_state == NodeState.DISABLED:
            async with self._lock:
                is_alive = node_id in self._connections
            target_state = NodeState.CONNECTED if is_alive else NodeState.LOST

        if target_state is not None and target_state != current_state:
            await self.transition_state(db, node_id, target_state)

        if disabled:
            async with self._lock:
                conn = self._connections.pop(node_id, None)
            if conn is not None:
                try:
                    await conn.websocket.close(code=4429, reason="Node disabled by operator")
                except Exception:
                    pass

        await log_action(
            db,
            user_id=by_user,
            action=AuditAction.DISABLE_NODE if disabled else AuditAction.ENABLE_NODE,
            node_id=node_id,
            details={
                "from_state": current_state.value,
                "new_state": target_state.value if target_state else current_state.value,
            },
        )
        logger.info("Node %s: disabled=%s by=%s", node_id, disabled, by_user)

    async def patch_metadata(
        self,
        db: aiosqlite.Connection,
        node_id: str,
        *,
        name: str | None = None,
        group: str | None = None,
        by_user: str = "system",
    ) -> None:
        """
        Update name and/or group on an existing node. Does NOT change state.
        """
        fields: dict[str, Any] = {"updated_at": time.time()}
        details: dict[str, Any] = {}
        if name is not None:
            fields["name"] = name
            details["name"] = name
        if group is not None:
            fields["node_group"] = group
            details["group"] = group
        if len(fields) == 1:
            return
        _ALLOWED_UPDATE_FIELDS = {"updated_at", "name", "node_group"}
        for k in fields:
            if k not in _ALLOWED_UPDATE_FIELDS:
                raise ValueError(f"Invalid update field: {k}")
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [node_id]
        await db.execute("UPDATE nodes SET " + set_clause + " WHERE id = ?", values)
        await db.commit()
        await log_action(
            db,
            user_id=by_user,
            action=AuditAction.UPDATE_NODE,
            node_id=node_id,
            details=details,
        )

    async def invalidate_join_tokens(self, db: aiosqlite.Connection, node_id: str) -> int:
        """
        Mark all existing join tokens for this node as consumed+expired.
        Returns the number of tokens invalidated.
        """
        now = time.time()
        async with db.execute(
            "SELECT id FROM join_tokens WHERE node_id = ? AND consumed = 0",
            (node_id,),
        ) as cursor:
            ids = [row["id"] for row in await cursor.fetchall()]
        if not ids:
            return 0
        placeholders = ", ".join("?" * len(ids))
        await db.execute(
            "UPDATE join_tokens SET consumed = 1, expires_at = ? WHERE id IN ("
            + placeholders
            + ")",
            [now, *ids],
        )
        await db.commit()
        return len(ids)

    async def is_disabled(self, db: aiosqlite.Connection, node_id: str) -> bool:
        async with db.execute("SELECT disabled FROM nodes WHERE id = ?", (node_id,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return False
        return bool(row["disabled"])

    async def lockdown(self) -> None:
        """
        Close all active WebSocket connections due to security compromise.
        """
        async with self._lock:
            conns = list(self._connections.values())
            self._connections.clear()

        for conn in conns:
            try:
                await conn.websocket.close(code=4433, reason="Security compromise detected")
            except Exception:
                pass
        logger.warning("NodeManager locked down: all active connections closed.")

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
                self._intent_created_at.pop(intent_id, None)
                future = self._pending_intents.pop(intent_id, None)
                if future is not None and not future.done():
                    future.cancel()
        logger.info("Node %s WebSocket unregistered.", node_id)

    async def get_connection(self, node_id: str) -> ActiveConnection | None:
        async with self._lock:
            return self._connections.get(node_id)

    async def touch_heartbeat(self, node_id: str) -> None:
        async with self._lock:
            if conn := self._connections.get(node_id):
                conn.touch()

    async def is_connected(self, node_id: str) -> bool:
        async with self._lock:
            return node_id in self._connections

    def connected_node_ids(self) -> list[str]:
        """Return the list of currently connected node IDs.
        Note: snapshot without lock — safe for debugging/admin display only."""
        return list(self._connections.keys())

    async def resolve_intent(self, intent_id: str, result: dict[str, Any]) -> None:
        """Resolve a pending intent with the Worker's response."""
        self._intent_nodes.pop(intent_id, None)
        self._intent_created_at.pop(intent_id, None)
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
        intent_max_age: float | None = None,
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
            intent_max_age : optional per-intent max age before cleanup falls stale

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
            self._intent_created_at[intent_id] = time.time()
            self._intent_nodes[intent_id] = node_id
            if intent_max_age is not None:
                self._intent_max_age[intent_id] = intent_max_age

            # Send type last to prevent intent dict from overwriting the message type
            await conn.websocket.send_json({**intent, "type": "INTENT"})
            logger.info(
                "Intent sent to node %s: action=%s id=%s", node_id, intent.get("action"), intent_id
            )

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Node {node_id} did not respond to intent {intent_id} within {timeout}s"
            )
        finally:
            self._intent_max_age.pop(intent_id, None)
            self._intent_nodes.pop(intent_id, None)
            self._intent_created_at.pop(intent_id, None)
            self._pending_intents.pop(intent_id, None)

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
            interval,
            lost_threshold,
            stale_threshold,
        )
        intent_cleanup_counter = 0

        while True:
            try:
                await asyncio.sleep(interval)
                await self._check_heartbeats(lost_threshold, stale_threshold)
                # Clean up stale pending intents every ~10 cycles
                intent_cleanup_counter += 1
                if intent_cleanup_counter >= 10:
                    intent_cleanup_counter = 0
                    self._cleanup_stale_intents()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Heartbeat monitor error (will retry)")

    def _cleanup_stale_intents(self) -> int:
        """Remove pending intents that are done or have been waiting longer than their max_age."""
        now = time.time()
        stale_ids: list[str] = []
        for intent_id, future in list(self._pending_intents.items()):
            created = self._intent_created_at.get(intent_id, now)
            max_age = self._intent_max_age.get(intent_id, self._default_intent_max_age)
            if future.done() or (now - created) > max_age:
                stale_ids.append(intent_id)
        for intent_id in stale_ids:
            self._intent_nodes.pop(intent_id, None)
            self._intent_created_at.pop(intent_id, None)
            self._intent_max_age.pop(intent_id, None)
            if intent_id in self._pending_intents:
                future = self._pending_intents.pop(intent_id)
                if not future.done():
                    future.cancel()
        count = len(stale_ids)
        if count:
            logger.warning("Cleaned up %d stale pending intents.", count)
        return count

    def set_default_intent_max_age(self, value: float) -> None:
        """Update the default intent max age at runtime (e.g. via admin endpoint)."""
        self._default_intent_max_age = value
        logger.info("Default intent max age updated to %.1fs", value)

    async def _check_heartbeats(self, lost_threshold: float, stale_threshold: float) -> None:
        """Check all nodes in the DB and update states based on heartbeat age."""
        db = get_db_conn()
        now = time.time()

        async with self._lock:
            connected = list(self._connections.items())

        for node_id, conn in connected:
            age = conn.heartbeat_age()
            if age > lost_threshold:
                logger.warning("Node %s: no heartbeat for %.0fs — marking LOST", node_id, age)
                await self.unregister_connection(node_id)
                try:
                    await self.transition_state(db, node_id, NodeState.LOST)
                    await log_action(
                        db,
                        user_id="system",
                        action=AuditAction.NODE_LOST,
                        node_id=node_id,
                        details={"heartbeat_age": age, "lost_threshold": lost_threshold},
                    )
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
                        await log_action(
                            db,
                            user_id="system",
                            action=AuditAction.NODE_STALE,
                            node_id=node_id,
                            details={"heartbeat_age": age, "stale_threshold": stale_threshold},
                        )
                        logger.warning("Node %s marked STALE (offline %.0fh)", node_id, age / 3600)
                    except Exception:
                        logger.exception("Failed to transition node %s to STALE", node_id)

    # -----------------------------------------------------------------------
    # Query helpers
    # -----------------------------------------------------------------------

    async def get_node(self, db: aiosqlite.Connection, node_id: str) -> dict[str, Any] | None:
        async with db.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        d = dict(row)
        d["online"] = node_id in self._connections
        return d

    async def list_nodes(
        self,
        db: aiosqlite.Connection,
        *,
        state: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        include_revoked: bool = False,
    ) -> list[dict[str, Any]]:
        """List nodes, optionally filtered by state, with pagination.

        By default, REVOKED rows are excluded (legacy state from before the
        hard-delete migration — they should not exist in fresh DBs). Pass
        `include_revoked=True` to include them (admin/debug only).
        """
        clauses: list[str] = []
        params: list[Any] = []
        if state:
            clauses.append("state = ?")
            params.append(state)
        if not include_revoked:
            clauses.append("state != ?")
            params.append(NodeState.REVOKED.value)
        where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = "SELECT * FROM nodes" + where_sql + " ORDER BY created_at DESC"

        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        if offset is not None:
            sql += " OFFSET ?"
            params.append(offset)

        rows = []
        async with db.execute(sql, params) as cursor:
            async for row in cursor:
                d = dict(row)
                d["online"] = d["id"] in self._connections
                rows.append(d)
        return rows


# Module-level singleton
node_manager = NodeManager()
