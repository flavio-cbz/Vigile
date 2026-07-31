from __future__ import annotations

"""
Vigile — Investigation Manager

Automatic alert investigation pipeline. When an alert fires, schedules a
Phase 3 LLM diagnostic analysis and stores the result in the `investigations`
table for operator review.

Flow:
  1. Alert fires in AlertEngine._fire_alert()
  2. Callback notifies InvestigationManager
  3. Investigation record created (status = "queued")
  4. Phase 3 analysis launched asynchronously via InsightsManager.analyze_anomaly()
  5. Result persisted in investigations (status = "completed" | "failed")
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any

import aiosqlite

from master.core.node_manager import NodeManager
from master.db.database import database_session

logger = logging.getLogger(__name__)


class InvestigationManager:
    """
    Manages the alert investigation lifecycle.

    Hooks into AlertEngine via on_alert_fired callback.
    Limits concurrent investigations globally (default: 3) to avoid
    saturating the LLM quota.
    """

    def __init__(self, max_concurrent: int = 3) -> None:
        self._insights: Any = None  # InsightsManager — lazy-loaded from DI
        self._max_concurrent = max_concurrent
        # Hard concurrency cap: at most `max_concurrent` investigations run at
        # the same time. `_reserved` is the synchronous reservation counter —
        # incremented before ANY await in on_alert_fired so concurrent alerts
        # can never both pass the cap check (the old `_active_count` race).
        self._sem = asyncio.Semaphore(max_concurrent)
        self._reserved = 0
        self._dropped_count = 0
        self._background_tasks: set[asyncio.Task] = set()

    @property
    def dropped_count(self) -> int:
        """Number of investigations dropped because the queue was full."""
        return self._dropped_count

    def _spawn_task(self, coro: Any, name: str) -> asyncio.Task:
        """Spawn a supervised background task tracked for graceful shutdown."""
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def ensure_tasks_complete(self, timeout: float = 30.0) -> None:
        """Wait for all background tasks to complete (graceful shutdown)."""
        if not self._background_tasks:
            return
        done, pending = await asyncio.wait(
            self._background_tasks, timeout=timeout
        )
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.wait(pending, timeout=5.0)
        self._background_tasks.clear()

    def _get_insights(self) -> Any:
        """Lazy-load InsightsManager from the DI layer."""
        if self._insights is None:
            try:
                from master.api.deps import get_insights_manager
                self._insights = get_insights_manager()
            except Exception:
                logger.warning("Failed to load InsightsManager — Phase 3 unavailable", exc_info=True)
        return self._insights

    def _get_node_manager(self) -> NodeManager:
        """Return the global node_manager singleton."""
        # Avoid import at module level to prevent circular imports
        from master.core.node_manager import node_manager as nm_singleton
        return nm_singleton

    # -------------------------------------------------------------------
    # Callback for AlertEngine — called when an alert fires
    # -------------------------------------------------------------------

    async def on_alert_fired(
        self,
        node_id: str,
        alert_name: str,
        severity: str,
        message: str,
        alert_id: str,
        db: aiosqlite.Connection,
        details: dict | None = None,
    ) -> str | None:
        """
        Called by AlertEngine when an alert fires.
        Creates an investigation record and queues Phase 3 analysis.
        Returns investigation ID or None if queued (concurrency cap).
        """
        investigation_id = str(uuid.uuid4())
        now = time.time()

        context = {
            "alert_id": alert_id,
            "alert_name": alert_name,
            "severity": severity,
            "message": message,
            "details": details or {},
        }

        # Check + reserve are synchronous with NO await in between — atomic in
        # the single-threaded event loop, unlike the old `_active_count` check.
        if self._reserved >= self._max_concurrent:
            self._dropped_count += 1
            drop_reason = (
                f"investigation queue full ({self._reserved}/{self._max_concurrent})"
            )
            logger.warning(
                "Investigation queue full (%d/%d) — dropping investigation for %s/%s",
                self._reserved, self._max_concurrent, node_id, alert_name,
            )
            try:
                await db.execute(
                    """INSERT INTO investigations
                       (id, alert_id, node_id, alert_name, severity, status,
                        context_json, result, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, 'dropped', ?, ?, ?, ?)""",
                    (
                        investigation_id, alert_id, node_id, alert_name, severity,
                        json.dumps(context),
                        json.dumps({"status": "dropped", "reason": drop_reason}),
                        now, now,
                    ),
                )
                await db.commit()
            except Exception as exc:
                logger.error("Failed to persist dropped investigation: %s", exc)
            return None

        self._reserved += 1

        try:
            await db.execute(
                """INSERT INTO investigations
                   (id, alert_id, node_id, alert_name, severity, status,
                    context_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?)""",
                (
                    investigation_id, alert_id, node_id, alert_name, severity,
                    json.dumps(context), now, now,
                ),
            )
            await db.commit()
        except Exception as exc:
            logger.error("Failed to create investigation: %s", exc)
            self._reserved -= 1
            return None

        logger.info(
            "Investigation %s created for alert %s on node %s",
            investigation_id[:12], alert_name, node_id[:12],
        )

        # Launch Phase 3 analysis asynchronously
        self._spawn_task(
            self._run_investigation(investigation_id, node_id),
            name=f"investigation:{investigation_id[:12]}",
        )

        return investigation_id

    # -------------------------------------------------------------------
    # Phase 3 execution
    # -------------------------------------------------------------------

    async def _run_investigation(
        self,
        investigation_id: str,
        node_id: str,
    ) -> None:
        """Execute Phase 3 LLM diagnostic and persist the result.

        The semaphore is the hard concurrency cap; each investigation opens
        its OWN pooled connection so concurrent runs never share the caller's
        aiosqlite connection (the shared-connection P0 hazard).
        """
        try:
            async with self._sem:
                async with database_session() as db:
                    inv_start = time.time()

                    try:
                        # Mark in_progress
                        await db.execute(
                            "UPDATE investigations SET status = 'in_progress', updated_at = ? WHERE id = ?",
                            (time.time(), investigation_id),
                        )
                        await db.commit()

                        # Run Phase 3 analysis
                        if self._insights is None or not self._insights._sllm:
                            result = {
                                "status": "skipped",
                                "reason": "LLM not configured on this Master",
                            }
                        else:
                            try:
                                report = await self._insights.analyze_anomaly(
                                    node_id=node_id,
                                    db=db,
                                    nm=self._get_node_manager(),
                                    locale="fr",
                                )
                                result = {
                                    "status": "completed",
                                    "report": report.model_dump(),
                                }
                            except Exception as exc:
                                logger.exception("Investigation %s Phase 3 failed", investigation_id[:12])
                                result = {
                                    "status": "failed",
                                    "error": str(exc),
                                }

                        # Persist result
                        await db.execute(
                            """UPDATE investigations SET
                                status = ?, result = ?, completed_at = ?, updated_at = ?
                               WHERE id = ?""",
                            (
                                "completed" if result.get("status") == "completed" else "failed",
                                json.dumps(result),
                                time.time(),
                                time.time(),
                                investigation_id,
                            ),
                        )
                        await db.commit()

                        duration = time.time() - inv_start
                        logger.info(
                            "Investigation %s completed in %.1fs with status=%s",
                            investigation_id[:12], duration, result.get("status", "unknown"),
                        )

                    except Exception as exc:
                        logger.exception("Investigation %s crashed", investigation_id[:12])
                        try:
                            await db.execute(
                                """UPDATE investigations SET status = 'failed', result = ?,
                                    completed_at = ?, updated_at = ? WHERE id = ?""",
                                (json.dumps({"error": str(exc)}), time.time(), time.time(), investigation_id),
                            )
                            await db.commit()
                        except Exception:
                            pass
        finally:
            self._reserved -= 1

    # -------------------------------------------------------------------
    # Query helpers
    # -------------------------------------------------------------------

    async def get_investigations(
        self,
        db: aiosqlite.Connection,
        node_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return paginated investigation list."""
        conditions: list[str] = []
        params: list[Any] = []
        if node_id:
            conditions.append("node_id = ?")
            params.append(node_id)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        # SAFE: conditions use ? markers, user values in params
        query = (
            f"SELECT * FROM investigations{where}"
            f" ORDER BY created_at DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# Module-level singleton — follows pattern of automation_engine, alert_engine
investigation_manager = InvestigationManager(max_concurrent=3)
