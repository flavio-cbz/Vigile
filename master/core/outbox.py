from __future__ import annotations

"""
Vigile — Transactional Outbox for Async Event Publishing

Provides an Outbox class that inserts domain events into the ``outbox`` DB
table within the current transaction, then dispatches them to registered async
handlers when process_pending() is called (typically from a background loop
or on startup).

Event types used in this project:
  - proposal.approved
  - intent.dispatched
  - plugin.state_changed
  - node.state_changed
  - alert.fired

Usage::

    from master.core.outbox import outbox

    # Register handlers at startup
    outbox.register_handler("node.state_changed", my_handler)

    # Publish inside a DB transaction
    await outbox.publish(
        event_type="node.state_changed",
        aggregate_id=node_id,
        aggregate_type="node",
        payload={"old_state": "CONNECTED", "new_state": "LOST"},
    )

    # Process pending events (e.g. in a periodic task)
    count = await outbox.process_pending()
"""

import json
import time
import uuid
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict


import aiosqlite
import logging

from master.db.database import get_db_conn, transaction

logger = logging.getLogger(__name__)

# Type alias for async outbox handlers.
# Receives the full outbox row (as dict) and an aiosqlite connection.
OutboxHandler = Callable[[Dict[str, Any], aiosqlite.Connection], Awaitable[Any]]



class Outbox:
    """
    Transactional outbox for reliable async event publishing.

    Events are persisted atomically within the caller's DB transaction, then
    dispatched asynchronously via registered handlers.  This guarantees at-least-
    once delivery: if the handler crashes between marking ``processed=1`` and
    completing side effects, the event may be re-processed on the next sweep.

    Lightweight constructor — no I/O, no settings/env reads.  For production use,
    rely on the module-level singleton ``outbox = Outbox()``.
    """

    def __init__(self, db: aiosqlite.Connection | None = None) -> None:
        """
        Args:
            db: Optional fixed DB connection.  When ``None`` (the default for
                the module singleton), every method falls back to
                ``get_db_conn()``.
        """
        self._db: aiosqlite.Connection | None = db
        # event_type → list of async handlers
        self._handlers: dict[str, list[OutboxHandler]] = defaultdict(list)

    # -----------------------------------------------------------------–
    # Internal helpers
    # -----------------------------------------------------------------–

    def _resolve_db(
        self, db: aiosqlite.Connection | None = None
    ) -> aiosqlite.Connection:
        """Return the caller-provided connection, the instance default, or the
        ambient context-var connection."""
        if db is not None:
            return db
        if self._db is not None:
            return self._db
        return get_db_conn()

    # -----------------------------------------------------------------–
    # Public API
    # -----------------------------------------------------------------–

    async def publish(
        self,
        event_type: str,
        aggregate_id: str | None,
        aggregate_type: str,
        payload: dict[str, Any],
        db: aiosqlite.Connection | None = None,
    ) -> str:
        """
        Insert a domain event into the outbox table.

        The insert runs **inside** the current transaction (or a new one if
        none is active).  The event is only visible to ``process_pending()``
        after the enclosing transaction commits.

        Args:
            event_type:  Dot-separated event name (e.g. ``"node.state_changed"``).
            aggregate_id:  ID of the entity that produced the event (may be
                ``None`` for global events).
            aggregate_type:  Entity type name (e.g. ``"node"``, ``"alert"``).
            payload:  Arbitrary JSON-serialisable event data.
            db:  Optional connection override.  Falls back to instance or
                context-var connection.

        Returns:
            The UUID of the newly created outbox entry.
        """
        conn = self._resolve_db(db)
        entry_id = str(uuid.uuid4())
        now = time.time()

        async with transaction(conn) as tx_db:
            await tx_db.execute(
                """INSERT INTO outbox
                   (id, event_type, aggregate_id, aggregate_type,
                    payload_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    entry_id,
                    event_type,
                    aggregate_id,
                    aggregate_type,
                    json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
                    now,
                ),
            )

        logger.debug(
            "Outbox entry published",
            entry_id=entry_id,
            event_type=event_type,
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
        )
        return entry_id

    async def process_pending(
        self, db: aiosqlite.Connection | None = None, *, batch_size: int = 100
    ) -> int:
        """
        Fetch and dispatch all unprocessed outbox entries.

        For each entry:
          1. Look up registered handlers for ``entry["event_type"]``.
          2. Call every matching handler with ``(entry_dict, db)``.
          3. On success → mark the entry as processed (``processed=1``,
             ``processed_at=now``).
          4. On failure → increment ``retry_count`` and store the error
             message; the entry will be retried on the next sweep.

        Handlers are awaited sequentially per entry (entries are processed in
        FIFO order) to preserve event ordering for the same aggregate.

        Args:
            db:  Optional connection override.
            batch_size:  Maximum number of entries to process in one call
                (default 100).  Prevents long-running loops from starving
                other coroutines.

        Returns:
            Number of entries successfully processed (marked ``processed=1``).
        """
        conn = self._resolve_db(db)
        processed_count = 0

        async with conn.execute(
            """SELECT * FROM outbox
               WHERE processed = 0
               ORDER BY created_at ASC
               LIMIT ?""",
            (batch_size,),
        ) as cursor:
            rows = await cursor.fetchall()

        for row in rows:
            entry = dict(row)
            event_type = entry["event_type"]
            handlers = list(self._handlers.get(event_type, []))

            # Also notify wildcard subscribers (event_type = "*")
            handlers.extend(self._handlers.get("*", []))

            if not handlers:
                # No handler registered — mark as processed to avoid
                # accumulating undeliverable entries.
                await self._mark_processed(conn, entry["id"], success=True)
                processed_count += 1
                continue

            success = True
            error_msg: str | None = None

            for handler in handlers:
                try:
                    await handler(entry, conn)
                except Exception:
                    logger.exception(
                        "Outbox handler failed",
                        entry_id=entry["id"],
                        event_type=event_type,
                        handler=handler.__name__,
                    )
                    success = False
                    error_msg = f"{handler.__name__}: handler raised"

            if success:
                await self._mark_processed(conn, entry["id"], success=True)
                processed_count += 1
            else:
                await self._mark_processed(
                    conn, entry["id"], success=False, error=error_msg
                )

        if processed_count:
            logger.info(
                "Outbox processed pending entries",
                count=processed_count,
                batch_size=batch_size,
            )

        return processed_count

    def register_handler(
        self, event_type: str, handler: OutboxHandler
    ) -> None:
        """
        Register an async handler for a specific event type.

        The handler receives ``(entry_dict, db_connection)`` where
        ``entry_dict`` is the full outbox row as a dict (keys match the
        ``outbox`` table columns).

        Use ``event_type="*"`` to register a catch-all handler that receives
        **every** event type.

        Args:
            event_type:  The event type to subscribe to (e.g.
                ``"node.state_changed"``) or ``"*"`` for all events.
            handler:  An async callable ``(dict[str, Any], aiosqlite.Connection)
                -> Awaitable[Any]``.
        """
        self._handlers[event_type].append(handler)
        logger.debug(
            "Outbox handler registered",
            event_type=event_type,
            handler=handler.__name__,
        )

    async def replay_unprocessed(
        self, db: aiosqlite.Connection | None = None, *, batch_size: int = 500
    ) -> int:
        """
        Replay all outbox entries that were **never** processed.

        This is intended for startup recovery: after a crash, any entries that
        were committed to the DB but not yet dispatched (``processed=0``) are
        re-dispatched.  It is equivalent to calling ``process_pending()`` but
        with a larger default batch size so that backlog recovery is faster.

        Args:
            db:  Optional connection override.
            batch_size:  Maximum entries to replay (default 500).

        Returns:
            Number of entries successfully (re-)processed.
        """
        logger.info("Outbox replaying unprocessed entries")
        return await self.process_pending(db=db, batch_size=batch_size)

    async def cleanup_old(
        self,
        processed_before_ts: float,
        db: aiosqlite.Connection | None = None,
    ) -> int:
        """
        Permanently remove processed outbox entries older than a given
        timestamp.

        This is a housekeeping operation — call it periodically (e.g. once
        per hour) to keep the outbox table size bounded.

        Args:
            processed_before_ts:  Unix timestamp.  Entries with
                ``processed_at < processed_before_ts`` are deleted.
            db:  Optional connection override.

        Returns:
            Number of deleted rows.
        """
        conn = self._resolve_db(db)

        async with transaction(conn) as tx_db:
            cursor = await tx_db.execute(
                "DELETE FROM outbox WHERE processed = 1 AND processed_at < ?",
                (processed_before_ts,),
            )
            deleted = cursor.rowcount

        if deleted:
            logger.info(
                "Outbox cleaned old entries",
                deleted=deleted,
                processed_before_ts=processed_before_ts,
            )

        return deleted

    # -----------------------------------------------------------------–
    # Internal mutation helpers
    # -----------------------------------------------------------------–

    async def _mark_processed(
        self,
        conn: aiosqlite.Connection,
        entry_id: str,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Mark an outbox entry as processed (or increment retry on failure)."""
        now = time.time()
        if success:
            async with transaction(conn) as tx_db:
                await tx_db.execute(
                    """UPDATE outbox
                       SET processed = 1, processed_at = ?, retry_count = retry_count
                       WHERE id = ?""",
                    (now, entry_id),
                )
        else:
            current_retry = await self._get_retry_count(conn, entry_id)
            async with transaction(conn) as tx_db:
                await tx_db.execute(
                    """UPDATE outbox
                       SET retry_count = ?, error = ?, processed_at = ?
                       WHERE id = ?""",
                    (current_retry + 1, error, now, entry_id),
                )

    @staticmethod
    async def _get_retry_count(conn: aiosqlite.Connection, entry_id: str) -> int:
        """Read the current retry_count for an entry."""
        async with conn.execute(
            "SELECT retry_count FROM outbox WHERE id = ?", (entry_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return row["retry_count"] if row else 0


# Module-level singleton — lightweight, 0 params, 0 I/O.
outbox: Outbox = Outbox()
