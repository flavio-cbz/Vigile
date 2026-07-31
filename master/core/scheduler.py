"""
Vigile — Scheduler

Background task runner for the Sprint 9 Plugin Engine.

Each plugin can declare a list of periodic tasks (``ScheduleSpec`` in the
manifest). The Scheduler owns the asyncio tasks for those periodic loops and
exposes a clean lifecycle:

  - start(plugin_id, tasks_spec, instance)  : spawn the loops
  - stop(plugin_id)                         : cancel & await each loop, draining
  - shutdown()                              : stop every plugin (FastAPI lifespan)

Active callback accounting (``_active_callbacks``) lets an external drain
mechanism wait for in-flight handler invocations before declaring a plugin
DEACTIVATED — the same contract the legacy PluginManager's
``_active_calls`` provided.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Per-task cancellation grace period (seconds) when stopping a plugin.
_STOP_TIMEOUT: float = 10.0


class Scheduler:
    """
    Owns the asyncio background task loops for plugin schedules.
    """

    def __init__(self) -> None:
        # "{plugin_id}:{task_name}" -> asyncio.Task
        self._tasks: dict[str, asyncio.Task] = {}
        # plugin_id -> number of in-flight handler invocations
        self._active_callbacks: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, plugin_id: str, tasks_spec: list[dict], instance: Any) -> None:
        """Spawn a periodic loop for every spec in ``tasks_spec``.

        ``tasks_spec`` is a list of mappings with keys ``name``,
        ``interval_secs`` and ``handler`` (the method name on ``instance``).
        Existing tasks for ``plugin_id`` are left untouched — call
        :meth:`stop` first to avoid duplicates.
        """
        for spec in tasks_spec:
            key = f"{plugin_id}:{spec['name']}"
            task = asyncio.create_task(self._loop(plugin_id, spec, instance))
            self._tasks[key] = task
            logger.info(
                "Scheduler: started task '%s' for plugin '%s' (every %ss)",
                spec["name"],
                plugin_id,
                spec["interval_secs"],
            )

    async def stop(self, plugin_id: str) -> None:
        """Cancel and await every task owned by ``plugin_id``.

        Each task gets ``_STOP_TIMEOUT`` seconds to finish after cancellation.
        ``CancelledError`` is the expected outcome and is silently swallowed.
        A task that resists cancellation past the timeout is logged as an
        error and left in the registry only if it is still alive.
        """
        keys_to_stop = [k for k in self._tasks if k.startswith(f"{plugin_id}:")]
        if not keys_to_stop:
            # Still drain the callback counter so callers can rely on stop()
            # always resetting it.
            self._active_callbacks.pop(plugin_id, None)
            return

        for key in keys_to_stop:
            task = self._tasks.pop(key, None)
            if task is None or task.done():
                continue
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=_STOP_TIMEOUT)
            except asyncio.CancelledError:
                # Expected: the loop honored cancellation.
                pass
            except asyncio.TimeoutError:
                logger.error(
                    "Scheduler: task '%s' did not stop within %.1fs — still running",
                    key,
                    _STOP_TIMEOUT,
                )

        # Drain the active-callback counter for this plugin.
        self._active_callbacks.pop(plugin_id, None)
        logger.info("Scheduler: stopped all tasks for plugin '%s'", plugin_id)

    async def shutdown(self) -> None:
        """Stop every plugin's tasks. Intended for the FastAPI lifespan shutdown."""
        plugin_ids = {
            key.split(":", 1)[0] for key in list(self._tasks.keys()) if ":" in key
        }
        for plugin_id in plugin_ids:
            await self.stop(plugin_id)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def active_callbacks(self, plugin_id: str) -> int:
        """Return the number of in-flight handler invocations for ``plugin_id``."""
        return self._active_callbacks.get(plugin_id, 0)

    def has_tasks(self, plugin_id: str) -> bool:
        """True if any task is currently tracked for ``plugin_id``."""
        return any(key.startswith(f"{plugin_id}:") for key in self._tasks)

    # ------------------------------------------------------------------
    # Loop coroutine
    # ------------------------------------------------------------------

    async def _loop(self, plugin_id: str, spec: dict, instance: Any) -> None:
        """Periodically invoke ``instance.<handler>`` every ``interval_secs``.

        The handler may be sync or async; sync handlers run in the default
        executor. Each invocation increments the plugin's active-callback
        counter for the duration of the call. Exceptions are logged and the
        loop continues. The loop terminates only on cancellation.
        """
        handler_name: str = spec["handler"]
        interval: float = float(spec["interval_secs"])
        loop = asyncio.get_running_loop()
        next_tick = loop.time() + interval

        while True:
            method = getattr(instance, handler_name, None)
            if method is None:
                logger.error(
                    "Scheduler: plugin '%s' instance has no attribute '%s' — stopping loop",
                    plugin_id,
                    handler_name,
                )
                return

            self._active_callbacks[plugin_id] = self._active_callbacks.get(plugin_id, 0) + 1
            try:
                if inspect.iscoroutinefunction(method):
                    await method()
                else:
                    await loop.run_in_executor(None, method)
            except asyncio.CancelledError:
                # Propagate cancellation but keep the counter consistent.
                self._active_callbacks[plugin_id] = max(
                    0, self._active_callbacks.get(plugin_id, 1) - 1
                )
                raise
            except Exception:
                logger.exception(
                    "Scheduler: handler '%s' for plugin '%s' raised an exception",
                    handler_name,
                    plugin_id,
                )
            finally:
                # Only decrement if we did not re-raise CancelledError above.
                current = self._active_callbacks.get(plugin_id, 0)
                if current > 0:
                    self._active_callbacks[plugin_id] = current - 1

            # Fixed-cadence sleep (anti-drift): sleep until the next absolute tick
            next_tick += interval
            now = loop.time()
            if next_tick <= now:
                # Handler overran one or more intervals: skip missed ticks
                # (no catch-up burst, no spin), re-anchor to now + interval
                next_tick = now + interval
            try:
                await asyncio.sleep(next_tick - now)
            except asyncio.CancelledError:
                raise
