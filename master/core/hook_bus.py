"""
Vigile — HookBus

Standalone hook dispatch bus for the Sprint 9 Plugin Engine.

A HookBus is a registry of named events ("hooks") to which plugins subscribe
callables. It provides four dispatch modes that mirror the legacy
PluginManager's semantics, but with no dependency on PluginManager:

  - call              : synchronous, serial,   returns list[Any] non-None
  - call_first        : synchronous, serial,   returns first non-None
  - async_call        : asynchronous, parallel returns list[Any] non-None
  - async_call_first  : asynchronous, parallel returns first non-None (via async_call)

Async hooks are skipped by the synchronous dispatchers (a warning is logged);
use async_call / async_call_first for coroutine functions.

Each async hook is run under a 30s timeout (asyncio.wait_for) and every hook
body is guarded against BaseException (SystemExit / KeyboardInterrupt are caught
and logged, never propagated out of the bus).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

#: Default per-hook timeout (seconds) for async dispatch.
_DEFAULT_ASYNC_TIMEOUT: float = 30.0


class HookBus:
    """
    A standalone hook registry with four dispatch modes.

    The registry maps a hook name to an ordered list of (plugin_name, fn)
    tuples preserving registration order. Dispatch iterates registrations
    in registration order.
    """

    def __init__(self) -> None:
        # hook_name -> [(plugin_name, callable)]
        self._hooks: dict[str, list[tuple[str, Callable]]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, hook_name: str, fn: Callable, *, plugin_name: str = "anonymous") -> None:
        """Subscribe ``fn`` to ``hook_name`` under ``plugin_name``."""
        self._hooks.setdefault(hook_name, []).append((plugin_name, fn))
        logger.debug("HookBus: '%s' registered hook '%s'", plugin_name, hook_name)

    def unregister(self, hook_name: str, plugin_name: str) -> int:
        """Remove every subscription from ``plugin_name`` on ``hook_name``.

        Returns the number of subscriptions removed.
        """
        if hook_name not in self._hooks:
            return 0
        before = len(self._hooks[hook_name])
        self._hooks[hook_name] = [
            (pn, fn) for pn, fn in self._hooks[hook_name] if pn != plugin_name
        ]
        removed = before - len(self._hooks[hook_name])
        if not self._hooks[hook_name]:
            del self._hooks[hook_name]
        return removed

    def has_hook(self, hook_name: str) -> bool:
        return hook_name in self._hooks and len(self._hooks[hook_name]) > 0

    def get_hooks(self) -> dict[str, list[str]]:
        """Return a {hook_name: [plugin_name, ...]} snapshot of the registry."""
        return {hook: [pn for pn, _ in impls] for hook, impls in self._hooks.items()}

    # ------------------------------------------------------------------
    # Synchronous dispatch
    # ------------------------------------------------------------------

    def call(self, hook_name: str, **kwargs: Any) -> list[Any]:
        """Invoke every sync subscription for ``hook_name`` in registration order.

        Async callables are skipped with a warning. Exceptions raised by a hook
        are caught and logged; dispatch continues to the next subscription.
        Returns the list of non-None results, in registration order.
        """
        results: list[Any] = []
        for plugin_name, fn in self._hooks.get(hook_name, []):
            if inspect.iscoroutinefunction(fn):
                logger.warning(
                    "HookBus: hook '%s' impl from '%s' is async — skipped in call(). "
                    "Use async_call() instead.",
                    hook_name,
                    plugin_name,
                )
                continue
            try:
                result = fn(**kwargs)
            except Exception:
                logger.exception(
                    "HookBus: hook '%s' impl from '%s' raised an exception",
                    hook_name,
                    plugin_name,
                )
                continue
            if result is not None:
                results.append(result)
        return results

    def call_first(self, hook_name: str, **kwargs: Any) -> Any | None:
        """Like :meth:`call` but stops at the first non-None result."""
        for plugin_name, fn in self._hooks.get(hook_name, []):
            if inspect.iscoroutinefunction(fn):
                logger.warning(
                    "HookBus: hook '%s' impl from '%s' is async — skipped in call_first(). "
                    "Use async_call_first() instead.",
                    hook_name,
                    plugin_name,
                )
                continue
            try:
                result = fn(**kwargs)
            except Exception:
                logger.exception(
                    "HookBus: hook '%s' impl from '%s' raised an exception",
                    hook_name,
                    plugin_name,
                )
                continue
            if result is not None:
                return result
        return None

    # ------------------------------------------------------------------
    # Asynchronous dispatch
    # ------------------------------------------------------------------

    async def _run_async_hook(
        self, plugin_name: str, fn: Callable, hook_name: str, **kwargs: Any
    ) -> Any:
        """Run a single hook body, awaiting if async or offloading to a thread.

        Catches BaseException (so SystemExit / KeyboardInterrupt never escape
        the bus). Returns the hook result, or the caught exception object so
        the caller (gather with return_exceptions=True) can filter it out.
        """
        try:
            if inspect.iscoroutinefunction(fn):
                return await fn(**kwargs)
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: fn(**kwargs))
        except BaseException as exc:  # noqa: BLE001 — intentional, see docstring
            logger.exception(
                "HookBus: async hook '%s' impl from '%s' raised: %s",
                hook_name,
                plugin_name,
                exc,
            )
            return exc

    async def async_call(self, hook_name: str, **kwargs: Any) -> list[Any]:
        """Invoke every subscription for ``hook_name`` concurrently.

        Async hooks are awaited; sync hooks are run in the default executor.
        Each hook is enveloped in a 30s timeout via ``asyncio.wait_for`` and a
        ``BaseException`` guard. Hooks that time out or raise are dropped from
        the returned list (their exception/timeout is logged). Returns the
        list of non-None successful results.
        """
        impls = self._hooks.get(hook_name, [])
        if not impls:
            return []

        # Wrap each hook body in wait_for(timeout=30). _run_async_hook itself
        # catches BaseException and returns the exception object, so the only
        # thing wait_for surfaces beyond a normal return is asyncio.TimeoutError
        # (raised by wait_for when the inner task exceeds the timeout).
        tasks: list[asyncio.Future] = []
        for plugin_name, fn in impls:
            inner = self._run_async_hook(plugin_name, fn, hook_name, **kwargs)
            tasks.append(asyncio.ensure_future(asyncio.wait_for(inner, timeout=_DEFAULT_ASYNC_TIMEOUT)))

        results_raw = await asyncio.gather(*tasks, return_exceptions=True)
        results: list[Any] = []
        for i, res in enumerate(results_raw):
            if isinstance(res, BaseException):
                # Either a TimeoutError from wait_for, or an exception returned
                # by _run_async_hook (already logged there). Log timeouts here
                # so they are visible; _run_async_hook already logged others.
                if isinstance(res, asyncio.TimeoutError):
                    logger.error(
                        "HookBus: async hook '%s' task %d timed out after %.1fs",
                        hook_name,
                        i,
                        _DEFAULT_ASYNC_TIMEOUT,
                    )
                continue
            if res is not None:
                results.append(res)
        return results

    async def async_call_first(self, hook_name: str, **kwargs: Any) -> Any | None:
        """Async first-non-None: delegates to :meth:`async_call`."""
        results = await self.async_call(hook_name, **kwargs)
        return results[0] if results else None
