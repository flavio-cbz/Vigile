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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from master.api.admin import router as admin_router
from master.api.audit import router as audit_router
from master.api.auth import router as auth_router
from master.api.chat import router as chat_router
from master.api.demo import router as demo_router
from master.api.nodes import router as nodes_router
from master.api.nodes_events import router as nodes_events_router
from master.api.services import router as services_router
from master.api.worker_binary import router as worker_binary_router
from master.config import settings
from master.core.node_manager import node_manager
from master.core.plugin_manager import plugin_manager
from master.core.rate_limiter import rate_limiter
from master.core.security_manager import init_security, load_or_generate_master_key
from master.db.database import close_db, init_db
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
    override_path = Path(settings.database_path).parent / "settings_override.json"
    if override_path.exists():
        try:
            import json

            with override_path.open("r", encoding="utf-8") as f:
                overrides = json.load(f)
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
    db = await init_db(settings.database_path, timeout=settings.db_timeout)
    logger.info("Database connection established.")

    # 2. Migrations
    await run_migrations(db)

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
    # 4.5. Initialize PluginManager
    await plugin_manager.initialize(db)

    # 5. Load plugins
    loaded = plugin_manager.load_plugins_from_dir(settings.plugins_dir)
    logger.info("Plugins loaded: %s", loaded or "none")

    # 6. Node Manager
    await node_manager.start(
        heartbeat_interval=settings.heartbeat_interval,
        lost_threshold=settings.heartbeat_lost_threshold,
        stale_threshold=settings.heartbeat_stale_threshold,
        default_intent_max_age=settings.default_intent_max_age,
        cache_update_interval=settings.cache_update_interval,
    )

    app.state.startup_time = time.time()
    app.state.master_url = settings.master_url
    app.state.trusted_proxies = settings.trusted_proxies
    rate_limiter.trusted_proxies = settings.trusted_proxies

    # 7. Start Rate Limiter Cleanup Task
    cleanup_task = rate_limiter.start_cleanup_task(app)

    logger.info("Master Node ready. 🚀")

    yield  # ← application runs here

    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("Master Node shutting down...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    await node_manager.stop()
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
    version="0.5.0",
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

# ---------------------------------------------------------------------------
# Static Files
# ---------------------------------------------------------------------------

os.makedirs("master/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="master/static"), name="static")

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
            "version": "0.5.0",
            "uptime_seconds": round(uptime, 1),
            "connected_nodes": len(node_manager.connected_node_ids()),
        }
    )


@app.exception_handler(404)
async def spa_fallback_exception_handler(request: Request, exc: HTTPException) -> Response:
    """Serve static assets if they exist, otherwise fall back to SPA index.html."""
    path = request.url.path.lstrip("/")

    # 1. Exclude API and WebSocket endpoints
    if path.startswith("api/") or path.startswith("ws/"):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    # 2. Check if requested file exists in the SPA dist folder
    file_path = Path("frontend/dist") / path
    if file_path.is_file():
        return FileResponse(file_path)

    # 3. Fallback to index.html for client-side routing
    index_path = Path("frontend/dist/index.html")
    if index_path.exists():
        return FileResponse(index_path)

    return JSONResponse(status_code=404, content={"detail": "Not Found"})
