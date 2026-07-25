"""
Vigile — Disk Scan Cache Helpers
Read/write cached disk-scan results in the nodes table.

Uses BEGIN IMMEDIATE via transaction() to serialize WAL writes.
"""

from __future__ import annotations

import aiosqlite

from master.db.database import transaction


async def get_cached_disk_scan(
    db: aiosqlite.Connection, node_id: str
) -> tuple[str | None, float | None]:
    """Return (json_string, timestamp) from the node cache, or (None, None)."""
    async with db.execute(
        "SELECT cached_disk_scan_json, cached_disk_scan_at FROM nodes WHERE id = ?",
        (node_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None, None
    return row["cached_disk_scan_json"], row["cached_disk_scan_at"]


async def set_cached_disk_scan(
    db: aiosqlite.Connection, node_id: str, json_data: str, timestamp: float
) -> None:
    """Write disk-scan cache inside a BEGIN IMMEDIATE transaction."""
    async with transaction(db) as tx_db:
        await tx_db.execute(
            "UPDATE nodes SET cached_disk_scan_json = ?, cached_disk_scan_at = ? WHERE id = ?",
            (json_data, timestamp, node_id),
        )
