"""Vigile — ASGI Logging Middleware (Master / Python).

Request/response correlation with timing, plus WebSocket lifecycle logging.
"""

from __future__ import annotations

import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from master.logging_config import get_logger

logger = get_logger("middleware")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID", "")
        if not correlation_id:
            correlation_id = uuid.uuid4().hex[:16]

        start = time.monotonic()
        client_addr = request.client.host if request.client else "unknown"
        http_method = request.method
        http_path = request.url.path

        logger.trace(
            "Request received", extra={
                "correlation_id": correlation_id,
                "http_method": http_method, "http_path": http_path,
                "query": request.url.query, "client_addr": client_addr,
            },
        )
        try:
            response = await call_next(request)
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            logger.info("Response sent", extra={
                "correlation_id": correlation_id, "http_method": http_method,
                "http_path": http_path, "http_status": response.status_code,
                "duration_ms": duration_ms, "client_addr": client_addr,
            })
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        except Exception as exc:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            logger.error("Request failed with exception", extra={
                "correlation_id": correlation_id, "http_method": http_method,
                "http_path": http_path, "duration_ms": duration_ms,
                "client_addr": client_addr,
            }, exc_info=True)
            raise


class WebSocketLoggingMiddleware:
    """ASGI middleware that logs WebSocket lifecycle events with correlation IDs."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "websocket":
            await self.app(scope, receive, send)
            return

        correlation_id = scope.get("query_string", b"").decode()
        client_addr = scope.get("client", ("unknown", 0))[0] if scope.get("client") else "unknown"
        ws_path = scope.get("path", "")

        logger.trace(
            "WebSocket connection opened",
            extra={"correlation_id": correlation_id, "path": ws_path, "client_addr": client_addr},
        )

        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            logger.error(
                "WebSocket error",
                extra={"correlation_id": correlation_id, "path": ws_path, "client_addr": client_addr},
                exc_info=True,
            )
            raise
        finally:
            logger.info(
                "WebSocket connection closed",
                extra={"correlation_id": correlation_id, "path": ws_path, "client_addr": client_addr},
            )
