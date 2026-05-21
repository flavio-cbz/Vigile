"""
Vigile — In-Memory Rate Limiter

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


class LoopBoundLock:
    """
    A helper lock that delegates to an asyncio.Lock bound to the current event loop.
    Prevents loop mismatch / closed loop errors in tests.
    """
    def __init__(self) -> None:
        self._locks: dict[Any, asyncio.Lock] = {}

    def _get_lock(self) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.Lock()
        # Prune closed event loops to prevent memory leaks
        self._locks = {lp: lk for lp, lk in self._locks.items() if not lp.is_closed()}
        if loop not in self._locks:
            self._locks[loop] = asyncio.Lock()
        return self._locks[loop]

    async def __aenter__(self) -> Any:
        return await self._get_lock().__aenter__()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        return await self._get_lock().__aexit__(exc_type, exc_val, exc_tb)


class RateLimiter:
    """
    Sliding-window rate limiter using a dict of timestamp lists.

    Thread-safe via asyncio.Lock. Designed for single-process async apps.
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: dict[str, list[float]] = {}
        self._lock = LoopBoundLock()

    async def is_allowed(self, key: str, max_requests: int | None = None) -> bool:
        """Check if a request from `key` is allowed. Cleans stale entries."""
        now = time.time()
        limit = max_requests if max_requests is not None else self.max_requests
        async with self._lock:
            timestamps = self._buckets.get(key, [])
            timestamps = [t for t in timestamps if now - t < self.window]

            if len(timestamps) >= limit:
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

            allowed = await self.is_allowed(key, max_requests=effective_max)
            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many requests. Try again in {self.window}s.",
                )

        return _dep


    def start_cleanup_task(self, app: FastAPI, interval: int = 300) -> asyncio.Task:
        """Start a background task that periodically cleans up expired buckets."""
        async def _cleanup_loop() -> None:
            while True:
                try:
                    await asyncio.sleep(interval)
                    await self.cleanup_expired()
                    logger.debug("Rate limiter cleanup: expired buckets removed.")
                except asyncio.CancelledError:
                    break
                except Exception:
                    logger.exception("Rate limiter cleanup error (will retry)")
        task = asyncio.create_task(_cleanup_loop(), name="rate_limiter_cleanup")
        logger.info("Rate limiter cleanup task started (interval=%ds).", interval)
        return task


# Module-level singleton
rate_limiter = RateLimiter()
