from __future__ import annotations

"""
Vigile — Circuit Breaker for Plugin Hook Dispatch

Protects the plugin engine from cascading failures: when a plugin's hook
fails N times consecutively, the circuit opens and subsequent calls are
rejected immediately (fail-fast) without invoking the plugin.  After a
timeout the circuit transitions to HALF_OPEN, allowing one probe call to
decide whether to close (success) or stay open (failure).

Thread-safe via LoopBoundLock (asyncio-lock per event loop).
"""

import asyncio
import time
from enum import Enum
from typing import Any, Callable

from master.core.lock import LoopBoundLock


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit is OPEN and the cooldown timeout has not elapsed."""


class CircuitBreaker:
    """Per-plugin circuit breaker guarding hook dispatch.

    States::

        CLOSED ──(threshold failures)──▶ OPEN
        OPEN   ──(timeout elapsed)─────▶ HALF_OPEN
        HALF_OPEN ──(success)──────────▶ CLOSED
        HALF_OPEN ──(failure)──────────▶ OPEN

    Args:
        name:  Plugin name (used in log / error messages).
        failure_threshold:  Consecutive failures before tripping (default 5).
        timeout:  Seconds in OPEN state before transitioning to HALF_OPEN (default 60).
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        timeout: float = 60.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout = timeout

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        self._lock = LoopBoundLock()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute *fn* through the circuit breaker.

        If the circuit is OPEN the call is rejected immediately (fail-fast).
        If the circuit is HALF_OPEN the call is allowed as a probe; a success
        closes the circuit, a failure re-opens it.

        Handles both coroutine and sync callables.  Sync callables are called
        directly (not in an executor) and may block the event loop briefly.
        """
        await self._check()

        try:
            if asyncio.iscoroutinefunction(fn):
                result = await fn(*args, **kwargs)
            else:
                result = fn(*args, **kwargs)
        except BaseException:
            await self.record_failure()
            raise

        await self.record_success()
        return result

    async def record_success(self) -> None:
        async with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
            self._failure_count = 0

    async def record_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN

    async def check(self) -> None:
        """Check & possibly transition circuit state without invoking a fn.

        Raises :class:`CircuitBreakerOpenError` if OPEN and the timeout has
        **not** elapsed yet.  If the timeout *has* elapsed the circuit
        transitions to HALF_OPEN and returns normally, signalling the caller
        that a probe call is now allowed.

        This is useful when the caller wants to run *fn* in an executor
        (e.g. for sync hooks) but still respect the CB.
        """
        await self._check()

    # ------------------------------------------------------------------
    # Reset (testing / manual recovery)
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Force the circuit back to CLOSED (testing or admin recovery)."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _check(self) -> None:
        """Lock-protected state check — raises if OPEN and not yet timed out."""
        async with self._lock:
            if self._state is CircuitState.OPEN:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self.timeout:
                    self._state = CircuitState.HALF_OPEN
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is OPEN "
                        f"({self._failure_count} failures, "
                        f"{self.timeout - elapsed:.1f}s remaining)"
                    )
