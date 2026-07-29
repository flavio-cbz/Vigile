"""
Vigile — HookBus

Standalone hook dispatch bus for the Sprint 9 Plugin Engine.

A HookBus is a registry of named events ("hooks") to which plugins subscribe
callables. It provides four dispatch modes that mirror the legacy
PluginManager's semantics, but with no dependency on PluginManager:

  - call              : synchronous, serial,   returns list[Any] non-None
  - call_first        : synchronous, serial,   returns first non-None
  - async_call        : asynchronous, parallel returns list[dict] structured results
  - async_call_first  : asynchronous, parallel returns first non-None result value

Async hooks are skipped by the synchronous dispatchers (a warning is logged);
use async_call / async_call_first for coroutine functions.

Each async hook is run under a 30s timeout (asyncio.wait_for) and every hook
body is guarded against BaseException (SystemExit / KeyboardInterrupt are caught
and logged, never propagated out of the bus).

Phase 7 additions:
  - HookName validation at registration time (warns on unknown hooks)
  - Per-plugin CircuitBreaker (5 consecutive failures → OPEN for 60s)
  - Structured result dicts from async_call
  - Outbox events for critical hooks (plugin.load, plugin.unload,
    node.connect, node.disconnect)
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from typing import Any

from master.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from master.core.enums import HookName

logger = logging.getLogger(__name__)

#: Default per-hook timeout (seconds) for async dispatch.
_DEFAULT_ASYNC_TIMEOUT: float = 30.0

#: Hooks whose dispatch is published to the transactional outbox.
#: Mapping: hook_name -> (event_type, aggregate_kwarg_key, aggregate_type)
_CRITICAL_HOOKS: dict[str, tuple[str, str, str]] = {
    "on_plugin_load": ("plugin.load", "plugin_id", "plugin"),
    "on_plugin_unload": ("plugin.unload", "plugin_id", "plugin"),
    "on_node_connect": ("node.connect", "node_id", "node"),
    "on_node_disconnect": ("node.disconnect", "node_id", "node"),
}


class HookBus:
    """
    A standalone hook registry with four dispatch modes.

    The registry maps a hook name to an ordered list of (plugin_name, fn)
    tuples preserving registration order. Dispatch iterates registrations
    in registration order.

    Each plugin gets its own :class:`CircuitBreaker` that trips after 5
    consecutive failures and stays open for 60s.
    """

    def __init__(self) -> None:
        # hook_name -> [(plugin_name, callable)]
        self._hooks: dict[str, list[tuple[str, Callable]]] = {}
        # plugin_name -> CircuitBreaker
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, hook_name: str, fn: Callable, *, plugin_name: str = "anonymous") -> None:
        """Subscribe ``fn`` to ``hook_name`` under ``plugin_name``.

        Validates ``hook_name`` against the :class:`HookName` enum — a
        warning is logged for unknown hook names so that typos are surfaced
        early without breaking compatibility.
        """
        self._validate_hook_name(hook_name, plugin_name)
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
    ) -> dict[str, Any]:
        """Run a single hook body with circuit-breaker protection.

        Returns a structured result dict::

            {"success": bool, "result": Any, "error": str | None, "plugin_name": str}

        Async hooks are awaited; sync hooks are offloaded to the default
        executor.  BaseException is caught so SystemExit / KeyboardInterrupt
        never escape the bus.
        """
        cb = self._get_circuit_breaker(plugin_name)

        try:
            if inspect.iscoroutinefunction(fn):
                # Async function — cb.call() handles state check & recording
                result = await cb.call(fn, **kwargs)
            else:
                # Sync function — check CB, run in executor, record outcome
                await cb.check()
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, lambda: fn(**kwargs))
                await cb.record_success()
        except CircuitBreakerOpenError:
            logger.warning(
                "HookBus: circuit breaker '%s' is OPEN for hook '%s' — skipping",
                plugin_name,
                hook_name,
            )
            return {
                "success": False,
                "result": None,
                "error": f"Circuit breaker '{plugin_name}' is OPEN",
                "plugin_name": plugin_name,
            }
        except BaseException as exc:
            logger.exception(
                "HookBus: async hook '%s' impl from '%s' raised: %s",
                hook_name,
                plugin_name,
                exc,
            )
            # cb.call already recorded failure for async fns; record for sync
            if not inspect.iscoroutinefunction(fn):
                await cb.record_failure()
            return {
                "success": False,
                "result": None,
                "error": str(exc),
                "plugin_name": plugin_name,
            }

        return {
            "success": True,
            "result": result,
            "error": None,
            "plugin_name": plugin_name,
        }

    async def async_call(self, hook_name: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Invoke every subscription for ``hook_name`` concurrently.

        Async hooks are awaited; sync hooks are run in the default executor.
        Each hook is enveloped in a 30s timeout via ``asyncio.wait_for`` and a
        ``BaseException`` guard.  Hooks that time out or raise are captured in
        the returned result dict rather than dropped silently.

        Returns a list of structured result dicts, one per subscription::

            [
                {"success": True,  "result": <value>, "error": None, "plugin_name": "p1"},
                {"success": False, "result": None,    "error": "...", "plugin_name": "p2"},
            ]

        Critical hooks (plugin.load, plugin.unload, node.connect,
        node.disconnect) additionally publish an outbox event.
        """
        impls = self._hooks.get(hook_name, [])
        if not impls:
            return []

        # Wrap each hook body in wait_for(timeout=30). _run_async_hook itself
        # catches BaseException and returns structured dicts, so the only thing
        # wait_for surfaces beyond a normal return is asyncio.TimeoutError.
        tasks: list[asyncio.Future] = []
        for plugin_name, fn in impls:
            inner = self._run_async_hook(plugin_name, fn, hook_name, **kwargs)
            tasks.append(
                asyncio.ensure_future(
                    asyncio.wait_for(inner, timeout=_DEFAULT_ASYNC_TIMEOUT)
                )
            )

        results_raw = await asyncio.gather(*tasks, return_exceptions=True)
        results: list[dict[str, Any]] = []
        for i, res in enumerate(results_raw):
            if isinstance(res, BaseException):
                # TimeoutError from wait_for — other exceptions are already
                # caught by _run_async_hook and returned as structured dicts.
                plugin_name = impls[i][0] if i < len(impls) else "unknown"
                logger.error(
                    "HookBus: async hook '%s' task %d (plugin '%s') timed out after %.1fs",
                    hook_name,
                    i,
                    plugin_name,
                    _DEFAULT_ASYNC_TIMEOUT,
                )
                results.append(
                    {
                        "success": False,
                        "result": None,
                        "error": f"Timeout after {_DEFAULT_ASYNC_TIMEOUT}s",
                        "plugin_name": plugin_name,
                    }
                )
                continue
            if isinstance(res, dict):
                results.append(res)

        # Outbox events for critical hooks
        if hook_name in _CRITICAL_HOOKS:
            await self._publish_outbox_event(hook_name, results, **kwargs)

        return results

    async def async_call_first(self, hook_name: str, **kwargs: Any) -> Any | None:
        """Async first-non-None: delegates to :meth:`async_call`.

        Returns the **result value** of the first successful subscription
        whose result is not None, or ``None`` if no hook returned a value.
        """
        results = await self.async_call(hook_name, **kwargs)
        for r in results:
            if r.get("success") and r.get("result") is not None:
                return r["result"]
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_hook_name(self, hook_name: str, plugin_name: str) -> None:
        """Warn if *hook_name* is not a known :class:`HookName` member.

        Uses a warning rather than a hard error so that forward-compatible
        hook names (e.g. from a newer plugin) don't crash the bus.
        """
        try:
            HookName(hook_name)
        except ValueError:
            logger.warning(
                "HookBus: '%s' registered unknown hook name '%s' — "
                "not in the HookName enum; if this is a new hook, "
                "add it to master/core/enums.py::HookName",
                plugin_name,
                hook_name,
            )

    def _get_circuit_breaker(self, plugin_name: str) -> CircuitBreaker:
        """Return (or create) the :class:`CircuitBreaker` for *plugin_name*."""
        if plugin_name not in self._circuit_breakers:
            self._circuit_breakers[plugin_name] = CircuitBreaker(name=plugin_name)
        return self._circuit_breakers[plugin_name]

    async def _publish_outbox_event(
        self,
        hook_name: str,
        results: list[dict[str, Any]],
        **kwargs: Any,
    ) -> None:
        """Publish a transactional outbox entry for a critical hook dispatch.

        The aggregate_id is extracted from ``kwargs`` (e.g. ``node_id`` for
        node hooks, ``plugin_id`` for plugin hooks).  Falls back silently if
        the expected kwarg is absent.
        """
        critical = _CRITICAL_HOOKS.get(hook_name)
        if critical is None:
            return
        event_type, agg_key, agg_type = critical

        aggregate_id: str | None = kwargs.get(agg_key)  # type: ignore[assignment]
        if not aggregate_id:
            logger.debug(
                "HookBus: cannot publish outbox event for '%s': "
                "no '%s' in kwargs",
                hook_name,
                agg_key,
            )
            return

        db = kwargs.get("db")
        try:
            from master.core.outbox import outbox

            await outbox.publish(
                event_type=event_type,
                aggregate_id=aggregate_id,
                aggregate_type=agg_type,
                payload={
                    "hook_name": hook_name,
                    "result_count": len(results),
                    "success_count": sum(1 for r in results if r.get("success")),
                    "failure_count": sum(1 for r in results if not r.get("success")),
                },
                db=db,
            )
        except Exception:
            logger.exception(
                "HookBus: failed to publish outbox event '%s' for %s '%s'",
                event_type,
                agg_type,
                aggregate_id,
            )
