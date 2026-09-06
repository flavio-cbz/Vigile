"""
Vigile — Disk Scan Cache Helpers
Read/write cached disk-scan results in disk_scans_cache table and disk-mount lists in the nodes table.

Uses BEGIN IMMEDIATE via transaction() to serialize WAL writes.
"""

from __future__ import annotations

import json
import os

import aiosqlite

from master.db.database import transaction


async def get_cached_disk_scan(
    db: aiosqlite.Connection, node_id: str, path: str = "/"
) -> tuple[str | None, float | None]:
    """Return (json_string, timestamp) from disk_scans_cache for (node_id, path), or (None, None)."""
    clean_path = os.path.normpath(path.strip()) if path else "/"
    try:
        async with db.execute(
            "SELECT scan_json, scanned_at FROM disk_scans_cache WHERE node_id = ? AND path = ?",
            (node_id, clean_path),
        ) as cursor:
            row = await cursor.fetchone()
        if row is not None:
            return row["scan_json"], row["scanned_at"]
    except Exception:
        pass

    # Fallback to legacy nodes table if path is "/"
    if clean_path == "/":
        try:
            async with db.execute(
                "SELECT cached_disk_scan_json, cached_disk_scan_at FROM nodes WHERE id = ?",
                (node_id,),
            ) as cursor:
                legacy_row = await cursor.fetchone()
            if legacy_row is not None and legacy_row["cached_disk_scan_json"]:
                return legacy_row["cached_disk_scan_json"], legacy_row["cached_disk_scan_at"]
        except Exception:
            pass

    return None, None


async def set_cached_disk_scan(
    db: aiosqlite.Connection,
    node_id: str,
    path: str,
    json_data: str,
    timestamp: float,
) -> None:
    """Write disk-scan cache inside a BEGIN IMMEDIATE transaction."""
    clean_path = os.path.normpath(path.strip()) if path else "/"
    ts = float(timestamp)

    async with transaction(db) as tx_db:
        await tx_db.execute(
            """
            INSERT INTO disk_scans_cache (node_id, path, scan_json, scanned_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(node_id, path) DO UPDATE SET
                scan_json = excluded.scan_json,
                scanned_at = excluded.scanned_at
            """,
            (node_id, clean_path, json_data, ts),
        )
        if clean_path == "/":
            try:
                await tx_db.execute(
                    "UPDATE nodes SET cached_disk_scan_json = ?, cached_disk_scan_at = ? WHERE id = ?",
                    (json_data, ts, node_id),
                )
            except Exception:
                pass


async def invalidate_cached_disk_scan(
    db: aiosqlite.Connection, node_id: str, path: str | None = None
) -> None:
    """Invalidate cached disk scans for a node (optionally scoped to path)."""
    clean_path = os.path.normpath(path.strip()) if path is not None else None
    async with transaction(db) as tx_db:
        if clean_path is not None:
            await tx_db.execute(
                "DELETE FROM disk_scans_cache WHERE node_id = ? AND path = ?",
                (node_id, clean_path),
            )
            if clean_path == "/":
                try:
                    await tx_db.execute(
                        "UPDATE nodes SET cached_disk_scan_json = NULL, cached_disk_scan_at = NULL WHERE id = ?",
                        (node_id,),
                    )
                except Exception:
                    pass
        else:
            await tx_db.execute(
                "DELETE FROM disk_scans_cache WHERE node_id = ?",
                (node_id,),
            )
            try:
                await tx_db.execute(
                    "UPDATE nodes SET cached_disk_scan_json = NULL, cached_disk_scan_at = NULL WHERE id = ?",
                    (node_id,),
                )
            except Exception:
                pass


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
        if not isinstance(disks, list):
            return []
        mounts: list[str] = []
        for d in disks:
            if isinstance(d, str) and d.strip():
                mounts.append(os.path.normpath(d.strip()))
            elif isinstance(d, dict) and d.get("mount_point"):
                mounts.append(os.path.normpath(str(d["mount_point"]).strip()))
        return mounts
    except Exception:
        return []


async def set_node_disk_mounts(
    db: aiosqlite.Connection, node_id: str, mounts: list[str] | list[dict]
) -> None:
    """Persist a disk-mount list on the node row (idempotent), supporting strings and dicts."""
    cleaned: list[dict[str, str]] = []
    for m in mounts:
        if isinstance(m, str) and m.strip():
            cleaned.append({"mount_point": os.path.normpath(m.strip())})
        elif isinstance(m, dict) and m.get("mount_point"):
            cleaned.append({"mount_point": os.path.normpath(str(m["mount_point"]).strip())})

    async with transaction(db) as tx_db:
        await tx_db.execute(
            "UPDATE nodes SET cached_disks_json = ? WHERE id = ?",
            (json.dumps(cleaned), node_id),
        )
