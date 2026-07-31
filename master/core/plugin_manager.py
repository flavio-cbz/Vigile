from __future__ import annotations

"""
Vigile — Plugin Manager

Native implementation of a hook-based plugin system, inspired by Pluggy (pytest).
Zero dependency on the Pluggy library itself.

Concepts:
  - Hook: a named event point (e.g. "get_supported_actions", "handle_intent")
  - Implementation: a callable registered to a hook
  - Plugin: a Python module with a register(pm) function

Sandbox Isolation:
  - Supports running plugins in separate subprocesses (sandbox=True) for crash resilience.
  - Implements remote database operations proxying to preserve database functionality.
"""

import asyncio
import importlib.util
import json
import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from master.core.plugin_engine import PluginEngine

logger = logging.getLogger(__name__)

from master.core.plugin_ids import canonical_plugin_id, plugin_file_stem
from master.core.hook_bus import HookBus



class PluginProcessWrapper:
    """
    Manages the lifecycle of an isolated plugin subprocess.
    Communicates via JSON-RPC lines on stdin/stdout, and handles database proxying.
    """

    def __init__(self, plugin_name: str, plugin_path: str):
        self.plugin_name = plugin_name
        self.plugin_path = plugin_path
        self.process: asyncio.subprocess.Process | None = None
        self.hooks: list[str] = []
        self.schema: dict[str, Any] = {}
        self._pending_calls: dict[str, asyncio.Future] = {}
        self._active_db_conns: dict[str, Any] = {}
        self._stdout_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._init_future: asyncio.Future | None = None

    async def start(self) -> None:
        import sys

        # Resolve script path relative to this file
        worker_script = os.path.join(os.path.dirname(__file__), "plugin_worker.py")
        loop = asyncio.get_running_loop()
        self._init_future = loop.create_future()

        env = os.environ.copy()
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if "PYTHONPATH" in env:
            env["PYTHONPATH"] = f"{project_root}:{env['PYTHONPATH']}"
        else:
            env["PYTHONPATH"] = project_root

        logger.info("Starting isolated plugin process for '%s'...", self.plugin_name)
        self.process = await asyncio.create_subprocess_exec(
            sys.executable,
            worker_script,
            self.plugin_name,
            self.plugin_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        self._stdout_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())

        try:
            await asyncio.wait_for(self._init_future, timeout=10.0)
            logger.info(
                "Isolated plugin process '%s' initialized with hooks: %s",
                self.plugin_name,
                self.hooks,
            )
        except asyncio.TimeoutError:
            logger.error("Initialization timed out for plugin process '%s'", self.plugin_name)
            await self.stop()
            raise RuntimeError(
                f"Plugin '{self.plugin_name}' worker process failed to initialize within 10s"
            )

    async def stop(self) -> None:
        logger.info("Stopping isolated plugin process '%s'...", self.plugin_name)
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except Exception:
                if self.process:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
            self.process = None

        if self._stdout_task:
            self._stdout_task.cancel()
            self._stdout_task = None
        if self._stderr_task:
            self._stderr_task.cancel()
            self._stderr_task = None

    async def _send_to_child(self, msg: dict) -> None:
        if self.process and self.process.stdin:
            data = (json.dumps(msg) + "\n").encode()
            self.process.stdin.write(data)
            await self.process.stdin.drain()

    async def _read_stdout(self) -> None:
        while self.process and self.process.stdout:
            line = await self.process.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode().strip())
                msg_type = msg.get("type")
                call_id = msg.get("call_id")

                if msg_type == "init":
                    self.hooks = msg.get("hooks", [])
                    self.schema = msg.get("schema", {})
                    if self._init_future and not self._init_future.done():
                        self._init_future.set_result(True)
                    continue

                if msg_type == "response":
                    fut = self._pending_calls.get(call_id)
                    if fut and not fut.done():
                        if msg.get("status") == "success":
                            fut.set_result(msg.get("result"))
                        else:
                            fut.set_exception(RuntimeError(msg.get("error")))
                    continue

                if msg_type in ("db_query",):
                    asyncio.create_task(self._handle_db_request(msg))
                    continue

            except Exception:
                logger.exception(
                    "[%s-parent] Failed to parse stdout line: %r", self.plugin_name, line
                )

    async def _read_stderr(self) -> None:
        while self.process and self.process.stderr:
            line = await self.process.stderr.readline()
            if not line:
                break
            logger.info("[%s-child-stderr] %s", self.plugin_name, line.decode().strip())

    async def _handle_db_request(self, msg: dict) -> None:
        call_id = cast(str, msg.get("call_id"))
        db_call_id = msg.get("db_call_id")
        msg_type = msg.get("type")

        # Get DB connection from call context or fallback
        db = self._active_db_conns.get(call_id)
        if not db:
            from master.db.database import get_db_conn

            try:
                db = get_db_conn()
            except Exception:
                db = None

        if not db:
            await self._send_to_child(
                {
                    "type": "db_result",
                    "db_call_id": db_call_id,
                    "status": "error",
                    "error": "No database connection available",
                }
            )
            return

        try:
            if msg_type == "db_query":
                sql = msg["sql"]
                params = msg.get("params", [])
                cursor = await db.execute(sql, params)
                rows = await cursor.fetchall()
                serializable_rows = [dict(r) for r in rows]
                await self._send_to_child(
                    {
                        "type": "db_result",
                        "db_call_id": db_call_id,
                        "status": "success",
                        "result": {
                            "rowcount": cursor.rowcount,
                            "lastrowid": cursor.lastrowid,
                            "rows": serializable_rows,
                        },
                    }
                )
        except Exception as e:
            logger.exception("[%s-parent] Database request failed", self.plugin_name)
            await self._send_to_child(
                {"type": "db_result", "db_call_id": db_call_id, "status": "error", "error": str(e)}
            )

    async def call_hook(self, hook_name: str, **kwargs: Any) -> Any:
        # Check process status and restart if dead
        if not self.process or self.process.returncode is not None:
            logger.warning("Plugin process '%s' is not running. Restarting...", self.plugin_name)
            await self.start()

        call_id = str(asyncio.get_running_loop().time()) + "-" + os.urandom(4).hex()
        fut = asyncio.get_running_loop().create_future()
        self._pending_calls[call_id] = fut

        # Extract db connection if present
        db = kwargs.pop("db", None)
        if db:
            self._active_db_conns[call_id] = db

        try:
            await self._send_to_child(
                {"type": "call_hook", "call_id": call_id, "hook_name": hook_name, "kwargs": kwargs}
            )
            return await fut
        finally:
            self._pending_calls.pop(call_id, None)
            self._active_db_conns.pop(call_id, None)


class PluginManager:
    """
    Lightweight hook-based plugin system.
    Supports in-process (sandbox=False) and out-of-process (sandbox=True) runners.
    """

    def __init__(self, engine: Any | None = None, hook_bus: HookBus | None = None) -> None:
        self._engine: Any = engine
        if hook_bus is not None:
            self._hook_bus: HookBus = hook_bus
        elif engine is not None and getattr(engine, "hook_bus", None) is not None:
            self._hook_bus = engine.hook_bus
        else:
            self._hook_bus = HookBus()
        self._hooks: dict[str, list[tuple[str, Callable]]] = self._hook_bus._hooks
        self._loaded_plugins: list[str] = []
        self._db: Any | None = None
        self._active_calls: dict[str, int] = {}
        self._draining_plugins: set[str] = set()
        self._enabled_plugins: set[str] | None = None
        self._disabled_plugins: set[str] | None = None
        self._sandbox: bool = False
        self._wrappers: dict[str, PluginProcessWrapper] = {}

    def set_engine(self, engine: Any) -> None:
        self._engine = engine

    async def initialize(self, db: Any, sandbox: bool = True) -> None:
        """
        Initialize the plugin manager with a database connection,
        load disabled plugin IDs, and set sandbox mode.
        """
        self._db = db
        self._sandbox = sandbox
        try:
            async with db.execute(
                "SELECT id FROM plugins WHERE enabled = 0"
            ) as cursor:
                rows = await cursor.fetchall()
                self._disabled_plugins = set()
                for row in rows:
                    raw_id = row[0]
                    self._disabled_plugins.add(raw_id)
                    self._disabled_plugins.add(canonical_plugin_id(raw_id))
                    self._disabled_plugins.add(plugin_file_stem(raw_id))
            logger.info(
                "PluginManager initialized. Disabled plugins: %s (Sandbox=%s)",
                self._disabled_plugins,
                self._sandbox,
            )
        except Exception as e:
            logger.error(
                "Failed to query disabled plugins during PluginManager initialization: %s", e
            )
            self._disabled_plugins = set()

    async def get_plugin_config(self, plugin_name: str) -> dict[str, Any]:
        """
        Retrieve configuration for a plugin from the database.
        """
        if self._db is None:
            return {}
        try:
            async with self._db.execute(
                "SELECT config_json FROM plugins WHERE id = ?", (plugin_name,)
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
        """Subscribe ``fn`` to ``hook_name`` under ``plugin_name``.

        Delegates to the :class:`HookBus` — single source of truth for hook
        registration.  Validates ``hook_name`` against the :class:`HookName`
        enum — a warning is logged for unknown hook names so that typos are
        surfaced early without breaking compatibility.
        """
        self._hook_bus.register(hook_name, fn, plugin_name=plugin_name)
        logger.debug("Plugin '%s' registered hook '%s'", plugin_name, hook_name)

    def unregister(self, hook_name: str, plugin_name: str) -> int:
        """Remove every subscription from ``plugin_name`` on ``hook_name``.

        Delegates to the :class:`HookBus`.
        Returns the number of subscriptions removed.
        """
        return self._hook_bus.unregister(hook_name, plugin_name)

    # -----------------------------------------------------------------------
    # Synchronous dispatch
    # -----------------------------------------------------------------------

    def call(self, hook_name: str, **kwargs: Any) -> list[Any]:
        """Invoke every sync subscription for ``hook_name`` in registration order.

        Delegates to the :class:`HookBus`.  Async callables are skipped with a
        warning.  Exceptions raised by a hook are caught and logged; dispatch
        continues to the next subscription.  Returns the list of non-None
        results, in registration order.
        """
        return self._hook_bus.call(hook_name, **kwargs)

    def call_first(self, hook_name: str, **kwargs: Any) -> Any | None:
        """Like :meth:`call` but stops at the first non-None result.

        Delegates to the :class:`HookBus`.
        """
        return self._hook_bus.call_first(hook_name, **kwargs)

    # -----------------------------------------------------------------------
    # Async dispatch
    # -----------------------------------------------------------------------

    async def async_call(self, hook_name: str, **kwargs: Any) -> list[Any]:
        """Invoke every subscription for ``hook_name`` concurrently.

        Delegates to the :class:`HookBus`.  Returns a list of non-None
        results from successful hooks.
        """
        results = await self._hook_bus.async_call(hook_name, **kwargs)
        return [r["result"] for r in results if r.get("success") and r.get("result") is not None]

    async def async_call_first(self, hook_name: str, **kwargs: Any) -> Any | None:
        """Async first-non-None: delegates to :meth:`async_call`.

        Returns the **result value** of the first successful subscription
        whose result is not None, or ``None`` if no hook returned a value.
        """
        return await self._hook_bus.async_call_first(hook_name, **kwargs)

    # -----------------------------------------------------------------------
    # Dynamic plugin loading
    # -----------------------------------------------------------------------

    async def load_plugins_from_dir(self, plugins_dir: str) -> list[str]:
        """
        Scan a directory for Python plugin files and load them.
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

            if self._disabled_plugins is not None and plugin_id in self._disabled_plugins:
                logger.info("Plugin '%s' is disabled in database — skipping load.", plugin_id)
                continue

            if plugin_id in self._loaded_plugins:
                logger.debug("Plugin '%s' already loaded — skipped.", plugin_id)
                continue

            success = await self.load_plugin(plugin_name, plugins_dir)
            if success:
                loaded.append(plugin_id)

        return loaded

    async def load_plugin(self, plugin_name: str, plugins_dir: str) -> bool:
        plugin_id = canonical_plugin_id(plugin_name)
        plugin_path = os.path.join(plugins_dir, f"{plugin_name}.py")
        if not os.path.isfile(plugin_path):
            pkg_init = os.path.join(plugins_dir, plugin_name, "__init__.py")
            if os.path.isfile(pkg_init):
                plugin_path = pkg_init
            else:
                logger.warning("Plugin file not found: %s", plugin_path)
                return False

        if plugin_id in self._loaded_plugins:
            logger.debug("Plugin '%s' already loaded — skipped.", plugin_id)
            return True

        if self._sandbox:
            try:
                wrapper = PluginProcessWrapper(plugin_id, plugin_path)
                await wrapper.start()
                self._wrappers[plugin_id] = wrapper

                # Register hook proxies
                for hook_name in wrapper.hooks:
                    self.register(
                        hook_name, self._make_proxy(wrapper, hook_name), plugin_name=plugin_id
                    )

                self._loaded_plugins.append(plugin_id)
                if self._disabled_plugins is not None:
                    self._disabled_plugins.discard(plugin_id)
                    self._disabled_plugins.discard(plugin_name)
                    self._disabled_plugins.discard(plugin_file_stem(plugin_id))
                if self._engine is not None:
                    self._engine.lifecycle._set_runtime(plugin_id, "ACTIVE")
                logger.info("Plugin loaded in isolated subprocess: %s", plugin_id)
                return True
            except Exception:
                logger.exception("Failed to load plugin '%s' in isolated subprocess", plugin_id)
                return False
        else:
            # Standalone dynamic load
            try:
                module_name = f"vigile.plugins.{plugin_name}"
                import sys

                if module_name in sys.modules:
                    sys.modules.pop(module_name)
                    for hook_name in list(self._hooks.keys()):
                        self.unregister(hook_name, plugin_id)
                        self.unregister(hook_name, plugin_name)

                spec = importlib.util.spec_from_file_location(module_name, plugin_path)
                if spec is None or spec.loader is None:
                    raise ImportError(f"Could not load spec for {plugin_path}")

                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                if not hasattr(module, "register"):
                    logger.warning("Plugin '%s' has no register() function — skipped.", plugin_id)
                    if module_name in sys.modules:
                        del sys.modules[module_name]
                    return False

                module.register(self)
                self._loaded_plugins.append(plugin_id)
                if self._disabled_plugins is not None:
                    self._disabled_plugins.discard(plugin_id)
                    self._disabled_plugins.discard(plugin_name)
                    self._disabled_plugins.discard(plugin_file_stem(plugin_id))
                if self._engine is not None:
                    self._engine.lifecycle._set_runtime(plugin_id, "ACTIVE")
                logger.info("Plugin loaded in-process: %s", plugin_id)
                return True
            except Exception:
                logger.exception("Failed to load plugin '%s' in-process", plugin_id)
                module_name = f"vigile.plugins.{plugin_name}"
                import sys

                if module_name in sys.modules:
                    del sys.modules[module_name]
                return False

    def _make_proxy(self, wrapper: PluginProcessWrapper, hook_name: str) -> Callable:
        async def proxy(**kwargs: Any) -> Any:
            return await wrapper.call_hook(hook_name, **kwargs)

        return proxy

    async def unload_plugin(self, plugin_name: str) -> None:
        """
        Safely unload a plugin by stopping its worker process or unregistering hooks.
        """
        plugin_id = canonical_plugin_id(plugin_name)
        module_stem = plugin_file_stem(plugin_name)

        logger.info("Unloading plugin '%s'...", plugin_id)
        self._draining_plugins.add(plugin_id)

        # Deactivate via engine if available to clean up hooks, scheduler, routes
        if self._engine is not None:
            try:
                runtime = await self._engine.lifecycle.get_runtime_state(plugin_id)
                if runtime == "ACTIVE":
                    await self._engine.deactivate(plugin_id)
            except Exception as e:
                logger.error("Failed to deactivate plugin '%s' via engine: %s", plugin_id, e)

        # Stop wrapper subprocess if running in sandbox mode
        wrapper = self._wrappers.pop(plugin_id, None)
        if wrapper:
            await wrapper.stop()

        # Unmount all routes
        if self._engine is not None and self._engine.route_registrar is not None:
            self._engine.route_registrar.unmount(plugin_id)

        # Unregister all hooks
        hooks_to_check = list(self._hooks.keys())
        for hook_name in hooks_to_check:
            self.unregister(hook_name, plugin_id)

        # Drain active running tasks
        while self._active_calls.get(plugin_id, 0) > 0:
            logger.debug(
                "Draining plugin '%s' (active calls: %d)", plugin_id, self._active_calls[plugin_id]
            )
            await asyncio.sleep(0.05)

        if plugin_id in self._loaded_plugins:
            self._loaded_plugins.remove(plugin_id)
        if self._disabled_plugins is not None:
            self._disabled_plugins.add(plugin_id)
            self._disabled_plugins.add(module_stem)
            self._disabled_plugins.add(plugin_name)
        if self._engine is not None:
            self._engine.lifecycle._remove(plugin_id)

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
        """Return a {hook_name: [plugin_name, ...]} snapshot of the registry."""
        return self._hook_bus.get_hooks()

    @property
    def loaded_plugins(self) -> list[str]:
        if self._engine is not None:
            return self._engine.loaded_plugins
        return list(self._loaded_plugins)

    def has_hook(self, hook_name: str) -> bool:
        return self._hook_bus.has_hook(hook_name)


# Module-level singleton
from master.core.plugin_engine import plugin_engine as _engine  # noqa: E402

plugin_engine = _engine
plugin_manager = _engine
