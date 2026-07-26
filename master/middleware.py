from __future__ import annotations

"""
Middleware management for Vigile Master Node.

This module contains the middleware functions and related logic.
"""

import logging

from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import MutableHeaders
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from master.config import settings

logger = logging.getLogger(__name__)


class CORSEchoOriginMiddleware:
    """ASGI middleware that echoes Origin as Access-Control-Allow-Origin.

    Replaces Starlette's CORSMiddleware when ``allow_origins=["*"]``.
    Echoing the specific origin instead of wildcard ``*`` works around the
    CORS spec incompatibility between ``Access-Control-Allow-Origin: *``
    and ``Access-Control-Allow-Credentials: true``, which browsers reject.
    """

    __slots__ = ("app",)

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Read Origin from request headers (lowercased in ASGI scope)
        origin = next(
            (v.decode("latin-1") for n, v in scope.get("headers", []) if n == b"origin"),
            None,
        )
        if not origin:
            await self.app(scope, receive, send)
            return

        # Handle CORS preflight
        if scope["method"] == "OPTIONS":
            headers = {
                b"access-control-allow-origin": origin.encode("latin-1"),
                b"access-control-allow-credentials": b"true",
                b"access-control-allow-methods": b"*",
                b"access-control-allow-headers": b"*",
                b"vary": b"Origin",
            }
            # Mirror the request's access-control-request-headers
            for n, v in scope.get("headers", []):
                if n == b"access-control-request-headers":
                    headers[b"access-control-allow-headers"] = v
                    break

            async def preflight_send(message: Message) -> None:
                if message["type"] == "http.response.start":
                    existing = dict(message.get("headers", []))
                    existing.update(headers)
                    message["headers"] = list(existing.items())
                await send(message)

            await self.app(scope, receive, preflight_send)
            return

        # Non-preflight: patch send to add ACAO + ACC after inner middleware
        async def patched_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                h = dict(message.get("headers", []))
                h[b"access-control-allow-origin"] = origin.encode("latin-1")
                h[b"access-control-allow-credentials"] = b"true"
                h[b"vary"] = b"Origin"
                message["headers"] = list(h.items())
                logger.debug("CORSEcho patch: ACAO=%s ACC=%s", h.get(b"access-control-allow-origin"), h.get(b"access-control-allow-credentials"))
            await send(message)

        await self.app(scope, receive, patched_send)


def setup_cors_middleware(app):
    """Configure CORS middleware.

    When ``allow_origins`` contains ``*``, registers ``CORSEchoOriginMiddleware``
    instead of Starlette's ``CORSMiddleware`` because the latter cannot combine
    wildcard origin with ``allow_credentials=True`` (per CORS spec).
    """
    if "*" in settings.cors_origins:
        logger.warning(
            "CORS_ORIGINS contains '*': using CORSEchoOriginMiddleware "
            "to work around wildcard + credentials incompatibility. "
            "Set CORS_ORIGINS to specific origins for production."
        )
        app.add_middleware(CORSEchoOriginMiddleware)
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )


def setup_cors_echo_origin_middleware(app):
    """No-op: CORS echo is handled inside ``setup_cors_middleware``."""
    pass


def setup_session_middleware(app):
    """
    Configure session middleware for the FastAPI application.
    """
    app.add_middleware(SessionMiddleware, secret_key=settings.server_secret_key)
    logger.info("SessionMiddleware initialized.")


def setup_https_enforcement_middleware(app):
    """
    Configure HTTPS enforcement middleware for the FastAPI application.
    
    Enforces HTTPS when behind a reverse proxy — checks X-Forwarded-Proto.
    """
    if settings.enforce_https:

        @app.middleware("http")
        async def _enforce_https(request, call_next):
            if request.url.path.startswith("/ws"):
                return await call_next(request)
            forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
            if forwarded_proto and forwarded_proto != "https":
                from fastapi.responses import JSONResponse
                from fastapi import status

                return JSONResponse(
                    status_code=status.HTTP_426_UPGRADE_REQUIRED,
                    content={"error": "HTTPS required", "message": "Use https:// instead of http://"},
                )
            return await call_next(request)

        logger.warning("HTTPS enforcement enabled — non-HTTPS requests will be rejected.")


def setup_rate_limiter(app):
    """
    Configure rate limiter middleware for the FastAPI application.
    """
    from master.core.rate_limiter import rate_limiter

    rate_limiter.max_requests = settings.rate_limit_max_requests
    rate_limiter.window = settings.rate_limit_window_seconds
    rate_limiter.middleware(app)
    logger.info(
        "Rate limiter active: %d req/%ds per IP per route",
        rate_limiter.max_requests,
        rate_limiter.window,
    )
