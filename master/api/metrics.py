from __future__ import annotations

"""
Vigile — Prometheus Metrics Endpoint

Exposes native Prometheus-format metrics without any third-party library.
Zero external dependencies — pure Python with async DB queries.

Metrics exposed:
  - vigile_connected_workers_total (gauge)
  - vigile_proposals_pending_total (gauge)
  - vigile_database_latency_seconds (gauge)
  - vigile_nodes_total (gauge, by state)
  - vigile_nodes_lost (gauge)
  - vigile_intents_failed_total (counter, by node_id and action)
  - vigile_uptime_seconds (gauge)
  - vigile_master_info (gauge, with version label)
"""

import time
from typing import Any

from master.db.database import get_db_conn

METRIC_PREFIX = "vigile"

HELP_LINES: dict[str, str] = {
    "connected_workers_total": "Number of active worker WebSocket connections",
    "proposals_pending_total": "Number of action proposals awaiting human approval",
    "database_latency_seconds": "Database query round-trip latency in seconds",
    "nodes_total": "Total number of registered nodes by state",
    "uptime_seconds": "Master process uptime in seconds",
    "master_info": "Master node version and build information",
    "nodes_lost": "Number of nodes in LOST state",
    "intents_failed_total": "Total failed intents by node and action",
}

TYPE_LINES: dict[str, str] = {
    "connected_workers_total": "gauge",
    "proposals_pending_total": "gauge",
    "database_latency_seconds": "gauge",
    "nodes_total": "gauge",
    "uptime_seconds": "gauge",
    "master_info": "gauge",
    "nodes_lost": "gauge",
    "intents_failed_total": "counter",
}


def _metric_line(name: str, value: Any, labels: dict[str, str] | None = None) -> str:
    """Render a single Prometheus metric line with optional labels."""
    full_name = f"{METRIC_PREFIX}_{name}"
    if labels:
        label_parts = ",".join(f'{k}="{v}"' for k, v in labels.items())
        return f"{full_name}{{{label_parts}}} {value}"
    return f"{full_name} {value}"


def _with_help_type(name: str) -> str:
    """Generate HELP and TYPE lines for a metric."""
    help_text = HELP_LINES.get(name, "")
    type_text = TYPE_LINES.get(name, "gauge")
    return (
        f"# HELP {METRIC_PREFIX}_{name} {help_text}\n" f"# TYPE {METRIC_PREFIX}_{name} {type_text}"
    )


async def render_prometheus(connected_count: int, startup_time: float, version: str) -> str:
    """
    Collect and render all Prometheus metrics.

    Args:
        connected_count: Number of currently connected WebSocket workers.
        startup_time: Unix timestamp when the Master process started.
        version: Master version string (e.g. "0.6.0").

    Returns:
        A string in Prometheus exposition format (text/plain; version=0.0.4).
    """
    db = get_db_conn()
    now = time.time()
    lines: list[str] = []

    # 1. vigile_connected_workers_total
    lines.append(_with_help_type("connected_workers_total"))
    lines.append(_metric_line("connected_workers_total", connected_count))
    lines.append("")

    # 2. vigile_proposals_pending_total
    async with db.execute(
        "SELECT COUNT(*) AS cnt FROM action_proposals WHERE status = ?",
        ("PENDING",),
    ) as cursor:
        row = await cursor.fetchone()
    pending_count = row["cnt"] if row else 0
    lines.append(_with_help_type("proposals_pending_total"))
    lines.append(_metric_line("proposals_pending_total", pending_count))
    lines.append("")

    # 3. vigile_database_latency_seconds
    t0 = time.monotonic()
    cursor = await db.execute("SELECT 1")
    await cursor.fetchone()
    latency = time.monotonic() - t0
    lines.append(_with_help_type("database_latency_seconds"))
    lines.append(_metric_line("database_latency_seconds", f"{latency:.6f}"))
    lines.append("")

    # 4. vigile_nodes_total (by state)
    async with db.execute("SELECT state, COUNT(*) AS cnt FROM nodes GROUP BY state") as cursor:
        node_rows = await cursor.fetchall()
    lines.append(_with_help_type("nodes_total"))
    for node_row in node_rows:
        state = node_row["state"]
        cnt = node_row["cnt"]
        lines.append(_metric_line("nodes_total", cnt, {"state": state}))
    lines.append("")

    # 5. vigile_nodes_lost — reflects node_manager state (LOST nodes)
    async with db.execute(
        "SELECT COUNT(*) AS cnt FROM nodes WHERE state = ?", ("LOST",)
    ) as cursor:
        lost_row = await cursor.fetchone()
    lost_count = lost_row["cnt"] if lost_row else 0
    lines.append(_with_help_type("nodes_lost"))
    lines.append(_metric_line("nodes_lost", lost_count))
    lines.append("")

    # 6. vigile_intents_failed_total — reflects alert_engine intent failure tracking
    async with db.execute(
        "SELECT node_id, action, COUNT(*) AS cnt "
        "FROM action_proposals WHERE status = 'FAILED' "
        "GROUP BY node_id, action"
    ) as cursor:
        failed_rows = await cursor.fetchall()
    lines.append(_with_help_type("intents_failed_total"))
    for frow in failed_rows:
        lines.append(_metric_line(
            "intents_failed_total", frow["cnt"],
            {"node_id": frow["node_id"], "action": frow["action"]},
        ))
    lines.append("")

    # 7. vigile_uptime_seconds
    uptime = now - startup_time
    lines.append(_with_help_type("uptime_seconds"))
    lines.append(_metric_line("uptime_seconds", f"{uptime:.3f}"))
    lines.append("")

    # 8. vigile_master_info
    lines.append(_with_help_type("master_info"))
    lines.append(_metric_line("master_info", 1, {"version": version}))
    lines.append("")

    # Prometheus exposition format: end with a trailing newline
    return "\n".join(lines) + "\n"
