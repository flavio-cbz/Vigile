"""
Vigile — Service Cache Helpers
Read/write cached systemd services in the nodes table.

Uses BEGIN IMMEDIATE via transaction() to serialize WAL writes.
Contract: {services, count, cached_at, stale, errors[]}, TTL 300s.
Only writes on success:true && parsed!=None (caller guard).
"""

from __future__ import annotations

import time

import aiosqlite

from master.db.database import transaction

TTL_SECONDS: float = 300.0


async def get_cached_services(
    db: aiosqlite.Connection, node_id: str
) -> tuple[str | None, float | None]:
    """Return (json_string, timestamp) from the node cache, or (None, None)."""
    async with db.execute(
        "SELECT cached_services_json, cached_services_at FROM nodes WHERE id = ?",
        (node_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None, None
    return row["cached_services_json"], row["cached_services_at"]


async def set_cached_services(
    db: aiosqlite.Connection, node_id: str, json_data: str, timestamp: float
) -> None:
    """Write services cache inside a BEGIN IMMEDIATE transaction.

    Defense-in-depth: rejects empty, null, or non-list JSON to prevent cache poison
    even if caller forgets the only-if-success guard.
    """
    if not json_data or not isinstance(json_data, str):
        return
    stripped = json_data.strip()
    if stripped in ("", "null"):
        return
    try:
        import json as _json

        parsed = _json.loads(json_data)
        if parsed is None:
            return
        # LIST_SERVICES must be a list — never cache a dict/object poison
        if not isinstance(parsed, list):
            return
    except Exception:
        return
    async with transaction(db) as tx_db:
        await tx_db.execute(
            "UPDATE nodes SET cached_services_json = ?, cached_services_at = ? WHERE id = ?",
            (json_data, timestamp, node_id),
        )


async def invalidate_cached_services(
    db: aiosqlite.Connection, node_id: str
) -> None:
    """Invalidate cached services for a node by setting cached_services_at = 0."""
    async with transaction(db) as tx_db:
        await tx_db.execute(
            "UPDATE nodes SET cached_services_at = 0 WHERE id = ?",
            (node_id,),
        )


def is_stale(cached_at: float | None, now: float | None = None) -> bool:
    """True if cache is missing or older than TTL_SECONDS."""
    if cached_at is None:
        return True
    if now is None:
        now = time.time()
    return (now - cached_at) > TTL_SECONDS

