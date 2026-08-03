"""
Vigile — Nodes API: helper functions
"""

from __future__ import annotations

import time

from master.api.demo_data import is_demo
from master.api.deps import DB


def _node_to_response(node: dict) -> dict:
    """Map DB row dict to the NodeResponse field set."""
    enrolled_at = node.get("enrolled_at")
    enrolled_recently = bool(enrolled_at is not None and (time.time() - float(enrolled_at)) < 86400)
    return {
        "id": node["id"],
        "name": node.get("name", ""),
        "hostname": node.get("hostname"),
        "machine_id": node.get("machine_id"),
        "arch": node.get("arch"),
        "os": node.get("os"),
        "state": node["state"],
        "online": node.get("online", False),
        "last_heartbeat": node.get("last_heartbeat"),
        "enrolled_at": enrolled_at,
        "created_at": node["created_at"],
        "updated_at": node["updated_at"],
        "group": node.get("node_group") or None,
        "disabled": bool(node.get("disabled", 0)),
        "enrolled_recently": enrolled_recently,
        "version": node.get("worker_version") or node.get("version"),
        "worker_version": node.get("worker_version") or node.get("version"),
    }


async def _add_node_metrics(db: DB, node_dict: dict, claims: dict) -> dict:
    """Fetch and merge the latest metrics snapshot for a node."""
    if is_demo(claims):
        # Return some mock metrics for demo nodes
        if node_dict["id"] == "demo-node-01":
            node_dict.update(
                {
                    "cpu_percent": 12.5,
                    "memory_percent": 45.2,
                    "disk_percent": 38.4,
                    "uptime_seconds": 3600.0,
                }
            )
        elif node_dict["id"] == "demo-node-02":
            node_dict.update(
                {
                    "cpu_percent": 8.0,
                    "memory_percent": 30.1,
                    "disk_percent": 42.0,
                    "uptime_seconds": 1800.0,
                }
            )
        return node_dict

    async with db.execute(
        """
        SELECT cpu_percent, mem_percent, disk_percent, uptime_seconds
        FROM metrics_snapshots
        WHERE node_id = ?
        ORDER BY collected_at DESC
        LIMIT 1
        """,
        (node_dict["id"],),
    ) as cursor:
        snapshot = await cursor.fetchone()
    if snapshot:
        node_dict.update(
            {
                "cpu_percent": snapshot["cpu_percent"],
                "memory_percent": snapshot["mem_percent"],
                "disk_percent": snapshot["disk_percent"],
                "uptime_seconds": snapshot["uptime_seconds"],
            }
        )
    return node_dict


async def _add_bulk_node_metrics(db: DB, node_dicts: list[dict], claims: dict) -> list[dict]:
    """Fetch and merge the latest metrics snapshots for a list of nodes in bulk."""
    if is_demo(claims):
        for nd in node_dicts:
            if nd["id"] == "demo-node-01":
                nd.update(
                    {
                        "cpu_percent": 12.5,
                        "memory_percent": 45.2,
                        "disk_percent": 38.4,
                        "uptime_seconds": 3600.0,
                    }
                )
            elif nd["id"] == "demo-node-02":
                nd.update(
                    {
                        "cpu_percent": 8.0,
                        "memory_percent": 30.1,
                        "disk_percent": 42.0,
                        "uptime_seconds": 1800.0,
                    }
                )
        return node_dicts

    node_ids = [n["id"] for n in node_dicts]
    if not node_ids:
        return node_dicts

    placeholders = ",".join("?" for _ in node_ids)
    snapshots_map = {}
    async with db.execute(
        f"""
        WITH RankedSnapshots AS (
            SELECT
                node_id,
                cpu_percent,
                mem_percent,
                disk_percent,
                uptime_seconds,
                ROW_NUMBER() OVER (PARTITION BY node_id ORDER BY collected_at DESC) as rn
            FROM metrics_snapshots
            WHERE node_id IN ({placeholders})
        )
        SELECT node_id, cpu_percent, mem_percent, disk_percent, uptime_seconds
        FROM RankedSnapshots
        WHERE rn = 1
        """,
        tuple(node_ids),
    ) as cursor:
        for row in await cursor.fetchall():
            snapshots_map[row["node_id"]] = {
                "cpu_percent": row["cpu_percent"],
                "memory_percent": row["mem_percent"],
                "disk_percent": row["disk_percent"],
                "uptime_seconds": row["uptime_seconds"],
            }

    for nd in node_dicts:
        snap = snapshots_map.get(nd["id"])
        if snap:
            nd.update(snap)
    return node_dicts
