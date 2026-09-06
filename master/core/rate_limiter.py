from __future__ import annotations

"""
Vigile — In-Memory Rate Limiter

Sliding-window rate limiter per IP per endpoint.
No external dependencies — pure Python stdlib.

S5 (J3a-T19): per-plugin, per-user budget limiter with two independent
sliding windows per plugin — READS vs MUTATIONS (plan faille 8). Composite
key ``plugin:{plugin_id}:{user_id}:{call_type}``, enforced as a FastAPI
dependency carrying the authenticated user. Budget comes from the plugin
manifest with an admin override in the plugin config; a cancelled attempt
releases its slot immediately via a token, a timeout consumes it until the
window elapses.
"""

import asyncio
import inspect
import ipaddress
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Awaitable

from master.core.enums import StrEnum

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from master.core.lock import LoopBoundLock

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Sliding-window rate limiter using a dict of timestamp deques.

    Thread-safe via asyncio.Lock. Designed for single-process async apps.
    """

    def __init__(
        self,
        max_requests: int = 60,
        window_seconds: int = 60,
        trusted_proxies: list[str] | None = None,
    ) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: dict[str, deque[float]] = {}
        self._lock = LoopBoundLock()
        self.trusted_proxies = trusted_proxies or []

    def _is_trusted_proxy(self, client_ip: str) -> bool:
        if not self.trusted_proxies:
            return False
        try:
            peer = ipaddress.ip_address(client_ip)
        except ValueError:
            return False
        for proxy in self.trusted_proxies:
            try:
                if "/" in proxy:
                    if peer in ipaddress.ip_network(proxy, strict=False):
                        return True
                elif peer == ipaddress.ip_address(proxy):
                    return True
            except ValueError:
                logger.warning("Ignoring invalid TRUSTED_PROXIES entry: %s", proxy)
        return False

    def client_ip(self, request: Request) -> str:
        """Return the rate-limit client IP, honoring XFF only from trusted proxies."""
        direct_ip = request.client.host if request.client else "unknown"
        if not self._is_trusted_proxy(direct_ip):
            return direct_ip

        forwarded_for = request.headers.get("x-forwarded-for", "")
        first_hop = forwarded_for.split(",", 1)[0].strip()
        if not first_hop:
            return direct_ip
        try:
            ipaddress.ip_address(first_hop)
        except ValueError:
            logger.warning("Ignoring invalid X-Forwarded-For value: %s", forwarded_for)
            return direct_ip
        return first_hop

    async def is_allowed(self, key: str, max_requests: int | None = None) -> bool:
        """Check if a request from `key` is allowed. Cleans stale entries in O(1)."""
        now = time.time()
        limit = max_requests if max_requests is not None else self.max_requests
        cutoff = now - self.window
        async with self._lock:
            q = self._buckets.get(key)
            if q is None:
                q = deque()
                self._buckets[key] = q

            while q and q[0] <= cutoff:
                q.popleft()

            if len(q) >= limit:
                return False

            q.append(now)
            return True

    async def cleanup_expired(self) -> None:
        """Periodic cleanup of expired entries (optional, call from background task)."""
        now = time.time()
        cutoff = now - self.window
        async with self._lock:
            expired_keys = [
                k for k, q in self._buckets.items() if not q or q[-1] <= cutoff
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

            client_ip = self.client_ip(request)
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
            client_ip = self.client_ip(request)
            key = f"dep:{client_ip}:{request.url.path}"

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


# ---------------------------------------------------------------------------
# S5 — Per-plugin, per-user budget limiter (J3a-T19)
# ---------------------------------------------------------------------------
# Two independent sliding windows per plugin per user: READS vs MUTATIONS
# (plan faille 8). Composite key `plugin:{plugin_id}:{user_id}:{call_type}`.
# Budget resolution precedence: defaults → manifest → admin override (config).

PLUGIN_BUDGET_WINDOW_SECONDS = 60
PLUGIN_DEFAULT_READS_PER_MINUTE = 60
PLUGIN_DEFAULT_MUTATIONS_PER_MINUTE = 10
PLUGIN_RATE_LIMITS_CONFIG_KEY = "rate_limits"


class PluginCallType(StrEnum):
    READS = "reads"
    MUTATIONS = "mutations"


@dataclass(frozen=True)
class PluginBudget:
    reads_per_minute: int = PLUGIN_DEFAULT_READS_PER_MINUTE
    mutations_per_minute: int = PLUGIN_DEFAULT_MUTATIONS_PER_MINUTE

    def limit_for(self, call_type: PluginCallType) -> int:
        if call_type is PluginCallType.READS:
            return self.reads_per_minute
        return self.mutations_per_minute


class PluginRateLimitToken:
    """Handle for a charged budget slot.

    ``release()`` frees exactly this slot immediately (cancelled attempt).
    Dropping the token without release consumes the slot until the window
    elapses (timeout path). Release is idempotent.
    """

    def __init__(
        self,
        limiter: PluginRateLimiter,
        bucket_key: str,
        seq: int,
        timestamp: float,
    ) -> None:
        self._limiter = limiter
        self._bucket_key = bucket_key
        self._seq = seq
        self.timestamp = timestamp
        self._released = False

    async def release(self) -> None:
        await self._limiter._release(self)


class PluginRateLimiter:
    """
    Sliding-window budget limiter keyed by plugin + user + call type.

    Buckets store ``(timestamp, seq)`` pairs so a specific acquisition can
    be released on cancellation without disturbing the other slots.
    """

    def __init__(self, window_seconds: int = PLUGIN_BUDGET_WINDOW_SECONDS) -> None:
        self.window = window_seconds
        self._buckets: dict[str, list[tuple[float, int]]] = {}
        self._lock = LoopBoundLock()
        self._seq = 0

    @staticmethod
    def _bucket_key(plugin_id: str, user_id: str, call_type: PluginCallType) -> str:
        return f"plugin:{plugin_id}:{user_id}:{call_type.value}"

    async def acquire(
        self,
        plugin_id: str,
        user_id: str,
        call_type: PluginCallType,
        budget: PluginBudget,
        now: float | None = None,
    ) -> PluginRateLimitToken | None:
        """Charge one unit against the given call-type budget.

        Returns a token on success, ``None`` when the budget is exhausted.
        The caller MUST ``release()`` the token when the attempt is cancelled
        (quota freed immediately); on timeout the token is simply dropped and
        the slot stays consumed until the window elapses.
        """
        now = time.time() if now is None else now
        key = self._bucket_key(plugin_id, user_id, call_type)
        limit = budget.limit_for(call_type)
        async with self._lock:
            entries = [(t, s) for (t, s) in self._buckets.get(key, []) if now - t < self.window]
            if len(entries) >= limit:
                self._buckets[key] = entries
                return None
            self._seq += 1
            seq = self._seq
            entries.append((now, seq))
            self._buckets[key] = entries
            return PluginRateLimitToken(self, key, seq, now)

    async def _release(self, token: PluginRateLimitToken) -> None:
        async with self._lock:
            if token._released:
                return
            entries = self._buckets.get(token._bucket_key, [])
            remaining = [(t, s) for (t, s) in entries if s != token._seq]
            if remaining:
                self._buckets[token._bucket_key] = remaining
            else:
                self._buckets.pop(token._bucket_key, None)
            token._released = True

    async def cleanup_expired(self) -> None:
        now = time.time()
        async with self._lock:
            expired_keys = [
                k
                for k, entries in self._buckets.items()
                if not entries or now - entries[-1][0] >= self.window
            ]
            for k in expired_keys:
                del self._buckets[k]

    def start_cleanup_task(self, app: FastAPI, interval: int = 300) -> asyncio.Task:
        """Background task that periodically cleans up expired buckets."""

        async def _cleanup_loop() -> None:
            while True:
                try:
                    await asyncio.sleep(interval)
                    await self.cleanup_expired()
                    logger.debug("Plugin rate limiter cleanup: expired buckets removed.")
                except asyncio.CancelledError:
                    break
                except Exception:
                    logger.exception("Plugin rate limiter cleanup error (will retry)")

        task = asyncio.create_task(_cleanup_loop(), name="plugin_rate_limiter_cleanup")
        logger.info("Plugin rate limiter cleanup task started (interval=%ds).", interval)
        return task


def _clamp_limit(value: object, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return max(0, value)


def resolve_plugin_budget(
    manifest_limits: dict[str, object] | None,
    config_override: dict[str, object] | None,
) -> PluginBudget:
    """Precedence: defaults → manifest → admin override (config wins).
    Invalid values fall back to the previous level; negative values clamp to
    0 (deny-all, fail closed)."""
    reads = PLUGIN_DEFAULT_READS_PER_MINUTE
    mutations = PLUGIN_DEFAULT_MUTATIONS_PER_MINUTE

    if isinstance(manifest_limits, dict):
        reads = _clamp_limit(manifest_limits.get("reads_per_minute"), reads)
        mutations = _clamp_limit(manifest_limits.get("mutations_per_minute"), mutations)

    if isinstance(config_override, dict):
        reads = _clamp_limit(config_override.get("reads_per_minute"), reads)
        mutations = _clamp_limit(config_override.get("mutations_per_minute"), mutations)

    return PluginBudget(reads_per_minute=reads, mutations_per_minute=mutations)


def plugin_budget_from_config(config_json: dict[str, Any] | None) -> PluginBudget | None:
    """Extract the admin override from the reserved ``rate_limits`` key of a
    plugin config (``plugins.config_json``); ``None`` when absent. API wiring
    composes this on top of the manifest/default budget (DI at edge — core
    never reads the DB itself)."""
    if not isinstance(config_json, dict):
        return None
    override = config_json.get(PLUGIN_RATE_LIMITS_CONFIG_KEY)
    if not isinstance(override, dict):
        return None
    return resolve_plugin_budget(None, override)


def default_user_provider(request: Request) -> str:
    """Per-user identity for the composite key: ``request.state.user_id`` when
    the auth layer set it, else the client IP (documented simplification,
    same rationale as the per-IP NOTE in ``api/rate_limits.py``)."""
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return str(user_id)
    return request.client.host if request.client else "unknown"


async def default_plugin_budget_provider(
    plugin_id: str, call_type: PluginCallType
) -> PluginBudget:
    """Default budget source: the plugin manifest (duck-typed ``rate_limits``
    field, added by the J3b manifest refinement). Fail-safe to defaults when
    the engine is unavailable or the field is absent."""
    manifest_limits: dict[str, object] | None = None
    try:
        from master.core.plugin_engine import plugin_engine as _engine

        manifest = _engine.get_manifest(plugin_id)
        if manifest is not None:
            manifest_limits = getattr(manifest, "rate_limits", None)
    except Exception as exc:
        logger.warning("Plugin budget provider: manifest unavailable for '%s': %s", plugin_id, exc)
    return resolve_plugin_budget(manifest_limits, None)


def require_plugin_budget(
    plugin_id: str,
    call_type: PluginCallType | str,
    *,
    budget: PluginBudget | None = None,
    user_provider: Callable[[Request], str] | None = None,
    budget_provider: Callable[
        [str, PluginCallType], PluginBudget | Awaitable[PluginBudget]
    ] | None = None,
    limiter: PluginRateLimiter | None = None,
) -> Callable[[Request], Awaitable[PluginRateLimitToken]]:
    """
    FastAPI dependency enforcing the S5 per-plugin, per-user budget.

    Usage (enforcement only):
        @router.get("/data", dependencies=[Depends(require_plugin_budget("plex", PluginCallType.READS))])

    Usage (release-on-cancel — the handler frees the quota on cancellation):
        async def handler(token: PluginRateLimitToken = Depends(require_plugin_budget("plex", PluginCallType.READS))):
            try:
                ...
            except asyncio.CancelledError:
                await token.release()
                raise

    ``budget`` short-circuits resolution; otherwise ``budget_provider`` is
    used, defaulting to the manifest-based provider. ``user_provider``
    defaults to :func:`default_user_provider`. Exhaustion raises 429 with a
    ``Retry-After`` header.
    """
    effective_limiter = limiter or plugin_rate_limiter
    normalized = PluginCallType(call_type)
    effective_user = user_provider or default_user_provider
    if budget is not None:
        effective_budget: Callable[
            [str, PluginCallType], PluginBudget | Awaitable[PluginBudget]
        ] = lambda _pid, _ct: budget
    else:
        effective_budget = budget_provider or default_plugin_budget_provider

    async def _dep(request: Request) -> PluginRateLimitToken:
        user_id = effective_user(request)
        resolved = effective_budget(plugin_id, normalized)
        if inspect.isawaitable(resolved):
            resolved = await resolved
        token = await effective_limiter.acquire(plugin_id, user_id, normalized, resolved)
        if token is None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Plugin '{plugin_id}' {normalized.value} budget exceeded "
                    f"for user '{user_id}'. Try again later."
                ),
                headers={"Retry-After": str(effective_limiter.window)},
            )
        return token

    return _dep


# Module-level singleton
plugin_rate_limiter = PluginRateLimiter()
