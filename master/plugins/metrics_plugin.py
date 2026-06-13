"""
Vigile — Metrics Plugin

Normalizes and validates STATUS_REPORT messages from Workers.

This plugin runs on the Master side. It defines:
  - MetricsSnapshot: Pydantic model for status report validation
  - Hooks into the plugin system for status report processing

Hooks registered:
  - get_supported_actions  → ["GET_STATS"]
  - normalize_status_report → validates raw report into MetricsSnapshot
  - on_status_report       → persists metrics into the metrics_snapshots table

Zero dependencies beyond the project whitelist (pydantic).
"""

import logging
import time
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model for a metrics snapshot from a Worker
# ---------------------------------------------------------------------------


class MetricsSnapshot(BaseModel):
    """
    Validated schema for a STATUS_REPORT from a Worker node.

    Fields match what a lightweight Go agent can collect from /proc
    and platform APIs without requiring any external dependencies.

    All fields have safe defaults (0 / empty) so partial reports
    are still accepted but zero-values flag missing data.
    """

    # CPU
    cpu_percent: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="CPU usage as percentage (0-100)",
    )
    cpu_load_1m: float | None = Field(
        default=None,
        ge=0.0,
        description="CPU load average over 1 minute",
    )
    cpu_load_5m: float | None = Field(
        default=None,
        ge=0.0,
        description="CPU load average over 5 minutes",
    )
    cpu_load_15m: float | None = Field(
        default=None,
        ge=0.0,
        description="CPU load average over 15 minutes",
    )
    cpu_cores: int | None = Field(
        default=None,
        ge=1,
        description="Number of CPU cores detected",
    )

    # Memory
    mem_total_bytes: int = Field(
        default=0,
        ge=0,
        description="Total physical RAM in bytes",
    )
    mem_used_bytes: int = Field(
        default=0,
        ge=0,
        description="Used physical RAM in bytes",
    )
    mem_percent: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Memory usage as percentage (0-100)",
    )

    # Swap
    swap_total_bytes: int = Field(
        default=0,
        ge=0,
        description="Total swap space in bytes",
    )
    swap_used_bytes: int = Field(
        default=0,
        ge=0,
        description="Used swap space in bytes",
    )

    # Disk
    disk_total_bytes: int = Field(
        default=0,
        ge=0,
        description="Total disk space in bytes (root partition)",
    )
    disk_used_bytes: int = Field(
        default=0,
        ge=0,
        description="Used disk space in bytes (root partition)",
    )
    disk_percent: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Disk usage as percentage (0-100)",
    )

    # System
    uptime_seconds: float = Field(
        default=0.0,
        ge=0.0,
        description="System uptime in seconds",
    )
    processes: int | None = Field(
        default=None,
        ge=0,
        description="Number of running processes",
    )

    # Timestamp (set by Master on arrival, Worker may also send its own)
    collected_at: float = Field(
        default_factory=time.time,
        description="Unix timestamp when metrics were collected",
    )

    @property
    def mem_free_bytes(self) -> int:
        """Derived: free memory = total - used."""
        return self.mem_total_bytes - self.mem_used_bytes

    @property
    def disk_free_bytes(self) -> int:
        """Derived: free disk = total - used."""
        return self.disk_total_bytes - self.disk_used_bytes

    def to_prometheus_labels(self) -> dict[str, str | float | int]:
        """
        Flatten to a dict suitable for Prometheus-style metric labels.
        Useful if we add a /metrics endpoint later (Sprint 5).
        """
        return {
            "cpu_percent": self.cpu_percent,
            "cpu_load_1m": self.cpu_load_1m or 0.0,
            "mem_percent": self.mem_percent,
            "mem_used_bytes": self.mem_used_bytes,
            "disk_percent": self.disk_percent,
            "disk_used_bytes": self.disk_used_bytes,
            "uptime_seconds": self.uptime_seconds,
        }

    def model_dump_flat(self) -> dict[str, Any]:
        """Return a flat dict of all fields (for DB storage / JSON serialization)."""
        return self.model_dump()


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------


def register(pm) -> None:
    """
    Register metrics plugin hooks.

    Hooks provided:
      - get_supported_actions() -> list[str]
          Returns the actions this plugin supports (e.g. "GET_STATS").
      - normalize_status_report(raw_report: dict) -> dict | None
          Validates a raw STATUS_REPORT message from a Worker.
          Returns a normalized MetricsSnapshot dict, or None if invalid.
      - on_status_report(node_id: str, snapshot: dict, db=None) -> None
          Called when a valid status report arrives from a Worker.
          Persists the snapshot into the metrics_snapshots table.
          Falls back to logging if db is None (graceful degradation).

    Usage (from worker_handler.py):
        raw = msg  # STATUS_REPORT from WebSocket
        snap = pm.call_first("normalize_status_report", raw_report=raw)
        if snap:
            await pm.async_call("on_status_report", node_id=node_id, snapshot=snap)
    """
    pm.register("get_supported_actions", _get_supported_actions, plugin_name="metrics")
    pm.register("normalize_status_report", _normalize_status_report, plugin_name="metrics")
    pm.register("on_status_report", _on_status_report, plugin_name="metrics")

    logger.info("Metrics plugin registered.")


# ---------------------------------------------------------------------------
# Hook implementations
# ---------------------------------------------------------------------------


def get_config_schema() -> dict[str, Any]:
    """Return plugin info and configuration schema."""
    return {
        "name": "Metrics Collector",
        "description": "Collects and persists system health telemetry (CPU cores, loads, memory, swap, and disk percentages) via /proc pipelines.",
        "category": "Monitoring",
        "schema": {
            "polling_interval": {
                "type": "integer",
                "title": "Polling Interval (seconds)",
                "default": 60,
                "description": "Frequency of metrics collection reports sent from the worker.",
            },
            "retention_days": {
                "type": "integer",
                "title": "Metrics Retention (days)",
                "default": 30,
                "description": "Number of days to keep historical metrics snapshots in the database.",
            },
        },
    }


def _get_supported_actions() -> list[str]:
    """Declare that this plugin handles the GET_STATS action."""
    return ["GET_STATS"]


def _normalize_status_report(raw_report: dict) -> dict | None:
    """
    Validate a raw STATUS_REPORT message from a Worker.

    Accepts both:
      - A dict with metrics directly (flat keys)
      - A dict with a "metrics" sub-key (nested)

    Returns a validated MetricsSnapshot as a plain dict, or None if invalid.
    """
    if not isinstance(raw_report, dict):
        logger.warning("normalize_status_report: raw_report is not a dict")
        return None

    # Support nested { "metrics": {...} } format
    data = raw_report.get("metrics", raw_report)

    try:
        snapshot = MetricsSnapshot(**data)
        logger.debug(
            "Status report normalized: CPU=%.1f%% MEM=%.1f%% DISK=%.1f%%",
            snapshot.cpu_percent,
            snapshot.mem_percent,
            snapshot.disk_percent,
        )
        return snapshot.model_dump_flat()
    except Exception as exc:
        logger.warning("Invalid status report: %s", exc)
        return None


async def _on_status_report(node_id: str, snapshot: dict, db=None) -> None:
    """
    Handle a validated status report from a Worker.

    Persists the snapshot into the metrics_snapshots table for
    later retrieval via GET /api/nodes/{id}/stats.

    Falls back to logging if no db handle is provided (graceful degradation).
    """
    cpu = snapshot.get("cpu_percent", 0)
    mem = snapshot.get("mem_percent", 0)
    disk = snapshot.get("disk_percent", 0)
    logger.info("Metrics [%s]: CPU=%.1f%% MEM=%.1f%% DISK=%.1f%%", node_id, cpu, mem, disk)

    if db is None:
        logger.debug("on_status_report: no DB handle — skipping persistence")
        return

    import time
    import uuid

    now = time.time()
    row_id = str(uuid.uuid4())

    await db.execute(
        """
        INSERT INTO metrics_snapshots (
            id, node_id, collected_at, created_at,
            cpu_percent, cpu_load_1m, cpu_load_5m, cpu_load_15m, cpu_cores,
            mem_total_bytes, mem_used_bytes, mem_percent,
            swap_total_bytes, swap_used_bytes,
            disk_total_bytes, disk_used_bytes, disk_percent,
            uptime_seconds, processes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row_id,
            node_id,
            snapshot.get("collected_at", now),
            now,
            snapshot.get("cpu_percent", 0),
            snapshot.get("cpu_load_1m"),
            snapshot.get("cpu_load_5m"),
            snapshot.get("cpu_load_15m"),
            snapshot.get("cpu_cores"),
            snapshot.get("mem_total_bytes", 0),
            snapshot.get("mem_used_bytes", 0),
            snapshot.get("mem_percent", 0),
            snapshot.get("swap_total_bytes", 0),
            snapshot.get("swap_used_bytes", 0),
            snapshot.get("disk_total_bytes", 0),
            snapshot.get("disk_used_bytes", 0),
            snapshot.get("disk_percent", 0),
            snapshot.get("uptime_seconds", 0),
            snapshot.get("processes"),
        ),
    )
    await db.commit()
    logger.debug("Metrics snapshot persisted for node %s (id=%s)", node_id, row_id)
