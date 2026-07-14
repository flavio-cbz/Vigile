"""
Vigile — Master Node Entry Point (reloaded)

FastAPI application with:
  - Async lifespan (DB init → plugin load → node manager start → shutdown)
  - REST routers: /api/auth, /api/nodes
  - WebSocket route: /ws/worker/join
  - CORS middleware
  - Structured logging
  - Health check endpoint

Run with:
    uvicorn master.main:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import logging
import os
import sys
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from master.api.admin import router as admin_router
from master.api.audit import router as audit_router
from master.api.auth import router as auth_router
from master.api.automations import router as automations_router
from master.api.chat import router as chat_router
from master.api.demo import router as demo_router
from master.api.investigations import router as investigations_router
from master.api.metrics import render_prometheus
from master.api.nodes import router as nodes_router
from master.api.nodes_events import router as nodes_events_router
from master.api.services import router as services_router
from master.api.worker_binary import router as worker_binary_router
from master.config import settings
from master.core.alert_engine import alert_engine
from master.core.investigation_manager import investigation_manager
from master.core.automation_engine import automation_engine
from master.core.enums import NodeState
from master.core.node_manager import node_manager
from master.core.plugin_manager import plugin_manager, plugin_engine as _plugin_engine_ref
from master.core.plugin_engine import PluginEngine
from master.core.hook_bus import HookBus
from master.core.scheduler import Scheduler
from master.core.proposal_autoexpire import auto_expire_proposals
from master.core.route_registrar import RouteRegistrar
from master.core.db_auto import DBAuto
from master.core.scanner import Scanner
from master.core.rate_limiter import rate_limiter
from master.core.security_manager import init_security, load_or_generate_master_key
from master.db.database import close_db, init_db, transaction
from master.db.migrations import run_migrations
from master.ws.worker_handler import worker_join_handler

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)

# Silence noisy third-party loggers
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("passlib").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Worker Auto-Update Task
# ---------------------------------------------------------------------------


async def auto_update_workers_task(db, nm, settings_obj) -> None:
    """
    Background loop that checks for worker updates and dispatches them if AUTO_UPDATE_WORKERS is enabled.
    """
    logger.info("Auto-update workers task started.")
    # Wait a bit on startup to let things settle down
    await asyncio.sleep(30.0)

    while True:
        try:
            if settings_obj.offline_mode:
                logger.info("Offline mode: skipping auto-update check.")
                await asyncio.sleep(3600.0)
                continue

            if settings_obj.auto_update_workers:
                logger.info("Auto-update: Checking connected nodes for updates...")
                from master.api.worker_binary import _fetch_manifest

                try:
                    manifest = await _fetch_manifest(settings_obj)
                except Exception as exc:
                    logger.error("Auto-update: Failed to fetch manifest: %s", exc)
                    manifest = None

                if manifest:
                    latest_version = manifest.get("version")
                    if latest_version:
                        logger.info(
                            "Auto-update: Latest available worker version: %s", latest_version
                        )

                        # Get all registered nodes (exclude revoked)
                        async with db.execute(
                            "SELECT id, name, version, state FROM nodes WHERE state != 'REVOKED'"
                        ) as cursor:
                            nodes = await cursor.fetchall()

                        for node in nodes:
                            node_id = node["id"]
                            # Check if node is online/connected
                            if await nm.is_connected(node_id):
                                current_version = node["version"]
                                # If version is empty (legacy) or doesn't match latest_version, trigger update
                                if not current_version or current_version != latest_version:
                                    logger.info(
                                        "Auto-update: Node %s (%s) has version %s (latest is %s). Dispatching update...",
                                        node_id,
                                        node["name"],
                                        current_version,
                                        latest_version,
                                    )
                                    try:
                                        # Run intent dispatch asynchronously in a separate task so it doesn't block the loop
                                        async def do_update(nid=node_id):
                                            try:
                                                from master.core.enums import WorkerAction

                                                await nm.send_intent(
                                                    nid,
                                                    {
                                                        "action": WorkerAction.UPDATE_WORKER,
                                                        "params": {},
                                                    },
                                                    timeout=30.0,
                                                )
                                                logger.info(
                                                    "Auto-update: Node %s successfully updated and restarted.",
                                                    nid,
                                                )
                                            except Exception as e:
                                                logger.error(
                                                    "Auto-update: Node %s update failed: %s", nid, e
                                                )

                                        asyncio.create_task(do_update())
                                    except Exception as exc:
                                        logger.error(
                                            "Auto-update: Failed to spawn update task for node %s: %s",
                                            node_id,
                                            exc,
                                        )
        except Exception as exc:
            logger.exception("Error in auto-update workers task: %s", exc)

        # Check every 1 hour (3600 seconds)
        await asyncio.sleep(3600.0)


async def proposal_expiry_task(db, nm, settings_obj) -> None:
    """
    Background loop that cancels stale PENDING proposals by TTL or
    resolved metric conditions.
    """
    logger.info("Proposal auto-expiry task started.")
    # Wait a bit on startup to let things settle and first metrics arrive
    await asyncio.sleep(60.0)

    while True:
        try:
            canceled = await auto_expire_proposals(db, nm)
            if canceled:
                logger.info("Proposal auto-expiry: canceled %d proposals.", canceled)
        except Exception as exc:
            logger.exception("Error in proposal expiry task: %s", exc)

        # Check every 60 seconds
        await asyncio.sleep(60.0)


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------


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
    import json

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
    hook_bus = HookBus()
    scheduler = Scheduler()
    route_registrar = RouteRegistrar(app)
    db_auto = DBAuto(db)
    scanner = Scanner(
        plugins_dir=settings.plugins_dir,
        db=db,
    )
    engine = PluginEngine(
        hook_bus=hook_bus,
        scheduler=scheduler,
        route_registrar=route_registrar,
        db_auto=db_auto,
        scanner=scanner,
        db=db,
    )
    scanner.set_lifecycle(engine.lifecycle)
    plugin_manager.set_engine(engine)
    import master.core.plugin_manager as _pm
    _pm.plugin_engine = engine
    await plugin_manager.initialize(db, sandbox=settings.plugin_sandbox)
    loaded = await plugin_manager.load_plugins_from_dir(settings.plugins_dir)
    logger.info("Plugins loaded: %s", loaded or "none")
    scan_result = await scanner.scan()
    if scan_result.installed:
        logger.info("Scanner installed new plugins: %s", scan_result.installed)
    if scan_result.orphans:
        logger.warning("Scanner found orphan plugins: %s", scan_result.orphans)

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
    plugin_manager.register(
        "on_status_report",
        automation_engine.evaluate_metric_trigger,
        plugin_name="automation_engine",
    )
    logger.info("Automation Engine initialized and state-change callback registered.")

    # 7b. Alert Engine (évaluation des seuils intégrés)
    await alert_engine.initialize(db)
    node_manager.register_state_change_callback(alert_engine.evaluate_node_state)
    plugin_manager.register(
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
        await asyncio.gather(cleanup_task, auto_update_task, proposal_expiry, cleanup_alerts, return_exceptions=True)
    except Exception:
        pass
    await node_manager.stop()
    await scheduler.shutdown()
    await close_db()
    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------


app = FastAPI(
    title="Vigile — Master Node",
    description=(
        "Fleet Manager for servers and homelabs. " "Zero-Trust. Zero SSH. Human-in-the-Loop AI."
    ),
    version="0.7.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    headers = getattr(exc, "headers", None)
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail, headers=headers)
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}, headers=headers
    )


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CORS wildcard + credentials compatibility fix.
# When allow_origins is ["*"], Starlette's CORSMiddleware sends
# "Access-Control-Allow-Origin: *" which is incompatible with
# "Access-Control-Allow-Credentials: true" per spec (browsers reject it).
# We patch this by echoing the request's Origin header when "*" is used.
if "*" in settings.cors_origins:
    logger.warning(
        "CORS_ORIGINS contains '*': dynamically echoing Origin header "
        "to work around wildcard + credentials incompatibility. "
        "Set CORS_ORIGINS to specific origins for production."
    )

    @app.middleware("http")
    async def _cors_echo_origin(request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        origin = request.headers.get("origin")
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
        return response


# Rate limiter (global middleware — excludes WebSocket)
rate_limiter.max_requests = settings.rate_limit_max_requests
rate_limiter.window = settings.rate_limit_window_seconds
rate_limiter.middleware(app)
logger.info(
    "Rate limiter active: %d req/%ds per IP per route",
    rate_limiter.max_requests,
    rate_limiter.window,
)

# Session middleware (for flash messages, CSRF, etc.)
app.add_middleware(SessionMiddleware, secret_key=settings.server_secret_key)
logger.info("SessionMiddleware initialized.")

# HTTPS enforcement middleware (behind reverse proxy — checks X-Forwarded-Proto)
if settings.enforce_https:

    @app.middleware("http")
    async def _enforce_https(request: Request, call_next: Callable) -> Response:
        if request.url.path.startswith("/ws"):
            return await call_next(request)
        forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
        if forwarded_proto and forwarded_proto != "https":
            return JSONResponse(
                status_code=status.HTTP_426_UPGRADE_REQUIRED,
                content={"error": "HTTPS required", "message": "Use https:// instead of http://"},
            )
        return await call_next(request)

    logger.warning("HTTPS enforcement enabled — non-HTTPS requests will be rejected.")

# ---------------------------------------------------------------------------
# REST Routers
# ---------------------------------------------------------------------------

app.include_router(auth_router)
app.include_router(nodes_router)
app.include_router(nodes_events_router)
app.include_router(services_router)
app.include_router(chat_router)
app.include_router(audit_router)
app.include_router(admin_router)
app.include_router(demo_router)
app.include_router(worker_binary_router)
app.include_router(automations_router)
app.include_router(investigations_router)

# ---------------------------------------------------------------------------
# WebSocket Routes
# ---------------------------------------------------------------------------


@app.websocket("/ws/worker/join")
async def ws_worker_join(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for Worker enrollment and operational communication.

    Protocol:
      Phase 1: Enrollment handshake (Ed25519 challenge/response)
      Phase 2: Operational (heartbeat + intent dispatch)
    """
    await worker_join_handler(websocket)


# ---------------------------------------------------------------------------
# System endpoints
# ---------------------------------------------------------------------------


@app.get("/health", tags=["system"], summary="Health check")
async def health_check() -> JSONResponse:
    """
    Basic health check endpoint.
    Returns uptime, connected node count, and version.
    """
    uptime = time.time() - getattr(app.state, "startup_time", time.time())
    return JSONResponse(
        {
            "status": "ok",
            "version": "0.7.0",
            "uptime_seconds": round(uptime, 1),
            "connected_nodes": len(node_manager.connected_node_ids()),
        }
    )


@app.get("/metrics", tags=["system"], summary="Prometheus metrics")
async def metrics() -> PlainTextResponse:
    """
    Expose Prometheus-format metrics for scraping.
    Returns text/plain content compatible with the Prometheus exposition format.
    """
    connected_count = len(node_manager.connected_node_ids())
    startup_time = getattr(app.state, "startup_time", time.time())
    version = "0.7.0"
    body = await render_prometheus(connected_count, startup_time, version)
    return PlainTextResponse(content=body, media_type="text/plain; version=0.0.4")


# ---------------------------------------------------------------------------
# Static Files (mounted last so API/WS/health routes take precedence)
# ---------------------------------------------------------------------------

os.makedirs("master/static", exist_ok=True)
app.mount("/", StaticFiles(directory="master/static", html=True), name="static")


@app.exception_handler(404)
async def spa_fallback_exception_handler(request: Request, exc: HTTPException) -> Response:
    """Exclude API/WebSocket endpoints; fall back to SPA index.html for client-side routing."""
    path = request.url.path.lstrip("/")

    if path.startswith("api/") or path.startswith("ws/") or path == "health":
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    index_path = Path("master/static/index.html")
    if index_path.exists():
        return FileResponse(index_path)

    return JSONResponse(status_code=404, content={"detail": "Not Found"})
