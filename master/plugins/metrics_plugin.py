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

import json
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

    # Per-mount disk inventory (Sprint 7) — raw array from Worker
    disks: list[dict] | None = Field(
        default=None,
        description="Per-mount disk stats: mount_point, fs_type, device, total_bytes, used_bytes, percent",
    )

    # Per-process CPU & memory (top N by CPU)
    top_processes: list[dict] | None = Field(
        default=None,
        description="Top CPU-consuming processes: pid, name, cpu_percent, mem_rss_kb, state",
    )

    # Network I/O (cumulative since boot, aggregate across non-loopback interfaces)
    net_bytes_recv: int | None = Field(
        default=None, ge=0,
        description="Total bytes received across all non-loopback interfaces since boot",
    )
    net_bytes_sent: int | None = Field(
        default=None, ge=0,
        description="Total bytes transmitted across all non-loopback interfaces since boot",
    )
    net_packets_recv: int | None = Field(
        default=None, ge=0,
        description="Total packets received since boot",
    )
    net_packets_sent: int | None = Field(
        default=None, ge=0,
        description="Total packets transmitted since boot",
    )
    net_errors_in: int | None = Field(
        default=None, ge=0,
        description="Total receive errors since boot",
    )
    net_errors_out: int | None = Field(
        default=None, ge=0,
        description="Total transmit errors since boot",
    )
    net_drops_in: int | None = Field(
        default=None, ge=0,
        description="Total receive drops since boot",
    )
    net_drops_out: int | None = Field(
        default=None, ge=0,
        description="Total transmit drops since boot",
    )

    # Disk I/O (cumulative since boot, aggregate across physical devices)
    disk_reads: int | None = Field(
        default=None, ge=0,
        description="Total disk reads completed since boot (aggregate across physical devices)",
    )
    disk_writes: int | None = Field(
        default=None, ge=0,
        description="Total disk writes completed since boot",
    )
    disk_read_bytes: int | None = Field(
        default=None, ge=0,
        description="Total bytes read from disk since boot",
    )
    disk_write_bytes: int | None = Field(
        default=None, ge=0,
        description="Total bytes written to disk since boot",
    )

    # Temperature (max across thermal zones, Celsius)
    temp_celsius: float | None = Field(
        default=None, ge=0.0,
        description="Maximum temperature across all thermal zones (Celsius)",
    )

    # PSI — Pressure Stall Information (avg10)
    psi_cpu_avg10: float | None = Field(
        default=None, ge=0.0,
        description="CPU pressure stall information — avg10",
    )
    psi_mem_avg10: float | None = Field(
        default=None, ge=0.0,
        description="Memory pressure stall information — avg10",
    )
    psi_io_avg10: float | None = Field(
        default=None, ge=0.0,
        description="I/O pressure stall information — avg10",
    )

    # File handles / inodes
    file_handles_used: int | None = Field(
        default=None, ge=0,
        description="Number of file handles currently in use",
    )
    file_handles_max: int | None = Field(
        default=None, ge=0,
        description="Maximum file handles allowed (kernel limit)",
    )

    # Entropy available
    entropy_avail: int | None = Field(
        default=None, ge=0,
        description="Available entropy in bits (for /dev/random)",
    )

    # Context switches since boot
    context_switches: int | None = Field(
        default=None, ge=0,
        description="Total context switches since boot",
    )

    # CPU throttling (aggregate core throttle count)
    cpu_throttled_count: int | None = Field(
        default=None, ge=0,
        description="Aggregate number of CPU core throttle events since boot",
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
            uptime_seconds, processes, disks_json, top_processes_json,
            net_bytes_recv, net_bytes_sent, net_packets_recv, net_packets_sent,
            net_errors_in, net_errors_out, net_drops_in, net_drops_out,
            disk_reads, disk_writes, disk_read_bytes, disk_write_bytes,
            temp_celsius,
            psi_cpu_avg10, psi_mem_avg10, psi_io_avg10,
            file_handles_used, file_handles_max,
            entropy_avail, context_switches, cpu_throttled_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            json.dumps(snapshot["disks"]) if snapshot.get("disks") else None,
            json.dumps(snapshot["top_processes"]) if snapshot.get("top_processes") else None,
            # Network I/O
            snapshot.get("net_bytes_recv"),
            snapshot.get("net_bytes_sent"),
            snapshot.get("net_packets_recv"),
            snapshot.get("net_packets_sent"),
            snapshot.get("net_errors_in"),
            snapshot.get("net_errors_out"),
            snapshot.get("net_drops_in"),
            snapshot.get("net_drops_out"),
            # Disk I/O
            snapshot.get("disk_reads"),
            snapshot.get("disk_writes"),
            snapshot.get("disk_read_bytes"),
            snapshot.get("disk_write_bytes"),
            # Temperature
            snapshot.get("temp_celsius"),
            # PSI
            snapshot.get("psi_cpu_avg10"),
            snapshot.get("psi_mem_avg10"),
            snapshot.get("psi_io_avg10"),
            # File handles
            snapshot.get("file_handles_used"),
            snapshot.get("file_handles_max"),
            # Entropy / context switches / CPU throttling
            snapshot.get("entropy_avail"),
            snapshot.get("context_switches"),
            snapshot.get("cpu_throttled_count"),
        ),
    )
    await db.commit()
    logger.debug("Metrics snapshot persisted for node %s (id=%s)", node_id, row_id)
