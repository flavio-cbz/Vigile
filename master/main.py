"""
Vigile — Master Node Entry Point

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

import logging
import sys
import time
from datetime import datetime
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, Request, Response, WebSocket, HTTPException
from fastapi import status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from master.config import settings
from master.db.database import close_db, init_db
from master.db.migrations import run_migrations
from master.core.node_manager import node_manager
from master.core.plugin_manager import plugin_manager
from master.core.audit import verify_chain
from master.core.rate_limiter import rate_limiter
from master.core.security_manager import init_security, load_or_generate_master_key
from master.api.auth import router as auth_router
from master.api.nodes import router as nodes_router
from master.api.services import router as services_router
from master.api.chat import router as chat_router
from master.api.frontend import router as frontend_router
from master.api.audit import router as audit_router
from master.api.deps import require_role
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
    logger.info("=" * 60)
    logger.info("Vigile — Master Node starting up")
    logger.info("  Master URL : %s", settings.master_url)
    logger.info("  Database   : %s", settings.database_path)
    logger.info("  Debug mode : %s", settings.debug)
    logger.info("=" * 60)

    if settings.master_url.startswith("http://"):
        logger.warning(
            "⚠️  Master URL uses HTTP — traffic is NOT encrypted. "
            "Use HTTPS/WSS in production!"
        )

    # 1. Init DB
    db = await init_db(settings.database_path)
    logger.info("Database connection established.")

    # 2. Migrations
    await run_migrations(db)

    # 3. Initialize Jinja2 templates and static files
    from jinja2 import Environment, FileSystemLoader
    from starlette.templating import _TemplateResponse
    jinja_env = Environment(
        loader=FileSystemLoader("master/templates"),
        autoescape=True,
        cache_size=0,
    )
    jinja_env.globals["now"] = datetime.utcnow
    class _Templates:
        def __init__(self, env):
            self.env = env
        def TemplateResponse(self, name, context, status_code=200, headers=None):
            template = self.env.get_template(name)
            return _TemplateResponse(template, context, status_code=status_code, headers=headers)
    app.state.templates = _Templates(jinja_env)
    logger.info("Jinja2Templates initialized.")

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
    logger.info("SecurityManager initialized.")

    # 5. Load plugins
    loaded = plugin_manager.load_plugins_from_dir(settings.plugins_dir)
    logger.info("Plugins loaded: %s", loaded or "none")

    # 6. Node Manager
    await node_manager.start(
        heartbeat_interval=settings.heartbeat_interval,
        lost_threshold=settings.heartbeat_lost_threshold,
        stale_threshold=settings.heartbeat_stale_threshold,
    )

    app.state.startup_time = time.time()
    app.state.master_url = settings.master_url
    app.state.trusted_proxies = settings.trusted_proxies
    
    # 7. Start Rate Limiter Cleanup Task
    import asyncio
    async def _rate_limiter_cleanup_task():
        try:
            while True:
                await asyncio.sleep(60)
                rate_limiter.cleanup_expired()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Error in rate limiter cleanup task: %s", e)

    cleanup_task = asyncio.create_task(_rate_limiter_cleanup_task())
    logger.info("Rate limiter cleanup task started.")
    
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
        "Fleet Manager for servers and homelabs. "
        "Zero-Trust. Zero SSH. Human-in-the-Loop AI."
    ),
    version="0.2.0-sprint2",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    headers = getattr(exc, "headers", None)
    if isinstance(exc.detail, dict):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
            headers=headers
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers
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
logger.info("Rate limiter active: %d req/%ds per IP per route",
            rate_limiter.max_requests, rate_limiter.window)

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
app.include_router(services_router)
app.include_router(chat_router)
app.include_router(audit_router)

# ---------------------------------------------------------------------------
# Static Files
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="master/static"), name="static")

# ---------------------------------------------------------------------------
# Frontend Routes (SSR + HTMX)
# ---------------------------------------------------------------------------

app.include_router(frontend_router)

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
    return JSONResponse({
        "status": "ok",
        "version": "0.2.0-sprint2",
        "uptime_seconds": round(uptime, 1),
        "connected_nodes": len(node_manager.connected_node_ids()),
    })


@app.get("/api/admin/audit-verify", tags=["admin"], summary="Verify audit log integrity")
async def verify_audit_chain(
    claims=Depends(require_role("admin")),
) -> JSONResponse:
    """
    Walk the entire audit log and verify the SHA256 hash chain.
    Returns a report indicating whether the chain is intact.
    Admin only.
    """
    from master.db.database import get_db_conn

    db = get_db_conn()
    report = await verify_chain(db)
    status_code = 200 if report["valid"] else 409
    return JSONResponse(report, status_code=status_code)


@app.get("/api/admin/nodes/connections", tags=["admin"], summary="List active WebSocket connections")
async def list_active_connections(
    claims=Depends(require_role("admin")),
) -> JSONResponse:
    """Debug endpoint: show all currently connected Worker nodes."""
    return JSONResponse({
        "connected_nodes": node_manager.connected_node_ids(),
        "count": len(node_manager.connected_node_ids()),
    })


@app.get("/api/admin/plugins", tags=["admin"], summary="List loaded plugins and hooks")
async def list_plugins(
    claims=Depends(require_role("admin")),
) -> JSONResponse:
    """Debug endpoint: show the plugin registry."""
    return JSONResponse({
        "loaded_plugins": plugin_manager.loaded_plugins,
        "hooks": plugin_manager.get_hooks(),
    })
