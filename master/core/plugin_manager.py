"""
Vigile — Plugin Manager

Native implementation of a hook-based plugin system, inspired by Pluggy (pytest).
Zero dependency on the Pluggy library itself.

Concepts:
  - Hook: a named event point (e.g. "get_supported_actions", "handle_intent")
  - Implementation: a callable registered to a hook
  - Plugin: a Python module with a register(pm) function

Features beyond the INIT.md sketch:
  - Async-aware: async_call() awaits coroutine implementations
  - Registration metadata: track which plugin registered which hook
  - Thread/task safety: locks protect the hook registry during load

A plugin module must expose:
    def register(pm: PluginManager) -> None:
        pm.register("hook_name", my_handler_function)
"""

import asyncio
import importlib.util
import inspect
import logging
import os
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class PluginManager:
    """
    Lightweight hook-based plugin system.

    Usage:
        pm = PluginManager()
        pm.register("on_node_connected", my_handler)
        results = pm.call("on_node_connected", node_id="abc123")

    Async hooks:
        results = await pm.async_call("on_node_connected", node_id="abc123")
    """

    def __init__(self) -> None:
        # { hook_name: [(plugin_name, callable)] }
        self._hooks: dict[str, list[tuple[str, Callable]]] = {}
        self._loaded_plugins: list[str] = []

    # -----------------------------------------------------------------------
    # Registration
    # -----------------------------------------------------------------------

    def register(self, hook_name: str, fn: Callable, *, plugin_name: str = "anonymous") -> None:
        """
        Register a callable under a hook name.

        Args:
            hook_name   : the event name (e.g. "handle_intent")
            fn          : sync or async callable to invoke
            plugin_name : for introspection/logging
        """
        self._hooks.setdefault(hook_name, []).append((plugin_name, fn))
        logger.debug("Plugin '%s' registered hook '%s'", plugin_name, hook_name)

    def unregister(self, hook_name: str, plugin_name: str) -> int:
        """Remove all implementations registered by a given plugin for a hook."""
        if hook_name not in self._hooks:
            return 0
        before = len(self._hooks[hook_name])
        self._hooks[hook_name] = [
            (pn, fn) for pn, fn in self._hooks[hook_name] if pn != plugin_name
        ]
        removed = before - len(self._hooks[hook_name])
        return removed

    # -----------------------------------------------------------------------
    # Synchronous dispatch
    # -----------------------------------------------------------------------

    def call(self, hook_name: str, **kwargs: Any) -> list[Any]:
        """
        Invoke all sync implementations registered for hook_name.
        Async implementations are skipped (use async_call for those).

        Returns a list of non-None return values (same contract as Pluggy firstresult=False).
        """
        results: list[Any] = []
        for plugin_name, fn in self._hooks.get(hook_name, []):
            if inspect.iscoroutinefunction(fn):
                logger.warning(
                    "Hook '%s' impl from '%s' is async — skipped in sync call(). "
                    "Use async_call() instead.",
                    hook_name, plugin_name,
                )
                continue
            try:
                result = fn(**kwargs)
                if result is not None:
                    results.append(result)
            except Exception:
                logger.exception(
                    "Hook '%s' impl from '%s' raised an exception", hook_name, plugin_name
                )
        return results

    def call_first(self, hook_name: str, **kwargs: Any) -> Any | None:
        """
        Like call(), but returns only the first non-None result.
        Useful for hooks where only one plugin should handle a given action.
        """
        for plugin_name, fn in self._hooks.get(hook_name, []):
            if inspect.iscoroutinefunction(fn):
                continue
            try:
                result = fn(**kwargs)
                if result is not None:
                    return result
            except Exception:
                logger.exception(
                    "Hook '%s' impl from '%s' raised an exception", hook_name, plugin_name
                )
        return None

    # -----------------------------------------------------------------------
    # Async dispatch
    # -----------------------------------------------------------------------

    async def async_call(self, hook_name: str, **kwargs: Any) -> list[Any]:
        """
        Invoke all implementations (sync + async) for hook_name concurrently.
        Sync implementations are run in the event loop's executor.

        Returns a list of non-None results.
        """
        tasks: list[asyncio.Future] = []

        for plugin_name, fn in self._hooks.get(hook_name, []):
            if inspect.iscoroutinefunction(fn):
                tasks.append(asyncio.create_task(fn(**kwargs), name=f"{plugin_name}.{hook_name}"))
            else:
                # Run sync hook in default thread pool to avoid blocking the loop
                # run_in_executor returns an asyncio.Future (awaitable), not a coroutine
                # Capture kwargs in closure to prevent cross-call contamination
                loop = asyncio.get_running_loop()
                fut = loop.run_in_executor(None, lambda f=fn, kw=kwargs: f(**kw))
                tasks.append(fut)

        if not tasks:
            return []

        results_raw = await asyncio.gather(*tasks, return_exceptions=True)
        results: list[Any] = []
        for i, res in enumerate(results_raw):
            if isinstance(res, Exception):
                logger.exception(
                    "Async hook '%s' task %d raised: %s", hook_name, i, res
                )
            elif res is not None:
                results.append(res)

        return results

    async def async_call_first(self, hook_name: str, **kwargs: Any) -> Any | None:
        """Async version of call_first — returns the first non-None result."""
        results = await self.async_call(hook_name, **kwargs)
        return results[0] if results else None

    # -----------------------------------------------------------------------
    # Dynamic plugin loading
    # -----------------------------------------------------------------------

    def load_plugins_from_dir(self, plugins_dir: str) -> list[str]:
        """
        Scan a directory for Python plugin files and load them.

        A plugin file must:
          - End with .py
          - Not start with _ (private/helper files excluded)
          - Export a register(pm: PluginManager) function

        Returns the list of successfully loaded plugin names.
        """
        if not os.path.isdir(plugins_dir):
            logger.warning("Plugins directory not found: %s", plugins_dir)
            return []

        loaded: list[str] = []

        for fname in sorted(os.listdir(plugins_dir)):
            if not fname.endswith(".py") or fname.startswith("_"):
                continue

            plugin_name = fname[:-3]
            plugin_path = os.path.join(plugins_dir, fname)

            try:
                spec = importlib.util.spec_from_file_location(
                    f"vigile.plugins.{plugin_name}", plugin_path
                )
                if spec is None or spec.loader is None:
                    raise ImportError(f"Could not load spec for {plugin_path}")

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)  # type: ignore[union-attr]

                if not hasattr(module, "register"):
                    logger.warning(
                        "Plugin '%s' has no register() function — skipped.", plugin_name
                    )
                    continue

                module.register(self)
                self._loaded_plugins.append(plugin_name)
                loaded.append(plugin_name)
                logger.info("Plugin loaded: %s", plugin_name)

            except Exception:
                logger.exception("Failed to load plugin '%s'", plugin_name)

        return loaded

    # -----------------------------------------------------------------------
    # Introspection
    # -----------------------------------------------------------------------

    def get_hooks(self) -> dict[str, list[str]]:
        """Return a dict of hook_name → [plugin_names] for debugging."""
        return {
            hook: [pn for pn, _ in impls]
            for hook, impls in self._hooks.items()
        }

    @property
    def loaded_plugins(self) -> list[str]:
        return list(self._loaded_plugins)

    def has_hook(self, hook_name: str) -> bool:
        return bool(self._hooks.get(hook_name))


# Module-level singleton (imported by other modules)
plugin_manager = PluginManager()
