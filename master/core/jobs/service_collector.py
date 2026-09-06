"""
Vigile — Service Collector Job (B4)

Periodically collects LIST_SERVICES from all connected Workers and writes
to the node's cached_services_json / cached_services_at columns.

- Concurrency bounded by asyncio.Semaphore(5) (thundering herd protection)
- asyncio.gather(..., return_exceptions=True) — one node's failure never poisons others
- set_cached_services only on success:true && parsed!=None (cache-poison guard)
- Schedule: 30s + jitter ±10s via asyncio.sleep (compatible with Scheduler's interval loop if needed)
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

COLLECT_INTERVAL: float = 30.0  # H8: 30s de base
JITTER_SECONDS: float = 10.0  # H8: jitter ±10s anti-thundering-herd

async def _collect_one(
    node_id: str,
    db: aiosqlite.Connection,
    port: Any,
    sem: asyncio.Semaphore,
) -> dict[str, Any]:
    """Collect services for a single node. Returns dict with success flag or exception info."""
    async with sem:
        try:
            # Timeout Master 12.0s pour laisser 2s de marge au Worker 10s (spec B4)
            result = await port.query(node_id, "LIST_SERVICES", timeout=12.0)
            if not result.get("success"):
                logger.warning(
                    "service_collector: node %s LIST_SERVICES success=false: %s",
                    node_id,
                    result.get("error"),
                )
                return {"node_id": node_id, "success": False, "error": result.get("error")}
            from master.core.plugin_utils import parse_worker_list
            from master.plugins.systemd import ServiceInfo

            parsed = parse_worker_list(result.get("output", ""), ServiceInfo)
            if parsed is None:
                logger.warning("service_collector: node %s unparseable service list", node_id)
                return {"node_id": node_id, "success": False, "error": "unparseable"}
            # H7bis guard: only write when success && parsed != None
            from master.db.service_cache import set_cached_services

            await set_cached_services(db, node_id, json.dumps(parsed), time.time())
            logger.info("service_collector: cached %d services for node %s", len(parsed), node_id)
            return {"node_id": node_id, "success": True, "count": len(parsed)}
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — catch all to prevent gather poison
            logger.warning("service_collector: failed for node %s: %s", node_id, exc)
            return {"node_id": node_id, "success": False, "error": str(exc)}


async def collect_services_for_all_nodes(
    db: aiosqlite.Connection,
    nm: Any,
) -> dict[str, Any]:
    """Collect LIST_SERVICES for all connected nodes in parallel (Semaphore 5).

    Returns:
        {"collected": int, "errors": list[str], "details": list[dict]}
    Never raises due to a single node's failure (return_exceptions=True).
    """
    connected = nm.connected_node_ids() if hasattr(nm, "connected_node_ids") else []
    if not connected:
        return {"collected": 0, "errors": [], "details": []}

    from master.core.worker_query_port import WorkerQueryPort

    port = WorkerQueryPort(nm)
    sem = asyncio.Semaphore(5)

    tasks = [_collect_one(nid, db, port, sem) for nid in connected]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    details: list[dict[str, Any]] = []
    errors: list[str] = []
    collected = 0
    for r in results:
        if isinstance(r, BaseException):
            errors.append(str(r))
            details.append({"success": False, "error": str(r)})
        elif isinstance(r, dict):
            details.append(r)
            if r.get("success"):
                collected += 1
            else:
                if r.get("error"):
                    errors.append(f"{r.get('node_id')}: {r.get('error')}")
        else:
            details.append({"success": False, "error": str(r)})

    return {"collected": collected, "errors": errors, "details": details}


async def service_collector_loop(
    db: aiosqlite.Connection,
    nm: Any,
    interval: float = COLLECT_INTERVAL,
    jitter: float = JITTER_SECONDS,
) -> None:
    """Background loop: sleep interval + jitter, then collect. Runs until cancelled."""
    logger.info(
        "service_collector_loop started (interval=%.1fs jitter=±%.1fs)",
        interval,
        jitter,
    )
    while True:
        try:
            # H8: 30s + jitter ±10s anti thundering herd
            sleep_for = interval + random.uniform(-jitter, jitter)
            await asyncio.sleep(sleep_for)
            await collect_services_for_all_nodes(db, nm)
        except asyncio.CancelledError:
            logger.info("service_collector_loop cancelled")
            break
        except Exception:
            logger.exception("service_collector_loop error (will retry)")
            await asyncio.sleep(5)

# Helper to register with existing Scheduler (optional)
def register_with_scheduler(scheduler: Any, nm: Any, db: aiosqlite.Connection) -> None:
    """Register the collector as a scheduler task (60s + jitter via scheduler's own jitter handling).

    The scheduler's _loop handles fixed cadence; we add jitter via interval randomisation
    inside the handler itself to keep the scheduler's anti-drift intact.
    """
    # Use a lightweight adapter instance so scheduler can call handler by name
    class _Adapter:
        async def run(self) -> None:
            await collect_services_for_all_nodes(db, nm)

    adapter = _Adapter()
    scheduler.start(
        "service_collector",
        [{"name": "collect_services", "interval_secs": COLLECT_INTERVAL, "handler": "run"}],
        adapter,
    )
