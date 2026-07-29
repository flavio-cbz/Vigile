"""
Vigile — Disk Scan Cache Helpers
Read/write cached disk-scan results and disk-mount lists in the nodes table.

Uses BEGIN IMMEDIATE via transaction() to serialize WAL writes.
"""

from __future__ import annotations

import json

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


async def get_node_disk_mounts(
    db: aiosqlite.Connection, node_id: str
) -> list[str]:
    """Return the list of mount_points cached on the node row, or empty list."""
    async with db.execute(
        "SELECT cached_disks_json FROM nodes WHERE id = ?", (node_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if not row or not row["cached_disks_json"]:
        return []
    try:
        disks = json.loads(row["cached_disks_json"])
        return [d["mount_point"] for d in disks if d.get("mount_point")]
    except (json.JSONDecodeError, TypeError, KeyError):
        return []


async def set_node_disk_mounts(
    db: aiosqlite.Connection, node_id: str, mounts: list[str]
) -> None:
    """Persist a disk-mount list on the node row (idempotent)."""
    async with transaction(db) as tx_db:
        await tx_db.execute(
            "UPDATE nodes SET cached_disks_json = ? WHERE id = ?",
            (json.dumps(mounts), node_id),
        )
