"""
Vigile — Plugin Engine v3
=========================
Responsabilités séparées :

  PluginRegistry   → découverte filesystem + lecture manifests (zéro import de code)
  HookBus          → souscription et dispatch sync/async des hooks
  PageRegistry     → pages déclarées par les plugins pour la sidebar
  PluginProcessWrapper → subprocess sandboxé (inchangé)
  PluginEngine     → orchestration : lifecycle, chargement, déchargement

Principes :
  - Le loader (class_based vs sandbox) est décidé de façon DÉCLARATIVE via
    manifest.trusted ou manifest.loader — jamais par probe d'import.
  - Une seule source de vérité : _states dict[str, _PluginState].
  - loaded_plugins est une property pure, sans fusion de structures.
  - has_hook ne mute jamais le bus.
  - Un asyncio.Lock par plugin_id empêche les double-loads concurrents.
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
from dataclasses import dataclass, field
from typing import Any, Literal

from master.core.hook_bus import HookBus
from master.core.plugin_base import PluginBase, PluginContext, RedactingAdapter
from master.core.plugin_lifecycle import PluginLifecycleManager
from master.core.plugin_manifest import PluginManifest
from master.core.plugin_ids import canonical_plugin_id, plugin_file_stem

try:
    import resource as _resource_mod
except ImportError:
    _resource_mod = None  # type: ignore[assignment]

_ENV_WHITELIST = frozenset({"PYTHONPATH", "PATH", "HOME", "LANG"})

logger: RedactingAdapter = RedactingAdapter(logging.getLogger(__name__))

# Plugin lifecycle state constants (backward-compat avec plugin_manager)
STATE_DECOUVERT  = "DECOUVERT"
STATE_INSTALLED  = "INSTALLED"
STATE_ACTIVE     = "ACTIVE"
STATE_DEACTIVATED = "DEACTIVATED"
STATE_UNINSTALL  = "UNINSTALL"

_LoaderKind = Literal["class_based", "sandbox", "legacy"]


# ---------------------------------------------------------------------------
# Internal state record
# ---------------------------------------------------------------------------

@dataclass
class _PluginState:
    plugin_id: str
    status: Literal["active", "disabled", "error"]
    loader: _LoaderKind = "class_based"
    error: str | None = None


# ---------------------------------------------------------------------------
# PluginRegistry — filesystem scan, zero code execution
# ---------------------------------------------------------------------------

class PluginRegistry:
    """Découverte filesystem des plugins. Ne charge aucun module Python.

    Deux façons de déclarer qu'un plugin doit utiliser le loader class_based
    plutôt que le sandbox subprocess :
      1. manifest.trusted = true
      2. manifest.loader  = "class_based"  (explicite)

    Tout plugin sans manifest explicite obtient un manifest synthétique
    avec loader="legacy" (chemin register(pm)).
    """

    def __init__(self) -> None:
        self._manifests: dict[str, PluginManifest] = {}
        self._manifest_dirs: dict[str, str] = {}
        self._errors: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_manifest(self, plugin_id: str) -> PluginManifest | None:
        return self._manifests.get(plugin_id)

    def get_all_manifests(self) -> dict[str, PluginManifest]:
        return dict(self._manifests)

    def get_plugin_dir(self, plugin_id: str) -> str | None:
        return self._manifest_dirs.get(plugin_id)

    def get_errors(self) -> dict[str, str]:
        return dict(self._errors)

    def resolve_loader(self, manifest: PluginManifest) -> _LoaderKind:
        """Retourne le loader à utiliser — décision purement déclarative."""
        if manifest.trusted:
            return "class_based"
        loader_field = getattr(manifest, "loader", None)
        if loader_field == "class_based":
            return "class_based"
        if loader_field == "legacy":
            return "legacy"
        # Plugins dossier sans trusted=true → sandbox par défaut
        return "sandbox"

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------

    async def scan(self, *dirs: str) -> None:
        """Scan un ou plusieurs répertoires. Lecture seule — aucun exec_module."""
        discovered: dict[str, PluginManifest] = {}
        self._errors = {}

        for d in dirs:
            if not os.path.isdir(d):
                continue
            for entry in sorted(os.listdir(d)):
                full_path = os.path.join(d, entry)

                if os.path.isdir(full_path):
                    self._scan_package_dir(full_path, entry, d, discovered)

                elif full_path.endswith(".py") and not entry.startswith("__"):
                    self._scan_py_file(full_path, entry, d, discovered)

                elif full_path.endswith(".zip"):
                    await self._install_zip_plugin(full_path, d, discovered)

        self._manifests = discovered

    def _scan_package_dir(
        self,
        full_path: str,
        entry: str,
        scan_dir: str,
        discovered: dict[str, PluginManifest],
    ) -> None:
        manifest_path = os.path.join(full_path, "manifest.json")
        if not os.path.isfile(manifest_path):
            return
        try:
            with open(manifest_path, encoding="utf-8") as f:
                data = json.load(f)
            manifest = PluginManifest(**data)
            discovered[manifest.id] = manifest
            self._manifest_dirs[manifest.id] = scan_dir
        except Exception as e:
            logger.error("Manifest invalide pour le plugin '%s': %s", entry, e)
            self._errors[entry] = str(e)

    def _scan_py_file(
        self,
        full_path: str,
        entry: str,
        scan_dir: str,
        discovered: dict[str, PluginManifest],
    ) -> None:
        pid = entry[:-3]
        manifest_data: dict | None = None

        # Cherche un manifest sidecar (.py.manifest.json) ou dans un sous-dossier
        for candidate in (full_path + ".manifest.json", os.path.join(scan_dir, pid, "manifest.json")):
            if os.path.isfile(candidate):
                try:
                    with open(candidate, encoding="utf-8") as mf:
                        manifest_data = json.load(mf)
                    break
                except Exception as e:
                    logger.error("Manifest sidecar invalide pour '%s': %s", entry, e)

        if manifest_data:
            try:
                manifest = PluginManifest(**manifest_data)
                discovered[manifest.id] = manifest
                self._manifest_dirs[manifest.id] = scan_dir
                return
            except Exception as e:
                logger.error("Manifest invalide pour '%s': %s", entry, e)
                self._errors[pid] = str(e)

        # Manifest synthétique — pas d'import, loader=legacy pour .py sans manifest
        discovered[pid] = PluginManifest(
            id=pid,
            name=pid.replace("_", " ").title(),
            version="1.0.0",
            description="Plugin Python (format legacy).",
            category="System",
            loader="legacy",    # type: ignore[call-arg]
        )
        self._manifest_dirs[pid] = scan_dir

    async def _install_zip_plugin(
        self, zip_path: str, scan_dir: str, discovered: dict[str, PluginManifest]
    ) -> None:
        basename = os.path.splitext(os.path.basename(zip_path))[0]

        sha256_path = zip_path + ".sha256"
        if os.path.isfile(sha256_path):
            try:
                with open(sha256_path, encoding="utf-8") as sf:
                    expected = sf.read().strip().split()[0].lower()
                with open(zip_path, "rb") as zf:
                    actual = hashlib.sha256(zf.read()).hexdigest()
                if expected != actual:
                    logger.error("SHA-256 mismatch pour '%s'", zip_path)
                    self._errors[basename] = "SHA-256 hash mismatch"
                    return
            except Exception as e:
                self._errors[basename] = f"SHA-256 verification error: {e}"
                return
        else:
            logger.warning("Pas de .sha256 pour '%s' — LOCAL_UNVERIFIED", zip_path)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                members = [m for m in zf.namelist() if m.endswith("manifest.json")]
                if not members:
                    self._errors[basename] = "manifest.json manquant dans l'archive"
                    return
                with zf.open(members[0]) as mf:
                    manifest_data = json.loads(mf.read().decode("utf-8"))
                manifest = PluginManifest(**manifest_data)

                extract_target = os.path.join(scan_dir, manifest.id)
                if os.path.exists(extract_target):
                    self._errors[manifest.id] = "Répertoire cible existe déjà"
                    return

                tmp_dir = tempfile.mkdtemp(prefix=f"vigile_zip_{manifest.id}_")
                try:
                    zf.extractall(tmp_dir)
                    items = os.listdir(tmp_dir)
                    src = os.path.join(tmp_dir, items[0]) if len(items) == 1 and os.path.isdir(os.path.join(tmp_dir, items[0])) else tmp_dir
                    os.rename(src, extract_target)
                    discovered[manifest.id] = manifest
                    self._manifest_dirs[manifest.id] = scan_dir
                    logger.info("ZIP plugin '%s' extrait vers '%s'", manifest.id, extract_target)
                except OSError as exc:
                    self._errors[manifest.id] = f"Extraction error: {exc}"
                    shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception as e:
            self._errors[basename] = f"ZIP invalide: {e}"


# ---------------------------------------------------------------------------
# PageRegistry
# ---------------------------------------------------------------------------

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
                for param in p.get("params", []):
                    route += f"/:{param}"
                entry["route"] = route
                result.append(entry)
        return result

    def get_sidebar_pages(self) -> list[dict]:
        return [p for p in self.get_all_pages() if p.get("sidebar")]


# ---------------------------------------------------------------------------
# PluginProcessWrapper (sandbox subprocess — inchangé fonctionnellement)
# ---------------------------------------------------------------------------

class PluginProcessWrapper:
    """Gestion du subprocess sandboxé d'un plugin."""

    def __init__(self, plugin_id: str, plugin_path: str, engine: "PluginEngine", env: dict[str, str] | None = None):
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

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
        raw_env = self._env if self._env is not None else os.environ
        env = {k: raw_env[k] for k in _ENV_WHITELIST if k in raw_env}
        env.setdefault("PYTHONPATH", project_root)
        env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
        env.setdefault("HOME", "/root")
        env.setdefault("LANG", "C.UTF-8")

        preexec_fn = None
        if _resource_mod is not None:
            def _set_limits():
                try:
                    _resource_mod.setrlimit(_resource_mod.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
                    _resource_mod.setrlimit(_resource_mod.RLIMIT_CPU, (30, 30))
                except Exception:
                    pass
            preexec_fn = _set_limits

        logger.info("Démarrage du subprocess sandboxé pour '%s'...", self.plugin_id)
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
            raise RuntimeError(f"Timeout d'initialisation du subprocess pour '{self.plugin_id}'")

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
        for task in (self._stdout_task, self._stderr_task):
            if task:
                task.cancel()

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
                mtype = msg.get("type")
                if mtype == "init":
                    self.hooks = msg.get("hooks", [])
                    self.schema = msg.get("schema", {})
                    if self._init_future and not self._init_future.done():
                        self._init_future.set_result(True)
                elif mtype == "response":
                    fut = self._pending_calls.get(msg.get("call_id"))
                    if fut and not fut.done():
                        if msg.get("status") == "success":
                            fut.set_result(msg.get("result"))
                        else:
                            fut.set_exception(RuntimeError(msg.get("error")))
                elif mtype == "db_query":
                    asyncio.create_task(self._handle_db(msg))
            except Exception:
                logger.exception("Erreur de parsing stdout du worker '%s'", self.plugin_id)

    async def _read_stderr(self) -> None:
        while self.process and self.process.stderr:
            line = await self.process.stderr.readline()
            if not line:
                break
            logger.info("[%s-stderr] %s", self.plugin_id, line.decode().strip())

    async def _handle_db(self, msg: dict) -> None:
        db_call_id = msg.get("db_call_id")
        if not self.engine.db:
            await self._send({"type": "db_result", "db_call_id": db_call_id, "status": "error", "error": "DB non initialisée"})
            return
        try:
            cursor = await self.engine.db.execute(msg["sql"], msg.get("params", []))
            rows = [dict(r) for r in await cursor.fetchall()]
            await self._send({
                "type": "db_result", "db_call_id": db_call_id, "status": "success",
                "result": {"rowcount": cursor.rowcount, "lastrowid": cursor.lastrowid, "rows": rows},
            })
        except Exception as e:
            await self._send({"type": "db_result", "db_call_id": db_call_id, "status": "error", "error": str(e)})

    async def call_hook(self, hook_name: str, **kwargs: Any) -> Any:
        if not self.process or self.process.returncode is not None:
            await self.start()
        call_id = f"{asyncio.get_running_loop().time()}-{os.urandom(4).hex()}"
        fut = asyncio.get_running_loop().create_future()
        self._pending_calls[call_id] = fut
        kwargs.pop("db", None)
        try:
            await self._send({"type": "call_hook", "call_id": call_id, "hook_name": hook_name, "kwargs": kwargs})
            return await fut
        finally:
            self._pending_calls.pop(call_id, None)


# ---------------------------------------------------------------------------
# _Lifecycle (backward-compat avec plugin_manager.py)
# ---------------------------------------------------------------------------

class _Lifecycle:
    def __init__(self) -> None:
        self._states: dict[str, str] = {}

    def get_state(self, plugin_id: str) -> str | None:
        return self._states.get(plugin_id)


# ---------------------------------------------------------------------------
# PluginEngine
# ---------------------------------------------------------------------------

class PluginEngine:
    """Orchestrateur de plugins v3.

    Délègue :
      - La découverte filesystem   → PluginRegistry
      - Le dispatch des hooks      → HookBus
      - Les pages sidebar          → PageRegistry
      - Le subprocess sandbox      → PluginProcessWrapper

    État interne :
      - _states : dict[str, _PluginState]  — source de vérité unique
      - _instances : dict[str, PluginBase] — instances class_based actives
      - _wrappers  : dict[str, PluginProcessWrapper] — wrappers sandbox actifs
      - _locks     : dict[str, asyncio.Lock] — empêche le double-load concurrent
    """

    def __init__(
        self,
        hook_bus: HookBus | None = None,
        scheduler: Any = None,
        route_registrar: Any = None,
        page_registry: PageRegistry | None = None,
        db_auto: Any = None,
        scanner: Any = None,   # ignoré — le registry interne est utilisé
        db: Any = None,
        settings: Any = None,
    ):
        self.hook_bus = hook_bus or HookBus()
        self.scheduler = scheduler
        self.route_registrar = route_registrar
        self.page_registry = page_registry or PageRegistry()
        self.db_auto = db_auto
        self._explicit_db = db
        self._settings = settings

        self._registry = PluginRegistry()
        self._instances: dict[str, PluginBase] = {}
        self._wrappers: dict[str, PluginProcessWrapper] = {}
        self._states: dict[str, _PluginState] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._errors: dict[str, str] = {}  # backward-compat

        # Exposé pour backward-compat avec admin.py (_hooks, _sandbox, _wrappers)
        self._hooks: dict = self.hook_bus._hooks
        self._sandbox: bool = True

        self.lifecycle: PluginLifecycleManager = PluginLifecycleManager(engine=self)

        # scanner = self pour backward-compat (admin.py: active_pm.scanner.get_manifest)
        self.scanner = self

    # ------------------------------------------------------------------
    # DB property — résolution paresseuse
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # PluginRegistry proxy (backward-compat : active_pm.scanner.get_manifest)
    # ------------------------------------------------------------------

    def get_manifest(self, plugin_id: str) -> PluginManifest | None:
        return self._registry.get_manifest(plugin_id)

    def get_all_manifests(self) -> dict[str, PluginManifest]:
        return self._registry.get_all_manifests()

    def is_plugin_loaded(self, plugin_id: str) -> bool:
        """Indique si un plugin est actuellement chargé et actif dans le runtime."""
        for candidate in {plugin_id, canonical_plugin_id(plugin_id), plugin_file_stem(plugin_id)}:
            if candidate in self._instances or candidate in self._wrappers:
                return True
        return False

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    async def initialize(self, db: Any = None, sandbox: bool | None = None) -> None:
        self._explicit_db = db
        if self.db_auto:
            self.db_auto.set_db(self.db)
        if sandbox is not None:
            self._sandbox = sandbox

        await self.scan()

        if not self.db:
            for plugin_id, manifest in self._registry.get_all_manifests().items():
                try:
                    await self._load(plugin_id, manifest)
                except Exception as e:
                    logger.exception("Échec du chargement de '%s' (sans DB)", plugin_id)
                    self._set_state(plugin_id, "error", error=str(e))
            return

        try:
            async with self.db.execute("SELECT id, enabled FROM plugins") as cursor:
                rows = await cursor.fetchall()
                db_states = {row[0]: bool(row[1]) for row in rows}
        except Exception:
            db_states = {}

        for plugin_id, manifest in self._registry.get_all_manifests().items():
            if plugin_id not in db_states:
                await self.db.execute(
                    "INSERT INTO plugins (id, version, enabled, status, config_json) VALUES (?, ?, 1, 'DISCOVERED', '{}')",
                    (plugin_id, manifest.version),
                )
                db_states[plugin_id] = True

            if db_states.get(plugin_id):
                try:
                    await self._load(plugin_id, manifest)
                except Exception as e:
                    logger.exception("Échec du chargement de '%s' au démarrage", plugin_id)
                    self._set_state(plugin_id, "error", error=str(e))
                    await self.db.execute("UPDATE plugins SET status = 'ERROR' WHERE id = ?", (plugin_id,))

        await self.db.commit()

    async def scan(self, plugins_dir: str | None = None) -> "PluginEngine":
        dirs: list[str] = []
        if plugins_dir:
            dirs.append(plugins_dir)
        else:
            system_dir = os.path.abspath("./master/plugins")
            user_dir = os.path.abspath(
                getattr(self._settings, "plugins_dir", "./master/plugins") if self._settings else "./master/plugins"
            )
            dirs.append(system_dir)
            if user_dir not in dirs:
                dirs.append(user_dir)

        await self._registry.scan(*dirs)
        self._errors = self._registry.get_errors()
        return self

    # ------------------------------------------------------------------
    # Chargement interne
    # ------------------------------------------------------------------

    def _get_lock(self, plugin_id: str) -> asyncio.Lock:
        if plugin_id not in self._locks:
            self._locks[plugin_id] = asyncio.Lock()
        return self._locks[plugin_id]

    def _set_state(
        self,
        plugin_id: str,
        status: Literal["active", "disabled", "error"],
        loader: _LoaderKind = "class_based",
        error: str | None = None,
    ) -> None:
        self._states[plugin_id] = _PluginState(plugin_id=plugin_id, status=status, loader=loader, error=error)
        if error:
            self._errors[plugin_id] = error
        elif plugin_id in self._errors:
            del self._errors[plugin_id]

    async def _load(self, plugin_id: str, manifest: PluginManifest, plugins_dir: str | None = None) -> None:
        config: dict = {}
        if self.db:
            try:
                async with self.db.execute("SELECT config_json FROM plugins WHERE id = ?", (plugin_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row and row[0]:
                        config = json.loads(row[0])
            except Exception:
                pass

        # Resolve plugin directory — single source of truth
        p_dir = (
            plugins_dir
            or self._registry.get_plugin_dir(plugin_id)
            or (getattr(self._settings, "plugins_dir", "master/plugins") if self._settings else "master/plugins")
        )
        plugin_dir = os.path.join(p_dir, plugin_id)
        init_file = os.path.join(plugin_dir, "__init__.py")
        if not os.path.exists(init_file):
            init_file = os.path.join(p_dir, f"{plugin_id}.py")

        def _is_class_based(pid: str, target_file: str) -> bool:
            if pid in PluginBase._decorated_registry:
                return True
            if getattr(manifest, "loader", None) == "class_based":
                return True
            return False

        is_package = os.path.exists(os.path.join(p_dir, plugin_id, "__init__.py"))
        use_sandbox = (
            self._sandbox
            and is_package
            and not manifest.trusted
            and not _is_class_based(plugin_id, init_file)
        )

        loader_kind = self._registry.resolve_loader(manifest)

        # Surcharge : si sandbox global désactivé, pas de subprocess
        if not self._sandbox and loader_kind == "sandbox":
            loader_kind = "class_based"

        if manifest.database and self.db_auto:
            db_specs = {t: [col.model_dump() for col in cols] for t, cols in manifest.database.items()}
            await self.db_auto.create_tables(plugin_id, db_specs)

        if loader_kind == "sandbox":
            await self._load_sandbox(plugin_id, manifest, p_dir)
        else:
            await self._load_inprocess(plugin_id, manifest, p_dir, config, loader_kind)

        if manifest.pages:
            self.page_registry.register(plugin_id, [p.model_dump() for p in manifest.pages])

        self._set_state(plugin_id, "active", loader=loader_kind)
        if self.db:
            await self.db.execute("UPDATE plugins SET status = 'ACTIVE', enabled = 1 WHERE id = ?", (plugin_id,))

    async def _load_sandbox(self, plugin_id: str, manifest: PluginManifest, p_dir: str) -> None:
        plugin_path = os.path.join(p_dir, plugin_id, "__init__.py")
        if not os.path.exists(plugin_path):
            plugin_path = os.path.join(p_dir, f"{plugin_id}.py")
        wrapper = PluginProcessWrapper(plugin_id, plugin_path, self)
        await wrapper.start()
        self._wrappers[plugin_id] = wrapper
        for hook_name in wrapper.hooks:
            self.hook_bus.register(hook_name, self._make_wrapper_proxy(wrapper, hook_name), plugin_name=plugin_id)
        if manifest.routes and self.route_registrar:
            self.route_registrar.mount(plugin_id, [r.model_dump() for r in manifest.routes], wrapper)

    async def _load_inprocess(
        self, plugin_id: str, manifest: PluginManifest, p_dir: str, config: dict, loader_kind: _LoaderKind
    ) -> None:
        module_name = f"master.plugins.{plugin_id}"
        init_file = os.path.join(p_dir, plugin_id, "__init__.py")
        if not os.path.exists(init_file):
            init_file = os.path.join(p_dir, f"{plugin_id}.py")

        if not os.path.exists(init_file):
            raise FileNotFoundError(f"Fichier d'entrée introuvable pour le plugin '{plugin_id}': {init_file}")

        spec = importlib.util.spec_from_file_location(module_name, init_file)
        if not spec or not spec.loader:
            raise ImportError(f"Impossible de créer le spec pour {init_file}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        plugin_class = PluginBase._decorated_registry.get(plugin_id)
        if plugin_class:
            ctx = PluginContext(plugin_id=plugin_id, config=config, db=self.db, hook_bus=self.hook_bus)
            instance = plugin_class(ctx)
            self._instances[plugin_id] = instance

            for hspec in instance.hooks:
                fn = getattr(instance, hspec["method_name"], None)
                if fn:
                    self.hook_bus.register(hspec["verb"], fn, plugin_name=plugin_id)

            if instance.scheduled and self.scheduler:
                self.scheduler.start(plugin_id, instance.scheduled, instance)

            if instance.routes and self.route_registrar:
                self.route_registrar.mount(plugin_id, instance.routes, instance)

        elif hasattr(module, "register"):
            # Chemin legacy register(pm)
            module.register(self)

    def _make_wrapper_proxy(self, wrapper: PluginProcessWrapper, hook_name: str) -> Callable:
        async def proxy(**kwargs: Any) -> Any:
            return await wrapper.call_hook(hook_name, **kwargs)
        return proxy

    # ------------------------------------------------------------------
    # API publique : load / unload / uninstall
    # ------------------------------------------------------------------

    async def load_plugin(self, plugin_id: str, plugins_dir: str | None = None) -> bool:
        manifest = self._registry.get_manifest(plugin_id)
        if not manifest:
            await self.scan(plugins_dir)
            manifest = self._registry.get_manifest(plugin_id)
        if not manifest:
            # Fallback : résolution par forme canonique/stem (ex: "test_pkg"
            # demandé alors que le manifest enregistre l'id "test_pkg_plugin").
            for form in {canonical_plugin_id(plugin_id), plugin_file_stem(plugin_id)}:
                manifest = manifest or self._registry.get_manifest(form)
            if not manifest:
                for mid, m in self._registry.get_all_manifests().items():
                    if canonical_plugin_id(mid) == canonical_plugin_id(plugin_id):
                        manifest = m
                        break
        if not manifest:
            logger.error("Impossible de charger '%s': manifest introuvable", plugin_id)
            return False

        # La forme canonique peut tronquer l'id ("test_pkg_plugin" -> "test_pkg") :
        # charger sous manifest.id évite un FileNotFoundError sur le fichier réel.
        target_id = manifest.id

        if target_id in self.loaded_plugins:
            return False

        async with self._get_lock(target_id):
            # Double-check après acquisition du lock
            if target_id in self.loaded_plugins:
                return False

            try:
                await self._load(target_id, manifest, plugins_dir)
                if self.db:
                    await self.db.commit()
                return True
            except Exception as e:
                logger.exception("Échec du chargement de '%s'", target_id)
                self._set_state(target_id, "error", error=str(e))
                try:
                    await self.unload_plugin(target_id)
                except Exception:
                    pass
                if self.db:
                    try:
                        await self.db.execute("UPDATE plugins SET status = 'ERROR', enabled = 1 WHERE id = ?", (target_id,))
                        await self.db.commit()
                    except Exception:
                        pass
                return False

    async def unload_plugin(self, plugin_id: str, *, persist: bool = True) -> None:
        logger.info("Déchargement du plugin '%s'...", plugin_id)

        await self.hook_bus.wait_for_drain(plugin_id)

        for hook_name in list(self.hook_bus.get_hooks().keys()):
            self.hook_bus.unregister(hook_name, plugin_id)

        if self.scheduler:
            await self.scheduler.stop(plugin_id)

        if self.route_registrar:
            self.route_registrar.unmount(plugin_id)

        self.page_registry.unregister(plugin_id)

        wrapper = self._wrappers.pop(plugin_id, None)
        if wrapper:
            await wrapper.stop()

        self._instances.pop(plugin_id, None)

        module_name = f"master.plugins.{plugin_id}"
        sys.modules.pop(module_name, None)

        # Nettoyer toutes les formes de l'id
        for k in {plugin_id, canonical_plugin_id(plugin_id), plugin_file_stem(plugin_id)}:
            if k in self._states:
                del self._states[k]
            self._errors.pop(k, None)

        if self.db and persist:
            await self.db.execute("UPDATE plugins SET status = 'DISABLED', enabled = 0 WHERE id = ?", (plugin_id,))
            await self.db.commit()

        logger.info("Plugin '%s' déchargé.", plugin_id)

    async def uninstall(self, plugin_id: str) -> None:
        manifest = self._registry.get_manifest(plugin_id)
        await self.unload_plugin(plugin_id)
        if manifest and manifest.database and self.db_auto:
            await self.db_auto.drop_tables(plugin_id, manifest.database)
        if self.db:
            await self.db.execute("DELETE FROM plugins WHERE id = ?", (plugin_id,))
            await self.db.commit()

    async def deactivate(self, plugin_id: str) -> None:
        """Backward-compat avec PluginManager.unload_plugin()."""
        await self.unload_plugin(plugin_id)

    async def load_plugins_from_dir(self, directory: str) -> list[str]:
        await self.scan(directory)
        loaded = []
        for plugin_id in self._registry.get_all_manifests():
            enabled = True
            if self.db:
                try:
                    async with self.db.execute("SELECT enabled FROM plugins WHERE id = ?", (plugin_id,)) as cursor:
                        row = await cursor.fetchone()
                        if row:
                            enabled = bool(row[0])
                except Exception:
                    pass
            if enabled and await self.load_plugin(plugin_id, directory):
                loaded.append(plugin_id)
        return loaded

    # ------------------------------------------------------------------
    # loaded_plugins — source de vérité unique
    # ------------------------------------------------------------------

    @property
    def loaded_plugins(self) -> list[str]:
        """Retourne les ids des plugins dont le statut est 'active'."""
        return [pid for pid, s in self._states.items() if s.status == "active"]

    # ------------------------------------------------------------------
    # Backward-compat : _loaded_plugins attendu par admin.py
    # ------------------------------------------------------------------

    @property
    def _loaded_plugins(self) -> list[str]:
        return self.loaded_plugins

    # ------------------------------------------------------------------
    # HookBus proxy
    # ------------------------------------------------------------------

    def get_hooks(self) -> dict[str, list[str]]:
        return self.hook_bus.get_hooks()

    def has_hook(self, hook_name: str) -> bool:
        return self.hook_bus.has_hook(hook_name)

    def register(self, hook_name: str, fn: Callable, *, plugin_name: str = "anonymous") -> None:
        self.hook_bus.register(hook_name, fn, plugin_name=plugin_name)

    def unregister(self, hook_name: str, plugin_name: str) -> int:
        return self.hook_bus.unregister(hook_name, plugin_name)

    def call(self, hook_name: str, **kwargs: Any) -> list[Any]:
        return self.hook_bus.call(hook_name, **kwargs)

    def call_first(self, hook_name: str, **kwargs: Any) -> Any | None:
        return self.hook_bus.call_first(hook_name, **kwargs)

    async def async_call(self, hook_name: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Invoke every subscription for *hook_name* concurrently.

        Delegates to the full-featured :class:`HookBus`, returning structured
        result dicts (``{"success", "result", "error", "plugin_name"}``).
        """
        return await self.hook_bus.async_call(hook_name, **kwargs)

    async def async_call_first(self, hook_name: str, **kwargs: Any) -> Any | None:
        return await self.hook_bus.async_call_first(hook_name, **kwargs)

    # ------------------------------------------------------------------
    # Arrêt propre
    # ------------------------------------------------------------------

    async def shutdown(self) -> None:
        for plugin_id in list(self._wrappers.keys()) + list(self._instances.keys()):
            try:
                # persist=False : un arrêt propre du serveur n'est PAS une
                # désactivation opérateur — l'état enabled/status en DB est
                # préservé pour être rechargé au prochain démarrage.
                await self.unload_plugin(plugin_id, persist=False)
            except Exception:
                pass
        if self.scheduler:
            await self.scheduler.shutdown()

    def set_engine(self, engine: Any) -> None:
        pass  # backward-compat no-op


# ---------------------------------------------------------------------------
# Singleton — backward-compat total avec plugin_manager.py et admin.py
# ---------------------------------------------------------------------------

plugin_engine = PluginEngine()
plugin_manager = plugin_engine
