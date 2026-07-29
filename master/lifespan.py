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
from typing import AsyncGenerator

from fastapi import FastAPI

from master.config import settings
from master.core.alert_engine import alert_engine
from master.core.automation_engine import automation_engine
from master.core.enums import NodeState
from master.core.investigation_manager import investigation_manager
from master.core.node_manager import node_manager
from master.core.plugin_engine import PluginEngine, PageRegistry
from master.core.proposal_autoexpire import auto_expire_proposals
from master.core.route_registrar import RouteRegistrar
from master.core.scheduler import Scheduler
from master.core.db_auto import DBAuto
from master.core.rate_limiter import rate_limiter
from master.core.security_manager import init_security, load_or_generate_master_key
from master.db.database import close_db, init_db, transaction
from master.db.migrations import run_migrations
from master.auto_update import auto_update_workers_task
from master.proposal_expiry import proposal_expiry_task

logger = logging.getLogger(__name__)


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

    # 2. Migrations
    await run_migrations(db)

    # Ensure default plugins are always enabled (idempotent upsert)
    from master.db.migrations import _seed_default_plugins
    await _seed_default_plugins(db)

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
    _pm.plugin_manager.set_engine(engine)
    _pm.plugin_manager = engine
    await engine.initialize(db, sandbox=settings.plugin_sandbox)
    logger.info("Plugins loaded: %s", engine.loaded_plugins)

    # 6. Node Manager
    await node_manager.start(
        heartbeat_interval=settings.heartbeat_interval,
        lost_threshold=settings.heartbeat_lost_threshold,
        stale_threshold=settings.heartbeat_stale_threshold,
        default_intent_max_age=settings.default_intent_max_age,
        cache_update_interval=settings.cache_update_interval,
    )

    # 7. Automation Engine
    await automation_engine.initialize(db)
    node_manager.register_state_change_callback(automation_engine.evaluate_state_trigger)
    engine.register(
        "on_status_report",
        automation_engine.evaluate_metric_trigger,
        plugin_name="automation_engine",
    )
    logger.info("Automation Engine initialized and state-change callback registered.")

    # 7b. Alert Engine (évaluation des seuils intégrés)
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
    # Wire alert engine → automation engine for alert-based triggers
    alert_engine.on_automation_alert_callback = automation_engine.evaluate_alert_callback
    logger.info("Investigation Manager initialized and wired to AlertEngine.")

    app.state.startup_time = time.time()
    app.state.master_url = settings.master_url
    app.state.trusted_proxies = settings.trusted_proxies
    rate_limiter.trusted_proxies = settings.trusted_proxies

    # 7. Start Rate Limiter Cleanup Task
    cleanup_task = rate_limiter.start_cleanup_task(app)

    # 8. Start Worker Auto-Update Task
    auto_update_task = asyncio.create_task(auto_update_workers_task(db, node_manager, settings))

    # 9. Start Proposal Auto-Expiry Task
    proposal_expiry = asyncio.create_task(proposal_expiry_task(db, node_manager, settings))

    # 10. Start Alert Cleanup Task (toutes les heures)
    async def alert_cleanup_loop() -> None:
        while True:
            await asyncio.sleep(3600)
            try:
                await alert_engine.cleanup_old_alerts(db)
            except Exception:
                logger.exception("Alert cleanup task failed.")

    cleanup_alerts = asyncio.create_task(alert_cleanup_loop())

    logger.info("Master Node ready. 🚀")

    yield  # ← application runs here

    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("Master Node shutting down...")
    cleanup_task.cancel()
    auto_update_task.cancel()
    proposal_expiry.cancel()
    cleanup_alerts.cancel()
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
            return_exceptions=True
        )
    except Exception:
        pass
    await node_manager.stop()
    await close_db()
    logger.info("Shutdown complete.")
