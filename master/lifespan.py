from __future__ import annotations

"""
Lifespan management for Vigile Master Node.

This module contains the lifespan context manager and related startup/shutdown logic.
"""

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI

from master.config import settings
from master.core.alert_engine import alert_engine
from master.core.enums import NodeState
from master.core.investigation_manager import investigation_manager
from master.core.node_manager import node_manager
from master.core.insights import InsightsManager
from master.core.plugin_engine import PluginEngine, PageRegistry
from master.core.proposal_autoexpire import auto_expire_proposals
from master.core.route_registrar import RouteRegistrar
from master.core.scheduler import Scheduler
from master.core.db_auto import DBAuto
from master.core.rate_limiter import rate_limiter
from master.core.security_manager import init_security, load_or_generate_master_key
from master.db.database import close_db, init_db, transaction
from master.db.migrations import run_migrations, run_seeds
from master.auto_update import auto_update_workers_task
from master.proposal_expiry import proposal_expiry_task
from master.core.outbox import outbox
from master.core.proposal_dispatcher import ApprovedProposalDispatcher

logger = logging.getLogger(__name__)


async def _on_node_connected(node_id: str, new_state: str, db: Any) -> None:
    """Fire a one-shot DISK_SCAN the first time a node goes CONNECTED."""
    if new_state != NodeState.CONNECTED.value:
        return
    try:
        await node_manager.trigger_disk_scan(node_id, db, force=True)
    except Exception as exc:
        logger.warning(
            "Failed to trigger background disk scan for node %s: %s", node_id, exc
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Async context manager for application startup and shutdown.

    Startup order:
      1. Open SQLite database
      2. Run migrations (idempotent)
      3. Initialize SecurityManager (DI from settings)
      4. Load plugins
      5. Start NodeManager heartbeat monitor

    Shutdown order (reverse):
      4. Stop NodeManager (close active WebSockets)
      3. (plugins don't need teardown in Sprint 1)
      2. (migrations are idempotent — no teardown)
      1. Close database
    """
    # ── Startup ───────────────────────────────────────────────────────────
    # Load LLM settings override if exists (files I/O belongs to edge)
    import anyio

    override_path = Path(settings.database_path).parent / "settings_override.json"

    def _read_overrides() -> dict | None:
        if override_path.exists():
            with override_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        return None

    try:
        overrides = await anyio.to_thread.run_sync(_read_overrides)
        if overrides:
            settings.apply_overrides(
                base_url=overrides.get("llm_base_url", settings.llm_base_url),
                api_key=overrides.get("llm_api_key", settings.llm_api_key),
                model=overrides.get("llm_model", settings.llm_model),
            )
            logger.info("Loaded LLM settings overrides from %s", override_path)
    except Exception as e:
        logger.error("Failed to load settings overrides: %s", e)

    logger.info("=" * 60)
    logger.info("Vigile — Master Node starting up")
    logger.info("  Master URL : %s", settings.master_url)
    logger.info("  Database   : %s", settings.database_path)
    logger.info("  Debug mode : %s", settings.debug)
    logger.info("=" * 60)

    if settings.allow_insecure:
        logger.warning(
            "⚠️  INSECURE MODE ENABLED (ALLOW_INSECURE=true). "
            "HTTPS/WSS enforcement is disabled and cookies are not secure. "
            "DO NOT USE IN PRODUCTION!"
        )
    else:
        logger.info("🔒 Secure mode active: HTTPS/WSS is enforced.")

    # 1. Init DB
    db = await init_db(settings.database_path, timeout=settings.db_timeout, pool_size=settings.db_pool_size)
    logger.info("Database connection established.")

    # 2. Migrations (DDL only)
    await run_migrations(db)

    # 2b. Seeds (admin user, default plugins — idempotent, never overwrites operator config)
    await run_seeds(db)

    # Reset any nodes left in CONNECTED, ENROLLING, or RECONNECTING states to LOST on startup
    async with transaction(db):
        await db.execute(
            "UPDATE nodes SET state = ? WHERE state IN (?, ?, ?)",
            (
                NodeState.LOST.value,
                NodeState.CONNECTED.value,
                NodeState.ENROLLING.value,
                NodeState.RECONNECTING.value,
            ),
        )
    logger.info("Stale node states reset to LOST on startup.")

    # 3. (Jinja2 templates removed in favor of React SPA)

    # 4. Initialize SecurityManager (with explicit DI from settings)
    master_key = load_or_generate_master_key(settings.master_key_path)
    init_security(
        server_secret=settings.server_secret_key,
        jwt_secret=settings.jwt_secret_key,
        jwt_algorithm=settings.jwt_algorithm,
        join_token_ttl=settings.join_token_ttl,
        worker_token_ttl=settings.worker_token_ttl,
        worker_token_rotation=settings.worker_token_rotation,
        jwt_access_token_ttl=settings.jwt_access_token_ttl,
        jwt_refresh_token_ttl=settings.jwt_refresh_token_ttl,
        master_private_key=master_key,
    )
    scheduler = Scheduler()
    route_registrar = RouteRegistrar(app)
    db_auto = DBAuto(db)
    engine = PluginEngine(
        scheduler=scheduler,
        route_registrar=route_registrar,
        page_registry=PageRegistry(),
        db_auto=db_auto,
        db=db,
        settings=settings,
    )
    import master.core.plugin_manager as _pm
    _pm.plugin_engine = engine
    _pm.plugin_manager = engine
    _pm.plugin_manager.set_engine(engine)

    await engine.initialize(db, sandbox=settings.plugin_sandbox)
    logger.info("Plugins loaded: %s", engine.loaded_plugins)

    # ── Startup Reconciliation ──────────────────────────────────────────
    # Recover from incomplete state after a crash or restart.
    # All failures are logged but do not block startup.

    # (a) Replay unprocessed outbox entries
    try:
        replayed = await outbox.replay_unprocessed(db)
        if replayed:
            logger.info("Outbox replay completed: %d entries processed", replayed)
        else:
            logger.info("Outbox replay completed — no unprocessed entries.")
    except Exception:
        logger.exception("Outbox replay failed during startup reconciliation")

    # (b) Dispatch APPROVED proposals that were never dispatched
    try:
        async with transaction(db):
            cursor = await db.execute(
                "SELECT id, node_id FROM action_proposals WHERE status = 'APPROVED' AND dispatch_id IS NULL"
            )
            pending = await cursor.fetchall()
        if pending:
            dispatcher = ApprovedProposalDispatcher(node_manager)
            for row in pending:
                try:
                    await dispatcher.dispatch_approved(row["id"], db, intent_timeout=30.0)
                    logger.info(
                        "Reconciled approved proposal %s for node %s",
                        row["id"], row["node_id"],
                    )
                except Exception:
                    logger.warning(
                        "Failed to dispatch approved proposal %s for node %s",
                        row["id"], row["node_id"],
                    )
        else:
            logger.info("No pending approved proposals to reconcile.")
    except Exception:
        logger.exception("Approved proposals reconciliation failed during startup")

    # (c) Reset plugins stuck in LOADING or STOPPING states
    try:
        async with transaction(db):
            await db.execute(
                "UPDATE plugins SET status = 'DISABLED', enabled = 0 WHERE status IN ('LOADING', 'STOPPING')"
            )
        logger.info("Plugin state reconciliation completed (LOADING/STOPPING → DISABLED).")
    except Exception:
        logger.exception("Plugin state reconciliation failed during startup")

    # 6. Node Manager
    insights_manager = InsightsManager()
    await node_manager.start(
        heartbeat_interval=settings.heartbeat_interval,
        lost_threshold=settings.heartbeat_lost_threshold,
        stale_threshold=settings.heartbeat_stale_threshold,
        default_intent_max_age=settings.default_intent_max_age,
        cache_update_interval=settings.cache_update_interval,
        insights_manager=insights_manager,
    )

    # 6b. Disk Scan — background trigger on first CONNECTED + 12h periodic via _cache_updater.
    node_manager.register_state_change_callback(_on_node_connected)
    logger.info("Disk scan background trigger registered for CONNECTED state changes.")

    # 6c. Insights — re-profile when node reconnects after being LOST for >4h.
    async def _on_node_reconnected(node_id: str, new_state: str, db: Any) -> None:
        """Re-profile when a node reconnects after being LOST for >4 hours."""
        if new_state != NodeState.CONNECTED.value:
            return
        try:
            async with db.execute(
                "SELECT last_heartbeat FROM nodes WHERE id = ?", (node_id,)
            ) as cursor:
                row = await cursor.fetchone()
            if row and row[0] and (time.time() - row[0]) > 14400:  # 4h
                logger.info(
                    "Node %s reconnected after >4h LOST. Triggering re-profile.", node_id
                )
                insights_manager.invalidate_cache(node_id)
                asyncio.create_task(
                    insights_manager.generate_profile(node_id, db, node_manager, force=True)
                )
        except Exception as exc:
            logger.warning(
                "Failed to check LOST duration for re-profile on node %s: %s",
                node_id, exc,
            )

    node_manager.register_state_change_callback(_on_node_reconnected)
    logger.info("Insights re-profile callback registered for LOST→CONNECTED transitions.")

    # 7. Alert Engine (évaluation des seuils intégrés)
    await alert_engine.initialize(db)
    node_manager.register_state_change_callback(alert_engine.evaluate_node_state)
    engine.register(
        "on_status_report",
        alert_engine.evaluate_metrics,
        plugin_name="alert_engine",
    )
    logger.info("Alert Engine initialized and registered.")

    # 7c. Investigation Manager (alerte → Phase 3 automatique)
    alert_engine.on_alert_fired_callback = investigation_manager.on_alert_fired
    logger.info("Investigation Manager initialized and wired to AlertEngine.")

    app.state.startup_time = time.time()
    app.state.master_url = settings.master_url
    app.state.trusted_proxies = settings.trusted_proxies
    rate_limiter.trusted_proxies = settings.trusted_proxies

    # 8. Start Rate Limiter Cleanup Task
    cleanup_task = rate_limiter.start_cleanup_task(app)

    # 9. Start Worker Auto-Update Task
    auto_update_task = asyncio.create_task(auto_update_workers_task(db, node_manager, settings))

    # 10. Start Proposal Auto-Expiry Task
    proposal_expiry = asyncio.create_task(proposal_expiry_task(db, node_manager, settings))

    # 11. Start Alert Cleanup Task (toutes les heures)
    async def alert_cleanup_loop() -> None:
        while True:
            await asyncio.sleep(3600)
            try:
                await alert_engine.cleanup_old_alerts(db)
            except Exception:
                logger.exception("Alert cleanup task failed.")

    cleanup_alerts = asyncio.create_task(alert_cleanup_loop())

    # 12. Outbox dispatch loop (toutes les 15 s) — at-least-once delivery
    async def outbox_dispatch_loop() -> None:
        while True:
            await asyncio.sleep(15)
            try:
                await outbox.process_pending(db, batch_size=100)
            except Exception:
                logger.exception("Outbox dispatch task failed.")

    outbox_dispatch = asyncio.create_task(outbox_dispatch_loop())

    # 13. Outbox cleanup loop (toutes les heures) — purge processed entries
    #     older than 7 days so the outbox table stays bounded.
    async def outbox_cleanup_loop() -> None:
        while True:
            await asyncio.sleep(3600)
            try:
                await outbox.cleanup_old(time.time() - 7 * 86400, db)
            except Exception:
                logger.exception("Outbox cleanup task failed.")

    outbox_cleanup = asyncio.create_task(outbox_cleanup_loop())

    logger.info("Master Node ready. 🚀")

    yield  # ← application runs here

    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("Master Node shutting down...")
    cleanup_task.cancel()
    auto_update_task.cancel()
    proposal_expiry.cancel()
    cleanup_alerts.cancel()
    outbox_dispatch.cancel()
    outbox_cleanup.cancel()
    try:
        await engine.shutdown()
    except Exception:
        logger.exception("Plugin engine shutdown failed.")
    try:
        await asyncio.gather(
            cleanup_task,
            auto_update_task,
            proposal_expiry,
            cleanup_alerts,
            outbox_dispatch,
            outbox_cleanup,
            return_exceptions=True
        )
    except Exception:
        pass
    await node_manager.stop()

    # Close shared httpx client pool
    try:
        from master.core.llm_http_pool import close_shared_client

        await close_shared_client()
    except Exception:
        logger.exception("Failed to close shared httpx client")

    await close_db()
    logger.info("Shutdown complete.")
