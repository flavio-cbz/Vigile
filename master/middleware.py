from __future__ import annotations

"""
Middleware management for Vigile Master Node.

This module contains the middleware functions and related logic.
"""

import logging

from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from master.config import settings

logger = logging.getLogger(__name__)


def setup_cors_middleware(app):
    """
    Configure CORS middleware for the FastAPI application.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def setup_cors_echo_origin_middleware(app):
    """
    Configure CORS echo origin middleware for wildcard origins.
    
    When allow_origins is ["*"], Starlette's CORSMiddleware sends
    "Access-Control-Allow-Origin: *" which is incompatible with
    "Access-Control-Allow-Credentials: true" per spec (browsers reject it).
    
    We patch this by echoing the request's Origin header when "*" is used.
    """
    if "*" in settings.cors_origins:
        logger.warning(
            "CORS_ORIGINS contains '*': dynamically echoing Origin header "
            "to work around wildcard + credentials incompatibility. "
            "Set CORS_ORIGINS to specific origins for production."
        )

        @app.middleware("http")
        async def _cors_echo_origin(request, call_next):
            response = await call_next(request)
            origin = request.headers.get("origin")
            if origin:
                response.headers["Access-Control-Allow-Origin"] = origin
            return response


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
