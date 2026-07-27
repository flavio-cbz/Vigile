from __future__ import annotations

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
import json
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
from master.api.plugins import router as plugins_router
from master.api.metrics import render_prometheus
from master.api.nodes import router as nodes_router
from master.api.nodes_events import router as nodes_events_router
from master.api.services import router as services_router
from master.api.worker_binary import router as worker_binary_router
from master.config import settings
from master.logging_config import setup_logging
from master.logging_config import get_logger
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from master.api.admin import router as admin_router
from master.api.audit import router as audit_router
from master.api.auth import router as auth_router
from master.api.automations import router as automations_router
from master.api.chat import router as chat_router
from master.api.demo import router as demo_router
from master.api.investigations import router as investigations_router
from master.api.plugins import router as plugins_router
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
from master.core.plugin_engine import PluginEngine, PageRegistry
from master.core.scheduler import Scheduler
from master.core.proposal_autoexpire import auto_expire_proposals
from master.core.route_registrar import RouteRegistrar
from master.core.db_auto import DBAuto
from master.core.rate_limiter import rate_limiter
from master.core.security_manager import init_security, load_or_generate_master_key
from master.db.database import close_db, init_db, transaction
from master.db.migrations import run_migrations
from master.ws.worker_handler import worker_join_handler
from master.lifespan import lifespan
from master.auto_update import auto_update_workers_task
from master.proposal_expiry import proposal_expiry_task
from master.middleware import (
    setup_cors_middleware,
    setup_cors_echo_origin_middleware,
    setup_session_middleware,
    setup_https_enforcement_middleware,
    setup_rate_limiter,
)
from master.endpoints import health_check, metrics, spa_fallback_exception_handler

# ── Structured verbose logging ──
setup_logging(level=logging.DEBUG if settings.debug else logging.INFO, output_format="json")
logger = get_logger("main")


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

setup_cors_middleware(app)
setup_cors_echo_origin_middleware(app)
setup_session_middleware(app)
setup_https_enforcement_middleware(app)
setup_rate_limiter(app)

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
app.include_router(plugins_router)

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
