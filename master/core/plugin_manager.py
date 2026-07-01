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
import inspect
import json
import logging
import os
import sys
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

        logger.info("Starting isolated plugin process for '%s'...", self.plugin_name)
        self.process = await asyncio.create_subprocess_exec(
            sys.executable,
            worker_script,
            self.plugin_name,
            self.plugin_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        self._stdout_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())

        try:
            await asyncio.wait_for(self._init_future, timeout=5.0)
            logger.info("Isolated plugin process '%s' initialized with hooks: %s", self.plugin_name, self.hooks)
        except asyncio.TimeoutError:
            logger.error("Initialization timed out for plugin process '%s'", self.plugin_name)
            await self.stop()
            raise RuntimeError(f"Plugin '{self.plugin_name}' worker process failed to initialize within 5s")

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

                if msg_type in ("db_execute", "db_commit"):
                    asyncio.create_task(self._handle_db_request(msg))
                    continue

            except Exception:
                logger.exception("[%s-parent] Failed to parse stdout line: %r", self.plugin_name, line)

    async def _read_stderr(self) -> None:
        while self.process and self.process.stderr:
            line = await self.process.stderr.readline()
            if not line:
                break
            logger.info("[%s-child-stderr] %s", self.plugin_name, line.decode().strip())

    async def _handle_db_request(self, msg: dict) -> None:
        call_id = msg.get("call_id")
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
            await self._send_to_child({
                "type": "db_result",
                "db_call_id": db_call_id,
                "status": "error",
                "error": "No database connection available"
            })
            return

        try:
            if msg_type == "db_execute":
                sql = msg["sql"]
                params = msg.get("params", [])
                cursor = await db.execute(sql, params)
                rows = await cursor.fetchall()
                serializable_rows = [dict(r) for r in rows]
                await self._send_to_child({
                    "type": "db_result",
                    "db_call_id": db_call_id,
                    "status": "success",
                    "result": {
                        "rowcount": cursor.rowcount,
                        "lastrowid": cursor.lastrowid,
                        "rows": serializable_rows
                    }
                })
            elif msg_type == "db_commit":
                await db.commit()
                await self._send_to_child({
                    "type": "db_result",
                    "db_call_id": db_call_id,
                    "status": "success",
                    "result": {}
                })
        except Exception as e:
            logger.exception("[%s-parent] Database request failed", self.plugin_name)
            await self._send_to_child({
                "type": "db_result",
                "db_call_id": db_call_id,
                "status": "error",
                "error": str(e)
            })

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
            await self._send_to_child({
                "type": "call_hook",
                "call_id": call_id,
                "hook_name": hook_name,
                "kwargs": kwargs
            })
            return await fut
        finally:
            self._pending_calls.pop(call_id, None)
            self._active_db_conns.pop(call_id, None)


class PluginManager:
    """
    Lightweight hook-based plugin system.
    Supports in-process (sandbox=False) and out-of-process (sandbox=True) runners.
    """

    def __init__(self) -> None:
        # { hook_name: [(plugin_name, callable)] }
        self._hooks: dict[str, list[tuple[str, Callable]]] = {}
        self._loaded_plugins: list[str] = []
        self._db: Any | None = None
        self._active_calls: dict[str, int] = {}
        self._draining_plugins: set[str] = set()
        self._enabled_plugins: set[str] | None = None
        self._sandbox: bool = False
        self._wrappers: dict[str, PluginProcessWrapper] = {}

    async def initialize(self, db: Any, sandbox: bool = True) -> None:
        """
        Initialize the plugin manager with a database connection,
        load enabled plugin IDs, and set sandbox mode.
        """
        self._db = db
        self._sandbox = sandbox
        try:
            async with db.execute(
                "SELECT plugin_id FROM plugin_configs WHERE enabled = 1"
            ) as cursor:
                rows = await cursor.fetchall()
                self._enabled_plugins = {row[0] for row in rows}
            logger.info("PluginManager initialized. Enabled plugins: %s (Sandbox=%s)", self._enabled_plugins, self._sandbox)
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
        Async implementations (including sandboxed proxies) are skipped.
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
        Invoke all implementations concurrently.
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

            if self._enabled_plugins is not None and plugin_id not in self._enabled_plugins:
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
                        hook_name,
                        self._make_proxy(wrapper, hook_name),
                        plugin_name=plugin_id
                    )

                self._loaded_plugins.append(plugin_id)
                if self._enabled_plugins is not None:
                    self._enabled_plugins.add(plugin_id)
                logger.info("Plugin loaded in isolated subprocess: %s", plugin_id)
                return True
            except Exception:
                logger.exception("Failed to load plugin '%s' in isolated subprocess", plugin_id)
                return False
        else:
            # Standalone dynamic load
            try:
                module_name = f"vigile.plugins.{plugin_name}"
                spec = importlib.util.spec_from_file_location(module_name, plugin_path)
                if spec is None or spec.loader is None:
                    raise ImportError(f"Could not load spec for {plugin_path}")

                module = importlib.util.module_from_spec(spec)
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

        # Stop wrapper subprocess if running in sandbox mode
        wrapper = self._wrappers.pop(plugin_id, None)
        if wrapper:
            await wrapper.stop()

        # Unregister all hooks
        for hook_name in list(self._hooks.keys()):
            self.unregister(hook_name, plugin_id)

        # Drain active running tasks
        while self._active_calls.get(plugin_id, 0) > 0:
            logger.debug(
                "Draining plugin '%s' (active calls: %d)", plugin_id, self._active_calls[plugin_id]
            )
            await asyncio.sleep(0.05)

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
        return {hook: [pn for pn, _ in impls] for hook, impls in self._hooks.items()}

    @property
    def loaded_plugins(self) -> list[str]:
        return list(self._loaded_plugins)

    def has_hook(self, hook_name: str) -> bool:
        return bool(self._hooks.get(hook_name))


# Module-level singleton
plugin_manager = PluginManager()
