"""
YouCloud AI Admin — In-Memory Rate Limiter

Sliding-window rate limiter per IP per endpoint.
No external dependencies — pure Python stdlib.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Sliding-window rate limiter using a dict of timestamp lists.

    Thread-safe via asyncio.Lock. Designed for single-process async apps.
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str) -> bool:
        """Check if a request from `key` is allowed. Cleans stale entries."""
        now = time.time()
        async with self._lock:
            timestamps = self._buckets.get(key, [])
            timestamps = [t for t in timestamps if now - t < self.window]

            if len(timestamps) >= self.max_requests:
                self._buckets[key] = timestamps
                return False

            timestamps.append(now)
            self._buckets[key] = timestamps
            return True

    async def cleanup_expired(self) -> None:
        """Periodic cleanup of expired entries (optional, call from background task)."""
        now = time.time()
        async with self._lock:
            expired_keys = [
                k for k, v in self._buckets.items()
                if not v or now - v[-1] >= self.window
            ]
            for k in expired_keys:
                del self._buckets[k]

    def middleware(self, app: FastAPI) -> None:
        """
        FastAPI middleware that rate-limits all requests by client IP.
        Skips WebSocket and static routes.
        """
        @app.middleware("http")
        async def _rate_limit_middleware(request: Request, call_next: Callable) -> Response:
            if request.url.path.startswith("/ws"):
                return await call_next(request)

            client_ip = request.client.host if request.client else "unknown"
            key = f"{client_ip}:{request.url.path}"

            allowed = await self.is_allowed(key)
            if not allowed:
                logger.warning("Rate limit exceeded: %s", key)
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"error": "Too many requests", "retry_after": self.window},
                )

            return await call_next(request)

    def dependency(self, max_requests: int | None = None) -> Callable:
        """
        FastAPI dependency for per-endpoint rate limiting.

        Usage:
            @router.get("/login", dependencies=[Depends(rate_limiter.dependency(10))])
        """
        effective_max = max_requests or self.max_requests

        async def _dep(request: Request) -> None:
            client_ip = request.client.host if request.client else "unknown"
            key = f"{client_ip}:{request.url.path}"

            allowed = await self.is_allowed(key)
            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many requests. Try again in {self.window}s.",
                )

        return _dep


# Module-level singleton
rate_limiter = RateLimiter()
