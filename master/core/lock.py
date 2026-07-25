from __future__ import annotations

"""
Vigile — Loop-Bound Lock

Shared asyncio.Lock wrapper that binds to the current event loop,
preventing loop mismatch / closed loop errors across modules and tests.
"""

import asyncio
from typing import Any


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
