"""
Vigile — Single-Flight Pattern

Suppresses duplicate in-flight async work for the same key.
Concurrent callers sharing the same key await the single in-flight coroutine.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, TypeVar

from master.core.lock import LoopBoundLock

logger = logging.getLogger(__name__)

T = TypeVar("T")


class SingleFlight:
    """Ensures that only one execution of a function is in-flight for a given key."""

    def __init__(self) -> None:
        self._in_flight: dict[str, asyncio.Future[Any]] = {}
        self._lock = LoopBoundLock()

    async def run(self, key: str, fn: Callable[[], Awaitable[T]]) -> T:
        """Run `fn` for `key`. If already in flight, wait for existing execution.

        Returns the result of `fn` or raises any exception produced by `fn`.
        """
        loop = asyncio.get_running_loop()
        leader = False
        async with self._lock:
            if key in self._in_flight:
                fut = self._in_flight[key]
                # If future belongs to another/closed loop or is already done, discard it
                if fut.get_loop() is not loop or fut.done():
                    fut = loop.create_future()
                    self._in_flight[key] = fut
                    leader = True
            else:
                fut = loop.create_future()
                self._in_flight[key] = fut
                leader = True

        if leader:
            try:
                result = await fn()
                if not fut.done():
                    fut.set_result(result)
                return result
            except BaseException as exc:
                if not fut.done():
                    fut.set_exception(exc)
                raise
            finally:
                async with self._lock:
                    if self._in_flight.get(key) is fut:
                        self._in_flight.pop(key, None)
        else:
            return await fut
