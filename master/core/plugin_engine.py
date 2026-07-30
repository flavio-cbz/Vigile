"""
Vigile — Plugin Engine v2
Consolidated engine managing plugin discovery, lifecycle, hook dispatching,
and sandbox execution, synchronized directly with the SQLite database.
"""

from __future__ import annotations
import asyncio
import hashlib
import importlib.util
import inspect
import json
import logging
import os
import shutil
import sys
import tempfile
import zipfile
from collections.abc import Callable
from typing import Any, cast

from master.core.plugin_base import PluginBase, PluginContext, RedactingAdapter
from master.core.plugin_lifecycle import PluginLifecycleManager
from master.core.plugin_manifest import PluginManifest

# Resource limits for subprocess isolation (Unix-only; best-effort on other platforms)
try:
    import resource as _resource_mod
except ImportError:
    _resource_mod = None  # type: ignore[assignment]

# Environment variable whitelist for sandboxed subprocesses
_ENV_WHITELIST = frozenset({"PYTHONPATH", "PATH", "HOME", "LANG"})

logger: RedactingAdapter = RedactingAdapter(logging.getLogger(__name__))

# Plugin lifecycle states (referenced by plugin_manager)
STATE_DECOUVERT = "DECOUVERT"
STATE_INSTALLED = "INSTALLED"
STATE_ACTIVE = "ACTIVE"
STATE_DEACTIVATED = "DEACTIVATED"
STATE_UNINSTALL = "UNINSTALL"

DEFAULT_TIMEOUT: float = 30.0

from master.core.plugin_ids import canonical_plugin_id, plugin_file_stem

class HookBus:
    """Manages subscription and dispatching of synchronous and asynchronous hooks."""
    def __init__(self) -> None:
        # hook_name -> [(plugin_name, callable)]
        self._hooks: dict[str, list[tuple[str, Callable]]] = {}

    def register(self, hook_name: str, fn: Callable, *, plugin_name: str = "anonymous") -> None:
        self._hooks.setdefault(hook_name, []).append((plugin_name, fn))

    def unregister(self, hook_name: str, plugin_name: str) -> int:
        if hook_name not in self._hooks:
            return 0
        before = len(self._hooks[hook_name])
        self._hooks[hook_name] = [(pn, fn) for pn, fn in self._hooks[hook_name] if pn != plugin_name]
        removed = before - len(self._hooks[hook_name])
        if not self._hooks[hook_name]:
            del self._hooks[hook_name]
        return removed

    def has_hook(self, hook_name: str) -> bool:
        return hook_name in self._hooks

    def get_hooks(self) -> dict[str, list[str]]:
        return {h: [pn for pn, _ in impls] for h, impls in self._hooks.items()}

    def call(self, hook_name: str, **kwargs: Any) -> list[Any]:
        results: list[Any] = []
        for plugin_name, fn in self._hooks.get(hook_name, []):
            if inspect.iscoroutinefunction(fn):
                logger.warning("Hook '%s' in '%s' is async; skipped in sync call().", hook_name, plugin_name)
                continue
            try:
                res = fn(**kwargs)
                if res is not None:
                    results.append(res)
            except Exception as e:
                logger.exception("Hook '%s' in '%s' raised an exception: %s", hook_name, plugin_name, e)
        return results

    def call_first(self, hook_name: str, **kwargs: Any) -> Any | None:
        for plugin_name, fn in self._hooks.get(hook_name, []):
            if inspect.iscoroutinefunction(fn):
                continue
            try:
                res = fn(**kwargs)
                if res is not None:
                    return res
            except Exception as e:
                logger.exception("Hook '%s' in '%s' raised an exception: %s", hook_name, plugin_name, e)
        return None

    async def _run_async_hook(self, plugin_name: str, fn: Callable, hook_name: str, **kwargs: Any) -> Any:
        try:
            if inspect.iscoroutinefunction(fn):
                return await fn(**kwargs)
            return await asyncio.get_running_loop().run_in_executor(None, lambda: fn(**kwargs))
        except BaseException as exc:
            logger.exception("Async hook '%s' in '%s' raised: %s", hook_name, plugin_name, exc)
            return exc

    async def async_call(self, hook_name: str, **kwargs: Any) -> list[Any]:
        impls = self._hooks.get(hook_name, [])
        if not impls:
            return []
        tasks = []
        for plugin_name, fn in impls:
            tasks.append(asyncio.wait_for(
                self._run_async_hook(plugin_name, fn, hook_name, **kwargs),
                timeout=DEFAULT_TIMEOUT
            ))
        results: list[Any] = []
        for res in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(res, BaseException):
                continue
            if res is not None:
                results.append(res)
        return results

    async def async_call_first(self, hook_name: str, **kwargs: Any) -> Any | None:
        res = await self.async_call(hook_name, **kwargs)
        return res[0] if res else None


class PluginProcessWrapper:
    """Manages the subprocess lifecycle of a sandboxed plugin."""
    def __init__(self, plugin_id: str, plugin_path: str, engine: PluginEngine, env: dict[str, str] | None = None):
        self.plugin_id = plugin_id
        self.plugin_path = plugin_path
        self.engine = engine
        self._env = env
        self.process: asyncio.subprocess.Process | None = None
        self.hooks: list[str] = []
        self.schema: dict[str, Any] = {}
        self._pending_calls: dict[str, asyncio.Future] = {}
        self._stdout_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._init_future: asyncio.Future | None = None

    async def start(self) -> None:
        worker_script = os.path.join(os.path.dirname(__file__), "plugin_worker.py")
        loop = asyncio.get_running_loop()
        self._init_future = loop.create_future()

        # Filter environment to whitelist only — no secrets, no host env leakage
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
        raw_env = self._env if self._env is not None else os.environ
        env = {k: raw_env[k] for k in _ENV_WHITELIST if k in raw_env}
        env.setdefault("PYTHONPATH", project_root)
        if "PATH" not in env:
            env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
        if "HOME" not in env:
            env["HOME"] = "/root"
        if "LANG" not in env:
            env["LANG"] = "C.UTF-8"

        # Build preexec_fn for resource limits (Unix-only)
        preexec_fn = None
        if _resource_mod is not None:
            def _set_limits():
                try:
                    # Max address space: 512 MB
                    _resource_mod.setrlimit(_resource_mod.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
                    # Max CPU time: 30 seconds
                    _resource_mod.setrlimit(_resource_mod.RLIMIT_CPU, (30, 30))
                except Exception:
                    pass
            preexec_fn = _set_limits

        logger.info("Starting isolated plugin process for '%s'...", self.plugin_id)
        self.process = await asyncio.create_subprocess_exec(
            sys.executable,
            worker_script,
            self.plugin_id,
            self.plugin_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            preexec_fn=preexec_fn,
        )
        self._stdout_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())

        try:
            await asyncio.wait_for(self._init_future, timeout=5.0)
        except asyncio.TimeoutError:
            await self.stop()
            raise RuntimeError(f"Subprocess initialization timed out for plugin '{self.plugin_id}'")

    async def stop(self) -> None:
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        if self._stdout_task:
            self._stdout_task.cancel()
        if self._stderr_task:
            self._stderr_task.cancel()

    async def _send(self, msg: dict) -> None:
        if self.process and self.process.stdin:
            self.process.stdin.write((json.dumps(msg) + "\n").encode())
            await self.process.stdin.drain()

    async def _read_stdout(self) -> None:
        while self.process and self.process.stdout:
            line = await self.process.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode().strip())
                msg_type = msg.get("type")
                if msg_type == "init":
                    self.hooks = msg.get("hooks", [])
                    self.schema = msg.get("schema", {})
                    if self._init_future and not self._init_future.done():
                        self._init_future.set_result(True)
                elif msg_type == "response":
                    fut = self._pending_calls.get(msg.get("call_id"))
                    if fut and not fut.done():
                        if msg.get("status") == "success":
                            fut.set_result(msg.get("result"))
                        else:
                            fut.set_exception(RuntimeError(msg.get("error")))
                elif msg_type in ("db_query",):
                    asyncio.create_task(self._handle_db(msg))
            except Exception:
                logger.exception("Error parsing stdout line from plugin worker '%s'", self.plugin_id)

    async def _read_stderr(self) -> None:
        while self.process and self.process.stderr:
            line = await self.process.stderr.readline()
            if not line:
                break
            logger.info("[%s-stderr] %s", self.plugin_id, line.decode().strip())

    async def _handle_db(self, msg: dict) -> None:
        db_call_id = msg.get("db_call_id")
        if not self.engine.db:
            await self._send({"type": "db_result", "db_call_id": db_call_id, "status": "error", "error": "Database not initialized"})
            return
        try:
            if msg["type"] == "db_query":
                cursor = await self.engine.db.execute(msg["sql"], msg.get("params", []))
                rows = [dict(r) for r in await cursor.fetchall()]
                await self._send({
                    "type": "db_result", "db_call_id": db_call_id, "status": "success",
                    "result": {"rowcount": cursor.rowcount, "lastrowid": cursor.lastrowid, "rows": rows}
                })
        except Exception as e:
            await self._send({"type": "db_result", "db_call_id": db_call_id, "status": "error", "error": str(e)})

    async def call_hook(self, hook_name: str, **kwargs: Any) -> Any:
        if not self.process or self.process.returncode is not None:
            await self.start()
        call_id = f"{asyncio.get_running_loop().time()}-{os.urandom(4).hex()}"
        fut = asyncio.get_running_loop().create_future()
        self._pending_calls[call_id] = fut
        kwargs.pop("db", None) # Worker uses DatabaseProxy
        try:
            await self._send({"type": "call_hook", "call_id": call_id, "hook_name": hook_name, "kwargs": kwargs})
            return await fut
        finally:
            self._pending_calls.pop(call_id, None)


class PageRegistry:
    def __init__(self) -> None:
        self._pages: dict[str, list[dict]] = {}

    def register(self, plugin_id: str, pages: list[dict]) -> None:
        self._pages[plugin_id] = list(pages)

    def unregister(self, plugin_id: str) -> None:
        self._pages.pop(plugin_id, None)

    def get_all_pages(self) -> list[dict]:
        result = []
        for pid, pages in self._pages.items():
            for p in pages:
                entry = dict(p)
                entry["plugin_id"] = pid
                route = f"/plugins/{pid}/{p.get('id', '')}"
                if p.get("params"):
                    for param in p["params"]:
                        route += f"/:{param}"
                entry["route"] = route
                result.append(entry)
        return result

    def get_sidebar_pages(self) -> list[dict]:
        return [p for p in self.get_all_pages() if p.get("sidebar")]


class _Lifecycle:
    """Simple plugin lifecycle state tracker.

    Referenced by plugin_manager.py to sync activation/deactivation state.
    """

    def __init__(self) -> None:
        self._states: dict[str, str] = {}

    def get_state(self, plugin_id: str) -> str | None:
        return self._states.get(plugin_id)


class PluginEngine:
    """Consolidated pluggable orchestrator (PluginEngine v2)."""
    def __init__(
        self,
        hook_bus: HookBus | None = None,
        scheduler: Any = None,
        route_registrar: Any = None,
        page_registry: PageRegistry | None = None,
        db_auto: Any = None,
        scanner: Any = None,
        db: Any = None,
        settings: Any = None,
    ):
        self.hook_bus = hook_bus or HookBus()
        self.scheduler = scheduler
        self.route_registrar = route_registrar
        self.page_registry = page_registry or PageRegistry()
        self.db_auto = db_auto
        self.scanner = self # We fold scanner into this class
        self._explicit_db = db
        self._settings = settings
        self._instances: dict[str, PluginBase] = {}
        self._wrappers: dict[str, PluginProcessWrapper] = {}
        self._errors: dict[str, str] = {}
        self._discovered_manifests: dict[str, PluginManifest] = {}
        self._manifest_dirs: dict[str, str] = {}
        self._loaded_plugins: list[str] = []
        self._hooks: dict = self.hook_bus._hooks
        self._sandbox: bool = True
        self.lifecycle: PluginLifecycleManager = PluginLifecycleManager(engine=self)

    @property
    def db(self) -> Any | None:
        if self._explicit_db:
            try:
                if self._explicit_db._connection is not None:
                    return self._explicit_db
            except AttributeError:
                pass
        try:
            from master.db.database import get_db_conn
            conn = get_db_conn()
            if conn and getattr(conn, "_connection", None) is not None:
                return conn
        except (RuntimeError, ImportError):
            pass
        return None

    def set_engine(self, engine: Any) -> None:
        pass

    async def deactivate(self, plugin_id: str) -> None:
        """Deactivate an active plugin (engine-level cleanup).

        Called by PluginManager.unload_plugin() to sync lifecycle state.
        Sub-process cleanup (hook_unregister, route_unmount, wrapper_stop)
        is handled by the caller — this only updates internal state tracking.
        """
        if plugin_id in self._loaded_plugins:
            self._loaded_plugins.remove(plugin_id)
        self._instances.pop(plugin_id, None)
        self._wrappers.pop(plugin_id, None)
        self.lifecycle._set_runtime(plugin_id, "UNLOADED")

    async def initialize(self, db: Any = None, sandbox: bool | None = None) -> None:
        self._explicit_db = db
        if self.db_auto:
            self.db_auto.set_db(self.db)
        if sandbox is not None:
            self._sandbox = sandbox
        # Scan filesystem first to discover all available plugins
        await self.scan()
        if not self.db:
            # No database: load all discovered plugins as active in-memory
            for plugin_id, manifest in self._discovered_manifests.items():
                try:
                    await self._load(plugin_id, manifest)
                except Exception as e:
                    logger.exception("Failed to load plugin '%s' (no db)", plugin_id)
                    self._errors[plugin_id] = str(e)
            return

        try:
            async with self.db.execute("SELECT id, enabled FROM plugins") as cursor:
                rows = await cursor.fetchall()
                db_states = {row[0]: bool(row[1]) for row in rows}
        except Exception:
            db_states = {}

        for plugin_id, manifest in self._discovered_manifests.items():
            # If plugin not in DB, insert as DISCOVERED
            if plugin_id not in db_states:
                await self.db.execute(
                    "INSERT INTO plugins (id, version, enabled, status, config_json) VALUES (?, ?, 1, 'DISCOVERED', '{}')",
                    (plugin_id, manifest.version)
                )
                db_states[plugin_id] = False
            
            # Load active plugins
            if db_states.get(plugin_id):
                try:
                    await self._load(plugin_id, manifest)
                except Exception as e:
                    logger.exception("Failed to load plugin '%s' at startup", plugin_id)
                    self._errors[plugin_id] = str(e)
                    await self.db.execute("UPDATE plugins SET status = 'ERROR' WHERE id = ?", (plugin_id,))
        await self.db.commit()

    async def scan(self, plugins_dir: str | None = None) -> Any:
        dirs_to_scan = []
        if plugins_dir:
            dirs_to_scan.append(plugins_dir)
        else:
            system_dir = "./master/plugins"
            user_dir = getattr(self._settings, "plugins_dir", "./master/plugins") if self._settings else "./master/plugins"
            dirs_to_scan.append(os.path.abspath(system_dir))
            user_abs = os.path.abspath(user_dir)
            if user_abs not in dirs_to_scan:
                dirs_to_scan.append(user_abs)

        discovered: dict[str, PluginManifest] = {}
        self._errors = {}

        for d in dirs_to_scan:
            if not os.path.isdir(d):
                continue
            for entry in sorted(os.listdir(d)):
                full_path = os.path.join(d, entry)
                if os.path.isdir(full_path):
                    manifest_path = os.path.join(full_path, "manifest.json")
                    if os.path.isfile(manifest_path):
                        try:
                            with open(manifest_path, encoding="utf-8") as f:
                                data = json.load(f)
                            manifest = PluginManifest(**data)
                            discovered[manifest.id] = manifest
                            self._manifest_dirs[manifest.id] = d
                        except Exception as e:
                            logger.error("Failed to parse manifest for plugin '%s': %s", entry, e)
                            self._errors[entry] = str(e)
                elif os.path.isfile(full_path) and entry.endswith(".py") and not entry.startswith("__"):
                    pid = entry[:-3]
                    # Scan passif: no exec_module — only read manifest.json if present,
                    # otherwise create a synthetic manifest from file metadata.
                    manifest_path_py = full_path + ".manifest.json"
                    dir_manifest = os.path.join(d, pid, "manifest.json")
                    manifest_data = None
                    if os.path.isfile(manifest_path_py):
                        try:
                            with open(manifest_path_py, encoding="utf-8") as mf:
                                manifest_data = json.load(mf)
                        except Exception as e:
                            logger.error("Failed to parse sidecar manifest for '%s': %s", entry, e)
                    elif os.path.isfile(dir_manifest):
                        try:
                            with open(dir_manifest, encoding="utf-8") as mf:
                                manifest_data = json.load(mf)
                        except Exception as e:
                            logger.error("Failed to parse manifest for '%s': %s", entry, e)

                    if manifest_data:
                        try:
                            manifest = PluginManifest(**manifest_data)
                            discovered[manifest.id] = manifest
                            self._manifest_dirs[manifest.id] = d
                        except Exception as e:
                            logger.error("Invalid manifest for '%s': %s", entry, e)
                            self._errors[entry] = str(e)
                    else:
                        # Synthetic manifest — no code executed
                        discovered[pid] = PluginManifest(
                            id=pid,
                            name=pid.replace("_", " ").title(),
                            version="1.0.0",
                            description="Custom plugin package.",
                            category="System",
                        )
                        self._manifest_dirs[pid] = d
                elif os.path.isfile(full_path) and entry.endswith(".zip"):
                    await self._install_zip_plugin(full_path, d, discovered)
        self._discovered_manifests = discovered
        return self

    async def _install_zip_plugin(
        self, zip_path: str, scan_dir: str, discovered: dict[str, PluginManifest]
    ) -> None:
        """Validate a ZIP archive, extract it, and register the plugin.

        Performs SHA-256 hash validation (if .sha256 sidecar exists),
        checks ``min_master_version`` compatibility, validates the
        manifest against the PluginManifest schema, extracts to a temp
        directory, and atomically renames into the scan directory.

        Unsigned archives are registered as LOCAL_UNVERIFIED.
        """
        logger.info("Processing ZIP plugin archive: %s", zip_path)
        basename = os.path.splitext(os.path.basename(zip_path))[0]

        # 1. SHA-256 hash validation (sidecar .sha256 file)
        sha256_path = zip_path + ".sha256"
        if os.path.isfile(sha256_path):
            try:
                with open(sha256_path, encoding="utf-8") as sf:
                    expected_hash = sf.read().strip().split()[0].lower()
                with open(zip_path, "rb") as zf:
                    actual_hash = hashlib.sha256(zf.read()).hexdigest()
                if expected_hash != actual_hash:
                    logger.error(
                        "SHA-256 mismatch for '%s': expected %s, got %s",
                        zip_path, expected_hash, actual_hash,
                    )
                    self._errors[basename] = "SHA-256 hash mismatch"
                    return
                logger.info("SHA-256 hash verified for '%s'", zip_path)
            except Exception as e:
                logger.error("Failed to verify SHA-256 for '%s': %s", zip_path, e)
                self._errors[basename] = f"SHA-256 verification error: {e}"
                return
        else:
            logger.warning(
                "No .sha256 sidecar for '%s' — marking as LOCAL_UNVERIFIED",
                zip_path,
            )

        # 2. Validate manifest inside the archive
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # Check manifest.json exists
                manifest_members = [m for m in zf.namelist() if m.endswith("manifest.json")]
                if not manifest_members:
                    logger.error("No manifest.json found in ZIP '%s'", zip_path)
                    self._errors[basename] = "Missing manifest.json in archive"
                    return

                # Use the first (or only) manifest.json
                manifest_rel_path = manifest_members[0]
                with zf.open(manifest_rel_path) as mf:
                    manifest_data = json.loads(mf.read().decode("utf-8"))
                manifest = PluginManifest(**manifest_data)

                # 3. API version compatibility check
                expected_master = getattr(self._settings, "version", None)
                if manifest.min_master_version and expected_master:
                    from packaging.version import Version
                    if Version(expected_master) < Version(manifest.min_master_version):
                        logger.error(
                            "Plugin '%s' requires master >= %s, current is %s",
                            manifest.id, manifest.min_master_version, expected_master,
                        )
                        self._errors[basename] = (
                            f"Requires master >= {manifest.min_master_version}"
                        )
                        return

                # 4. Extract to temp directory
                extract_target = os.path.join(scan_dir, manifest.id)
                if os.path.exists(extract_target):
                    logger.error(
                        "Plugin directory '%s' already exists for '%s'",
                        extract_target, manifest.id,
                    )
                    self._errors[manifest.id] = "Target directory already exists"
                    return

                tmp_dir = tempfile.mkdtemp(prefix=f"vigile_zip_{manifest.id}_")
                try:
                    zf.extractall(tmp_dir)
                    # Determine the top-level directory inside the archive
                    extracted_items = os.listdir(tmp_dir)
                    if len(extracted_items) == 1 and os.path.isdir(
                        os.path.join(tmp_dir, extracted_items[0])
                    ):
                        src = os.path.join(tmp_dir, extracted_items[0])
                    else:
                        src = tmp_dir

                    # Atomic rename
                    os.rename(src, extract_target)
                    logger.info(
                        "ZIP plugin '%s' extracted and installed at '%s'",
                        manifest.id, extract_target,
                    )

                    discovered[manifest.id] = manifest
                    self._manifest_dirs[manifest.id] = scan_dir
                except OSError as exc:
                    logger.error(
                        "Failed to extract/rename ZIP '%s': %s", zip_path, exc,
                    )
                    self._errors[manifest.id] = f"Extraction error: {exc}"
                    # Cleanup temp dir on failure
                    if os.path.exists(tmp_dir):
                        shutil.rmtree(tmp_dir, ignore_errors=True)
                    return

        except (zipfile.BadZipFile, json.JSONDecodeError, Exception) as e:
            logger.error("Failed to process ZIP plugin '%s': %s", zip_path, e)
            self._errors[basename] = f"Invalid ZIP: {e}"

    def get_manifest(self, plugin_id: str) -> PluginManifest | None:
        return self._discovered_manifests.get(plugin_id)

    def get_all_manifests(self) -> dict[str, PluginManifest]:
        return dict(self._discovered_manifests)

    async def _load(self, plugin_id: str, manifest: PluginManifest, plugins_dir: str | None = None) -> None:
        # Load plugin configuration
        config = {}
        if self.db:
            try:
                async with self.db.execute("SELECT config_json FROM plugins WHERE id = ?", (plugin_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row and row[0]:
                        config = json.loads(row[0])
            except Exception:
                pass

        # Check sandbox execution
        p_dir = plugins_dir or self._manifest_dirs.get(plugin_id) or (getattr(self._settings, "plugins_dir", "master/plugins") if self._settings else "master/plugins")
        is_package = os.path.exists(os.path.join(p_dir, plugin_id, "__init__.py"))
        use_sandbox = self._sandbox and is_package and not manifest.trusted and plugin_id not in ("metrics", "systemd", "docker")
        
        # Setup tables if database schema defined in manifest
        if manifest.database and self.db_auto:
            db_specs = {t: [col.model_dump() for col in cols] for t, cols in manifest.database.items()}
            await self.db_auto.create_tables(plugin_id, db_specs)


        if use_sandbox:
            plugin_path = os.path.join(p_dir, plugin_id, "__init__.py")
            if not os.path.exists(plugin_path):
                plugin_path = os.path.join(p_dir, f"{plugin_id}.py")
            wrapper = PluginProcessWrapper(plugin_id, plugin_path, self)
            await wrapper.start()
            self._wrappers[plugin_id] = wrapper
            
            # Hook routing via wrapper call proxies
            for hook_name in wrapper.hooks:
                self.hook_bus.register(hook_name, self._make_wrapper_proxy(wrapper, hook_name), plugin_name=plugin_id)
            
            # Route registration is driven by route descriptions in manifest.json
            if manifest.routes and self.route_registrar:
                self.route_registrar.mount(plugin_id, [r.model_dump() for r in manifest.routes], wrapper)
        else:
            module_name = f"master.plugins.{plugin_id}"
            plugin_dir = os.path.join(p_dir, plugin_id)
            init_file = os.path.join(plugin_dir, "__init__.py")
            if not os.path.exists(init_file):
                init_file = os.path.join(p_dir, f"{plugin_id}.py")
            spec = importlib.util.spec_from_file_location(module_name, init_file)
            if not spec or not spec.loader:
                raise ImportError(f"Could not load spec for {init_file}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Discover PluginBase subclass
            plugin_class = PluginBase._decorated_registry.get(plugin_id)
            if plugin_class:
                ctx = PluginContext(plugin_id=plugin_id, config=config, db=self.db, hook_bus=self.hook_bus)
                instance = plugin_class(ctx)
                self._instances[plugin_id] = instance

                # Register Hooks
                for hspec in instance.hooks:
                    fn = getattr(instance, hspec["method_name"], None)
                    if fn:
                        self.hook_bus.register(hspec["verb"], fn, plugin_name=plugin_id)
                
                # Start Scheduled Tasks
                if instance.scheduled and self.scheduler:
                    self.scheduler.start(plugin_id, instance.scheduled, instance)

                # Mount dynamic HTTP routes
                if instance.routes and self.route_registrar:
                    self.route_registrar.mount(plugin_id, instance.routes, instance)
            elif hasattr(module, "register"):
                module.register(self)

        # Pages registration
        if manifest.pages:
            self.page_registry.register(plugin_id, [p.model_dump() for p in manifest.pages])
        
        self._errors.pop(plugin_id, None)
        if self.db:
            await self.db.execute("UPDATE plugins SET status = 'ACTIVE', enabled = 1 WHERE id = ?", (plugin_id,))

    def _make_wrapper_proxy(self, wrapper: PluginProcessWrapper, hook_name: str) -> Callable:
        async def proxy(**kwargs: Any) -> Any:
            return await wrapper.call_hook(hook_name, **kwargs)
        return proxy

    async def load_plugin(self, plugin_id: str, plugins_dir: str | None = None) -> bool:
        if plugin_id in self.loaded_plugins:
            return False
        manifest = self.get_manifest(plugin_id)
        if not manifest:
            await self.scan(plugins_dir)
            manifest = self.get_manifest(plugin_id)
        if not manifest:
            logger.error("Cannot load plugin '%s': manifest not found", plugin_id)
            return False
        try:
            await self._load(plugin_id, manifest, plugins_dir)
            if plugin_id not in self._instances and plugin_id not in self._wrappers:
                if plugin_id not in self._loaded_plugins:
                    self._loaded_plugins.append(plugin_id)
            if self.db:
                await self.db.commit()
            return True
        except Exception as e:
            logger.exception("Failed to load plugin '%s'", plugin_id)
            self._errors[plugin_id] = str(e)
            try:
                await self.unload_plugin(plugin_id)
            except Exception:
                pass
            if self.db:
                try:
                    await self.db.execute("UPDATE plugins SET status = 'ERROR', enabled = 1 WHERE id = ?", (plugin_id,))
                    await self.db.commit()
                except Exception:
                    pass
            return False

    async def unload_plugin(self, plugin_id: str) -> None:
        logger.info("Unloading plugin '%s'...", plugin_id)
        # Unsubscribe Hooks
        for hook_name in list(self.hook_bus.get_hooks().keys()):
            self.hook_bus.unregister(hook_name, plugin_id)

        # Stop Scheduled Tasks
        if self.scheduler:
            await self.scheduler.stop(plugin_id)

        # Unmount routes
        if self.route_registrar:
            self.route_registrar.unmount(plugin_id)

        # Unregister pages
        self.page_registry.unregister(plugin_id)

        # Stop sandbox process wrapper if any
        wrapper = self._wrappers.pop(plugin_id, None)
        if wrapper:
            await wrapper.stop()

        self._instances.pop(plugin_id, None)
        self._errors.pop(plugin_id, None)

        # Clean up sys.modules to prevent stale module references on reload
        module_name = f"master.plugins.{plugin_id}"
        sys.modules.pop(module_name, None)

        if plugin_id in self._loaded_plugins:
            self._loaded_plugins.remove(plugin_id)

        if self.db:
            await self.db.execute("UPDATE plugins SET status = 'DISABLED', enabled = 0 WHERE id = ?", (plugin_id,))
            await self.db.commit()
        logger.info("Plugin '%s' unloaded successfully.", plugin_id)

    async def uninstall(self, plugin_id: str) -> None:
        manifest = self.get_manifest(plugin_id)
        await self.unload_plugin(plugin_id)
        if manifest and manifest.database and self.db_auto:
            await self.db_auto.drop_tables(plugin_id, manifest.database)
        if self.db:
            await self.db.execute("DELETE FROM plugins WHERE id = ?", (plugin_id,))
            await self.db.commit()

    @property
    def loaded_plugins(self) -> list[str]:
        seen = set(self._instances.keys()) | set(self._wrappers.keys())
        legacy = [pid for pid in self._loaded_plugins if pid not in seen]
        return list(seen) + legacy

    async def load_plugins_from_dir(self, directory: str) -> list[str]:
        await self.scan(directory)
        loaded = []
        for plugin_id in self._discovered_manifests:
            enabled = True
            if self.db:
                try:
                    async with self.db.execute("SELECT enabled FROM plugins WHERE id = ?", (plugin_id,)) as cursor:
                        row = await cursor.fetchone()
                        if row:
                            enabled = bool(row[0])
                except Exception:
                    pass
            if enabled:
                if await self.load_plugin(plugin_id, directory):
                    loaded.append(plugin_id)
        return loaded

    def get_hooks(self) -> dict[str, list[str]]:
        return self.hook_bus.get_hooks()

    def has_hook(self, hook_name: str) -> bool:
        return self.hook_bus.unregister(hook_name, "") != 0 or hook_name in self.hook_bus.get_hooks()

    def register(self, hook_name: str, fn: Callable, *, plugin_name: str = "anonymous") -> None:
        self.hook_bus.register(hook_name, fn, plugin_name=plugin_name)

    def unregister(self, hook_name: str, plugin_name: str) -> int:
        return self.hook_bus.unregister(hook_name, plugin_name)

    def call(self, hook_name: str, **kwargs: Any) -> list[Any]:
        return self.hook_bus.call(hook_name, **kwargs)

    def call_first(self, hook_name: str, **kwargs: Any) -> Any | None:
        return self.hook_bus.call_first(hook_name, **kwargs)

    async def async_call(self, hook_name: str, **kwargs: Any) -> list[Any]:
        return await self.hook_bus.async_call(hook_name, **kwargs)

    async def async_call_first(self, hook_name: str, **kwargs: Any) -> Any | None:
        return await self.hook_bus.async_call_first(hook_name, **kwargs)

    async def shutdown(self) -> None:
        for plugin_id in list(self._wrappers.keys()) + list(self._instances.keys()):
            await self.unload_plugin(plugin_id)
        if self.scheduler:
            await self.scheduler.shutdown()

plugin_engine = PluginEngine()
plugin_manager = plugin_engine
