from __future__ import annotations

import time
from typing import Any

import aiosqlite
import pytest

from master.core.outbox import DEFAULT_MAX_RETRIES, Outbox
from master.db.database import transaction


async def _fetch_entry(db: aiosqlite.Connection, entry_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT * FROM outbox WHERE id = ?", (entry_id,)
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


@pytest.mark.asyncio
async def test_publish_and_process_dispatches_to_handler(db: aiosqlite.Connection):
    """Registered handler receives the entry and the entry is marked processed."""
    outbox = Outbox(db=db)
    handled: list[dict[str, Any]] = []

    async def handler(entry: dict[str, Any], conn: aiosqlite.Connection) -> None:
        handled.append(entry)

    outbox.register_handler("test.event", handler)

    first = await outbox.publish(
        db=db,
        event_type="test.event",
        aggregate_id="agg-1",
        aggregate_type="node",
        payload={"k": "v1"},
    )
    second = await outbox.publish(
        db=db,
        event_type="test.event",
        aggregate_id="agg-2",
        aggregate_type="node",
        payload={"k": "v2"},
    )

    count = await outbox.process_pending(db=db)

    assert count == 2
    # FIFO order preserved
    assert [e["aggregate_id"] for e in handled] == ["agg-1", "agg-2"]
    assert all(e["payload_json"] for e in handled)
    for entry_id in (first, second):
        row = await _fetch_entry(db, entry_id)
        assert row["processed"] == 1
        assert row["processed_at"] is not None


@pytest.mark.asyncio
async def test_handler_failure_increments_retry_count(db: aiosqlite.Connection):
    """A failing handler bumps retry_count and leaves the entry unprocessed."""
    outbox = Outbox(db=db)

    async def failing_handler(entry: dict[str, Any], conn: aiosqlite.Connection) -> None:
        raise RuntimeError("boom")

    outbox.register_handler("test.event", failing_handler)

    entry_id = await outbox.publish(
        db=db,
        event_type="test.event",
        aggregate_id="agg-1",
        aggregate_type="node",
        payload={"k": "v1"},
    )

    count = await outbox.process_pending(db=db)

    assert count == 0
    row = await _fetch_entry(db, entry_id)
    assert row["processed"] == 0
    assert row["retry_count"] == 1
    assert "failing_handler" in row["error"]


@pytest.mark.asyncio
async def test_dead_letter_cap_permanently_fails_poisoned_entry(db: aiosqlite.Connection):
    """After max_retries failures the entry is dead-lettered with a permanent error."""
    outbox = Outbox(db=db, max_retries=2)

    async def failing_handler(entry: dict[str, Any], conn: aiosqlite.Connection) -> None:
        raise RuntimeError("poisoned")

    outbox.register_handler("test.event", failing_handler)

    entry_id = await outbox.publish(
        db=db,
        event_type="test.event",
        aggregate_id="agg-1",
        aggregate_type="node",
        payload={"k": "v1"},
    )

    # Sweep 1 — first failure, still retryable
    await outbox.process_pending(db=db)
    row = await _fetch_entry(db, entry_id)
    assert row["processed"] == 0
    assert row["retry_count"] == 1

    # Sweep 2 — retry cap reached, dead-lettered
    await outbox.process_pending(db=db)
    row = await _fetch_entry(db, entry_id)
    assert row["processed"] == 1
    assert row["retry_count"] == 2
    assert "PERMANENTLY FAILED after 2 retries" in row["error"]

    # No further retry attempts happen once dead-lettered
    await outbox.process_pending(db=db)
    row = await _fetch_entry(db, entry_id)
    assert row["retry_count"] == 2


@pytest.mark.asyncio
async def test_default_max_retries_constant():
    assert DEFAULT_MAX_RETRIES == 5
    assert Outbox()._max_retries == 5


@pytest.mark.asyncio
async def test_cleanup_old_deletes_only_old_processed_entries(db: aiosqlite.Connection):
    outbox = Outbox(db=db)

    async def handler(entry: dict[str, Any], conn: aiosqlite.Connection) -> None:
        pass

    outbox.register_handler("test.event", handler)

    old_id = await outbox.publish(
        db=db,
        event_type="test.event",
        aggregate_id="old",
        aggregate_type="node",
        payload={},
    )
    fresh_id = await outbox.publish(
        db=db,
        event_type="test.event",
        aggregate_id="fresh",
        aggregate_type="node",
        payload={},
    )
    await outbox.process_pending(db=db)

    # Unprocessed entry, deliberately old — must survive cleanup
    unprocessed_id = await outbox.publish(
        db=db,
        event_type="no.handler",
        aggregate_id="unprocessed",
        aggregate_type="node",
        payload={},
    )
    # Backdate it so it is older than the cutoff
    past = time.time() - 10 * 86400
    async with transaction(db) as tx:
        await tx.execute(
            "UPDATE outbox SET processed_at = ? WHERE id = ?", (past, unprocessed_id)
        )

    # Backdate only the "old" processed entry
    async with transaction(db) as tx:
        await tx.execute(
            "UPDATE outbox SET processed_at = ? WHERE id = ?", (past, old_id)
        )

    cutoff = time.time() - 7 * 86400
    deleted = await outbox.cleanup_old(processed_before_ts=cutoff, db=db)

    assert deleted == 1
    assert await _fetch_entry(db, old_id) is None
    assert await _fetch_entry(db, fresh_id) is not None
    assert await _fetch_entry(db, unprocessed_id) is not None


@pytest.mark.asyncio
async def test_replay_unprocessed_dispatches_pending_entries(db: aiosqlite.Connection):
    """replay_unprocessed re-dispatches entries published before handler registration."""
    outbox = Outbox(db=db)
    handled: list[str] = []

    entry_id = await outbox.publish(
        db=db,
        event_type="late.event",
        aggregate_id="agg-1",
        aggregate_type="node",
        payload={"k": "v1"},
    )

    # No handler registered at publish time — would be auto-processed by sweep.
    # Register now, then replay: the entry must reach the handler.
    async def handler(entry: dict[str, Any], conn: aiosqlite.Connection) -> None:
        handled.append(entry["id"])

    outbox.register_handler("late.event", handler)

    replayed = await outbox.replay_unprocessed(db=db)

    assert replayed == 1
    assert handled == [entry_id]
    row = await _fetch_entry(db, entry_id)
    assert row["processed"] == 1
