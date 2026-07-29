from __future__ import annotations

"""
Endpoint handlers for Vigile Master Node.

This module contains the endpoint handlers for the FastAPI application.
"""

import logging
import time
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from master.core.node_manager import node_manager
from master.api.metrics import render_prometheus

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_STATIC_DIR = _PROJECT_ROOT / "master" / "static"


async def health_check(request: Request) -> JSONResponse:
    """
    Basic health check endpoint.

    Returns uptime, connected node count, and version.
    """
    uptime = time.time() - getattr(request.app.state, "startup_time", time.time())
    return JSONResponse(
        {
            "status": "ok",
            "version": "0.7.0",
            "uptime_seconds": round(uptime, 1),
            "connected_nodes": len(node_manager.connected_node_ids()),
        }
    )


async def metrics(request: Request) -> PlainTextResponse:
    """
    Expose Prometheus-format metrics for scraping.

    Returns text/plain content compatible with the Prometheus exposition format.
    """
    connected_count = len(node_manager.connected_node_ids())
    startup_time = getattr(request.app.state, "startup_time", time.time())
    version = "0.7.0"
    body = await render_prometheus(connected_count, startup_time, version)
    return PlainTextResponse(content=body, media_type="text/plain; version=0.0.4")


async def spa_fallback_exception_handler(request: Request, exc: HTTPException) -> JSONResponse | FileResponse:
    """
    Exclude API/WebSocket endpoints; fall back to SPA index.html for client-side routing.
    """
    path = request.url.path.lstrip("/")

    if path.startswith("api/") or path.startswith("ws/") or path == "health":
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    index_path = _STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))

    return JSONResponse(status_code=404, content={"detail": "Not Found"})
