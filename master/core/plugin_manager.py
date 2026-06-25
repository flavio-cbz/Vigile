"""
Vigile — Plugin Manager

Native implementation of a hook-based plugin system, inspired by Pluggy (pytest).
Zero dependency on the Pluggy library itself.

Concepts:
  - Hook: a named event point (e.g. "get_supported_actions", "handle_intent")
  - Implementation: a callable registered to a hook
  - Plugin: a Python module with a register(pm) function

Features beyond the PLAN.md sketch:
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
import json
import logging
import os
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_BUILTIN_PLUGIN_FILE_TO_ID = {
    "metrics_plugin": "metrics",
    "systemd_plugin": "systemd",
    "docker_plugin": "docker",
}

_BUILTIN_PLUGIN_ID_TO_FILE = {
    plugin_id: file_stem for file_stem, plugin_id in _BUILTIN_PLUGIN_FILE_TO_ID.items()
}


def canonical_plugin_id(plugin_name: str) -> str:
    """Map an on-disk plugin stem to the public plugin id."""
    return _BUILTIN_PLUGIN_FILE_TO_ID.get(plugin_name, plugin_name)


def plugin_file_stem(plugin_id: str) -> str:
    """Resolve the file stem for a public plugin id."""
    return _BUILTIN_PLUGIN_ID_TO_FILE.get(plugin_id, plugin_id)


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
        self._db: Any | None = None
        self._active_calls: dict[str, int] = {}
        self._draining_plugins: set[str] = set()
        self._enabled_plugins: set[str] | None = None

    async def initialize(self, db: Any) -> None:
        """
        Initialize the plugin manager with a database connection
        and load the set of enabled plugins.
        """
        self._db = db
        try:
            async with db.execute(
                "SELECT plugin_id FROM plugin_configs WHERE enabled = 1"
            ) as cursor:
                rows = await cursor.fetchall()
                self._enabled_plugins = {row[0] for row in rows}
            logger.info("PluginManager initialized. Enabled plugins: %s", self._enabled_plugins)
        except Exception as e:
            logger.error(
                "Failed to query enabled plugins during PluginManager initialization: %s", e
            )
            self._enabled_plugins = None

    async def get_plugin_config(self, plugin_name: str) -> dict[str, Any]:
        """
        Retrieve configuration for a plugin from the database.
        """
        if self._db is None:
            return {}
        try:
            async with self._db.execute(
                "SELECT config_json FROM plugin_configs WHERE plugin_id = ?", (plugin_name,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return json.loads(row[0])
        except Exception as e:
            logger.error("Error fetching config for plugin '%s': %s", plugin_name, e)
        return {}

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
                    hook_name,
                    plugin_name,
                )
                continue

            if self._enabled_plugins is not None and plugin_name not in self._enabled_plugins:
                continue

            self._active_calls[plugin_name] = self._active_calls.get(plugin_name, 0) + 1
            try:
                result = fn(**kwargs)
                if result is not None:
                    results.append(result)
            except Exception:
                logger.exception(
                    "Hook '%s' impl from '%s' raised an exception", hook_name, plugin_name
                )
            finally:
                self._active_calls[plugin_name] -= 1
        return results

    def call_first(self, hook_name: str, **kwargs: Any) -> Any | None:
        """
        Like call(), but returns only the first non-None result.
        Useful for hooks where only one plugin should handle a given action.
        """
        for plugin_name, fn in self._hooks.get(hook_name, []):
            if inspect.iscoroutinefunction(fn):
                continue

            if self._enabled_plugins is not None and plugin_name not in self._enabled_plugins:
                continue

            self._active_calls[plugin_name] = self._active_calls.get(plugin_name, 0) + 1
            try:
                result = fn(**kwargs)
                if result is not None:
                    return result
            except Exception:
                logger.exception(
                    "Hook '%s' impl from '%s' raised an exception", hook_name, plugin_name
                )
            finally:
                self._active_calls[plugin_name] -= 1
        return None

    # -----------------------------------------------------------------------
    # Async dispatch
    # -----------------------------------------------------------------------

    async def _run_async_hook(
        self, plugin_name: str, fn: Callable, hook_name: str, **kwargs: Any
    ) -> Any:
        self._active_calls[plugin_name] = self._active_calls.get(plugin_name, 0) + 1
        try:
            if inspect.iscoroutinefunction(fn):
                return await fn(**kwargs)
            else:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(None, lambda: fn(**kwargs))
        finally:
            self._active_calls[plugin_name] -= 1

    async def async_call(self, hook_name: str, **kwargs: Any) -> list[Any]:
        """
        Invoke all implementations (sync + async) for hook_name concurrently.
        Sync implementations are run in the event loop's executor.

        Returns a list of non-None results.
        """
        tasks: list[asyncio.Future] = []

        for plugin_name, fn in self._hooks.get(hook_name, []):
            if self._enabled_plugins is not None and plugin_name not in self._enabled_plugins:
                continue

            fut = asyncio.create_task(
                self._run_async_hook(plugin_name, fn, hook_name, **kwargs),
                name=f"{plugin_name}.{hook_name}",
            )
            tasks.append(fut)

        if not tasks:
            return []

        results_raw = await asyncio.gather(*tasks, return_exceptions=True)
        results: list[Any] = []
        for i, res in enumerate(results_raw):
            if isinstance(res, Exception):
                logger.exception("Async hook '%s' task %d raised: %s", hook_name, i, res)
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
            plugin_id = canonical_plugin_id(plugin_name)

            if self._enabled_plugins is not None and plugin_id not in self._enabled_plugins:
                logger.info("Plugin '%s' is disabled in database — skipping load.", plugin_id)
                continue

            if plugin_id in self._loaded_plugins:
                logger.debug("Plugin '%s' already loaded — skipped.", plugin_id)
                continue

            success = self.load_plugin(plugin_name, plugins_dir)
            if success:
                loaded.append(plugin_id)

        return loaded

    def load_plugin(self, plugin_name: str, plugins_dir: str) -> bool:
        plugin_id = canonical_plugin_id(plugin_name)
        plugin_path = os.path.join(plugins_dir, f"{plugin_name}.py")
        if not os.path.isfile(plugin_path):
            logger.warning("Plugin file not found: %s", plugin_path)
            return False

        if plugin_id in self._loaded_plugins:
            logger.debug("Plugin '%s' already loaded — skipped.", plugin_id)
            return True

        try:
            module_name = f"vigile.plugins.{plugin_name}"
            spec = importlib.util.spec_from_file_location(module_name, plugin_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not load spec for {plugin_path}")

            module = importlib.util.module_from_spec(spec)

            # Register in sys.modules before executing to handle relative/absolute imports cleanly
            import sys

            sys.modules[module_name] = module

            spec.loader.exec_module(module)

            if not hasattr(module, "register"):
                logger.warning("Plugin '%s' has no register() function — skipped.", plugin_id)
                if module_name in sys.modules:
                    del sys.modules[module_name]
                return False

            module.register(self)
            self._loaded_plugins.append(plugin_id)
            if self._enabled_plugins is not None:
                self._enabled_plugins.add(plugin_id)
            logger.info("Plugin loaded: %s", plugin_id)
            return True
        except Exception:
            logger.exception("Failed to load plugin '%s'", plugin_id)
            module_name = f"vigile.plugins.{plugin_name}"
            import sys

            if module_name in sys.modules:
                del sys.modules[module_name]
            return False

    async def unload_plugin(self, plugin_name: str) -> None:
        """
        Safely unload a plugin by unregistering hooks and draining active calls.
        """
        plugin_id = canonical_plugin_id(plugin_name)
        module_stem = plugin_file_stem(plugin_name)

        logger.info("Unloading plugin '%s'...", plugin_id)
        self._draining_plugins.add(plugin_id)

        # 1. Unregister all hooks
        for hook_name in list(self._hooks.keys()):
            self.unregister(hook_name, plugin_id)

        # 2. Drain active running tasks
        while self._active_calls.get(plugin_id, 0) > 0:
            logger.debug(
                "Draining plugin '%s' (active calls: %d)", plugin_id, self._active_calls[plugin_id]
            )
            await asyncio.sleep(0.05)

        # 3. Clean up loaded list and sys.modules
        if plugin_id in self._loaded_plugins:
            self._loaded_plugins.remove(plugin_id)
        if self._enabled_plugins is not None and plugin_id in self._enabled_plugins:
            self._enabled_plugins.remove(plugin_id)

        module_name = f"vigile.plugins.{module_stem}"
        import sys

        if module_name in sys.modules:
            del sys.modules[module_name]

        self._draining_plugins.discard(plugin_id)
        logger.info("Plugin '%s' unloaded successfully.", plugin_id)

    # -----------------------------------------------------------------------
    # Introspection
    # -----------------------------------------------------------------------

    def get_hooks(self) -> dict[str, list[str]]:
        """Return a dict of hook_name → [plugin_names] for debugging."""
        return {hook: [pn for pn, _ in impls] for hook, impls in self._hooks.items()}

    @property
    def loaded_plugins(self) -> list[str]:
        return list(self._loaded_plugins)

    def has_hook(self, hook_name: str) -> bool:
        return bool(self._hooks.get(hook_name))


# Module-level singleton (imported by other modules)
plugin_manager = PluginManager()
