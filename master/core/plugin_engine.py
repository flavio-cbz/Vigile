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
import time
import types
import uuid
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from master.core.command_registry import CommandEntry, scan_all_routes
from master.core.hook_bus import HookBus
from master.core.lock import LoopBoundLock
from master.core.plugin_base import PluginBase, PluginContext, RedactingAdapter
from master.core.plugin_lifecycle import PluginLifecycleManager
from master.core.plugin_manifest import (
    PluginManifest,
    PluginManifestV2,
    load_and_validate_manifest,
    project_legacy_pages,
)
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


class PluginNamespaceError(RuntimeError):
    """S1 namespace enforcement: a plugin was rejected at load time because
    one of its contributions (class attribution, hook subscription, or
    command name) does not belong to its own namespace."""


# S4 — revision-based hot-reload: boot_id is regenerated at every master
# process start (faille 7). A client seeing a different boot_id must
# invalidate everything and reload — never reconcile partially.
_PROCESS_BOOT_ID: str = str(uuid.uuid4())


@dataclass(frozen=True)
class PluginRevision:
    """(boot_id, counter) pair identifying one atomic registry swap."""

    boot_id: str
    counter: int


def _attach_raw_extras(v2: PluginManifestV2, data: dict) -> PluginManifestV2:
    """Re-attache les champs déclarés uniquement dans le manifest brut (V1)
    que la migration V1→V2 ne transporte pas — ex. ``external_auth_domains``.

    ``_migrate_v1_to_v2`` ne copie que les champs V1 connus ; un champ V2
    déclaré dans un manifest V1 (``schema_version`` absent) serait
    silencieusement perdu. Ce helper le recopie depuis le dict brut après
    validation (le modèle V2 n'est pas frozen → affectation directe).
    """
    raw_domains = data.get("external_auth_domains")
    if raw_domains and not v2.external_auth_domains:
        v2.external_auth_domains = [str(d) for d in raw_domains]
    return v2


def _snapshot_hook_subs(bus: HookBus | None) -> set[tuple[str, str, int]]:
    """Snapshot of every hook subscription as (hook, plugin_name, id(fn)).

    ``id(fn)`` pins each subscription's identity: the S1 rollback relies on
    it to remove ONLY the subs introduced by the rejected load, never a
    real plugin's subscription that happens to share the same name.
    """
    if bus is None:
        return set()
    return {(hook, pn, id(fn)) for hook, subs in bus._hooks.items() for pn, fn in subs}


def _plugin_id_forms(plugin_id: str) -> frozenset[str]:
    """Every identity form a plugin may legitimately subscribe under."""
    return frozenset(
        {plugin_id, canonical_plugin_id(plugin_id), plugin_file_stem(plugin_id)}
    )


def sweep_namespace_violations(
    plugin_id: str,
    *,
    instance: PluginBase | None = None,
    module: types.ModuleType | None = None,
    hook_bus: HookBus | None = None,
    hook_subs_before: set[tuple[str, str, int]] | None = None,
    command_names: Iterable[str] | None = None,
) -> list[str]:
    """S1 registry sweep — collect every namespace violation of one plugin load.

    The decoration-time ``@route`` check is advisory; THIS load-time sweep is
    the enforcement (contract §8.1). Attribution is PER MODULE and covers
    both registration shapes (metrics: module-level ``register(pm)`` AND
    ``PluginBase`` class-based):

      Rule A — class attribution: the plugin class must claim the loaded
               ``plugin_id`` and be defined in the loaded module.
      Rule B — hook attribution: every subscription introduced DURING this
               load must use one of the plugin's id forms
               ({plugin_id, canonical_plugin_id, plugin_file_stem}).
      Rule C — command namespace: every command must be exactly
               ``plugin_id`` or start with ``f"{plugin_id}."`` — the dotted
               prefix, NOT a plain id prefix (``docker2.containers`` is not
               docker's, but plain ``startswith("docker")`` would accept it).

    Returns human-readable violations; an empty list means the plugin is
    clean. The caller must reject the WHOLE plugin on any violation
    (fail-closed, one failure → whole-plugin reject).
    """
    violations: list[str] = []
    id_forms = _plugin_id_forms(plugin_id)

    if instance is not None:
        cls = instance.__class__
        claimed = getattr(cls, "plugin_id", "")
        if claimed != plugin_id:
            violations.append(
                f"class '{cls.__name__}' claims plugin_id '{claimed}' "
                f"(expected '{plugin_id}')"
            )
        if module is not None and cls.__module__ != module.__name__:
            violations.append(
                f"class '{cls.__name__}' is defined in module "
                f"'{cls.__module__}' (expected '{module.__name__}')"
            )

    if command_names is not None:
        for cmd in command_names:
            if cmd != plugin_id and not cmd.startswith(f"{plugin_id}."):
                violations.append(
                    f"command '{cmd}' is outside the '{plugin_id}' namespace "
                    f"(prefix must be '{plugin_id}.')"
                )

    if hook_bus is not None and hook_subs_before is not None:
        current = _snapshot_hook_subs(hook_bus)
        for hook, plugin_name, _fn_id in sorted(current - hook_subs_before):
            if plugin_name not in id_forms:
                violations.append(
                    f"hook '{hook}' registered under foreign plugin_name "
                    f"'{plugin_name}' (expected one of {sorted(id_forms)})"
                )

    return violations


@dataclass
class _PluginState:
    plugin_id: str
    status: Literal["active", "disabled", "error"]
    loader: _LoaderKind = "class_based"
    error: str | None = None


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
        # S3 — V2 meta-schema shadow: canonical declarative contract
        # validated at scan time. May exist without a V1 manifest (V2-only
        # plugins); V1 discovery is never blocked by a V2 failure.
        self._v2_manifests: dict[str, PluginManifestV2] = {}

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

    def get_v2_manifest(self, plugin_id: str) -> PluginManifestV2 | None:
        return self._v2_manifests.get(plugin_id)

    def get_all_v2_manifests(self) -> dict[str, PluginManifestV2]:
        return dict(self._v2_manifests)

    def set_v2_manifest(self, plugin_id: str, v2: PluginManifestV2) -> None:
        self._v2_manifests[plugin_id] = v2

    def remove_v2_manifest(self, plugin_id: str) -> None:
        self._v2_manifests.pop(plugin_id, None)

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
        except Exception as e:
            logger.error("Manifest invalide pour le plugin '%s': %s", entry, e)
            self._errors[entry] = str(e)
            return

        try:
            manifest = PluginManifest(**data)
        except Exception as e:
            # V1 fail-closed → try the V2 meta-schema (V2-only plugin)
            try:
                v2 = _attach_raw_extras(load_and_validate_manifest(data), data)
            except Exception:
                logger.error("Manifest invalide pour le plugin '%s': %s", entry, e)
                self._errors[entry] = str(e)
                return
            self._v2_manifests[v2.id] = v2
            self._manifest_dirs[v2.id] = scan_dir
            try:
                compat_manifest = PluginManifest(
                    id=v2.id,
                    name=v2.name or v2.id,
                    version=v2.version,
                    author=v2.author,
                    description=v2.description,
                    icon=v2.icon,
                    category=v2.category,
                    trusted=getattr(v2, "trusted", True),
                    external_auth_domains=v2.external_auth_domains,
                )
                discovered[compat_manifest.id] = compat_manifest
            except Exception:
                pass
            return

        discovered[manifest.id] = manifest
        self._manifest_dirs[manifest.id] = scan_dir
        # Additive V2 validation: a V2 failure never blocks V1 discovery.
        try:
            self._v2_manifests[manifest.id] = _attach_raw_extras(
                load_and_validate_manifest(data), data
            )
        except Exception as e:
            logger.warning("Manifest V2 invalide pour '%s' (V1 conservé): %s", entry, e)

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
                # Additive V2 validation of the sidecar manifest
                try:
                    self._v2_manifests[manifest.id] = _attach_raw_extras(
                        load_and_validate_manifest(manifest_data), manifest_data
                    )
                except Exception as e:
                    logger.warning("Manifest V2 invalide pour '%s' (V1 conservé): %s", entry, e)
                return
            except Exception as e:
                # V1 sidecar invalide → essai V2 (plugin V2-only en fichier simple)
                try:
                    v2 = _attach_raw_extras(load_and_validate_manifest(manifest_data), manifest_data)
                    self._v2_manifests[v2.id] = v2
                    self._manifest_dirs[v2.id] = scan_dir
                    try:
                        compat_manifest = PluginManifest(
                            id=v2.id,
                            name=v2.name or v2.id,
                            version=v2.version,
                            author=v2.author,
                            description=v2.description,
                            icon=v2.icon,
                            category=v2.category,
                            trusted=getattr(v2, "trusted", True),
                            external_auth_domains=v2.external_auth_domains,
                        )
                        discovered[compat_manifest.id] = compat_manifest
                    except Exception:
                        pass
                    return
                except Exception:
                    logger.error("Manifest invalide pour '%s': %s", entry, e)
                    self._errors[pid] = str(e)

        # Manifest synthétique — pas d'import, loader=legacy pour .py sans manifest
        discovered[pid] = PluginManifest(
            id=pid,
            name=pid.replace("_", " ").title(),
            version="0.0.0",
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
                # Additive V2 validation of the archive manifest
                try:
                    self._v2_manifests[manifest.id] = _attach_raw_extras(
                        load_and_validate_manifest(manifest_data), manifest_data
                    )
                except Exception as e:
                    logger.warning("Manifest V2 invalide pour '%s' (V1 conservé): %s", manifest.id, e)

                # Valide manifest.id : il ne doit pas s'échapper du répertoire de scan
                scan_dir_real = Path(scan_dir).resolve()
                extract_target = (scan_dir_real / manifest.id).resolve()
                if not extract_target.is_relative_to(scan_dir_real):
                    self._errors[manifest.id] = "manifest.id invalide (traversal de chemin)"
                    return

                if os.path.exists(extract_target):
                    self._errors[manifest.id] = "Répertoire cible existe déjà"
                    return

                tmp_dir = tempfile.mkdtemp(prefix=f"vigile_zip_{manifest.id}_")
                try:
                    # Zip-slip : chaque membre doit rester sous tmp_dir
                    tmp_real = Path(tmp_dir).resolve()
                    for member in zf.namelist():
                        if not (tmp_real / member).resolve().is_relative_to(tmp_real):
                            raise OSError(f"Entrée ZIP invalide: {member!r}")
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
        # PYTHONPATH forcé : le subprocess worker doit importer master.* depuis
        # le projet, sans héritage d'un PYTHONPATH hôte potentiellement pollué.
        env["PYTHONPATH"] = project_root
        env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
        env.setdefault("HOME", os.path.expanduser("~"))
        env.setdefault("LANG", "C.UTF-8")

        preexec_fn = None
        if _resource_mod is not None:
            def _set_limits():
                # Garde-fous de RESSOURCES (mémoire/CPU) — pas une frontière de
                # sécurité : le subprocess tourne toujours sur le noyau hôte.
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

        # EOF → le subprocess est mort : résoudre toutes les futures en attente
        # pour éviter les hangs (snapshot : call_hook pop le dict pendant ce temps).
        returncode = self.process.returncode if self.process else None
        if self._init_future and not self._init_future.done():
            self._init_future.set_exception(RuntimeError("subprocess terminated before initialization"))
        for fut in list(self._pending_calls.values()):
            if not fut.done():
                fut.set_exception(RuntimeError(f"subprocess terminated (returncode={returncode})"))

    async def _read_stderr(self) -> None:
        while self.process and self.process.stderr:
            line = await self.process.stderr.readline()
            if not line:
                break
            logger.info("[%s-stderr] %s", self.plugin_id, line.decode().strip())

    async def _handle_db(self, msg: dict) -> None:
        # Modèle de confiance : le sandbox fournit des limites de ressources
        # (RLIMIT) et une isolation d'env — PAS un confinement SQL. La règle
        # SELECT-only est une convention de surface API appliquée côté client
        # dans PluginContext.db_query (plugin_base.py) ; le parent exécute
        # telle quelle la requête qui arrive sur le canal IPC. Aucune
        # validation supplémentaire ici (choix architectural).
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
        # Auto-restart du subprocess mort — sans circuit breaker local : le
        # CircuitBreaker (niveau HookBus) couvre le dispatch des hooks.
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
        boot_id: str | None = None,
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
        self._kill_switch: dict[str, dict] = {}
        self._boot_id: str = boot_id or _PROCESS_BOOT_ID
        self._revision_counter: int = 0
        self._swap_lock = LoopBoundLock()
        # Module-level register(pm) plugins (legacy shape) — the allowlist
        # scan covers BOTH _instances and _plugin_modules.
        self._plugin_modules: dict[str, types.ModuleType] = {}
        # Code-derived command inventory (J1): name -> CommandEntry
        self._command_allowlist: dict[str, CommandEntry] = {}

        # Exposé pour backward-compat avec admin.py (_hooks, _sandbox, _wrappers)
        self._hooks: dict = self.hook_bus._hooks
        self._sandbox: bool = True

        self.lifecycle: PluginLifecycleManager = PluginLifecycleManager(engine=self)

        # scanner = self pour backward-compat (admin.py: active_pm.scanner.get_manifest)
        self.scanner = self

    @property
    def db(self) -> Any | None:
        # L'accès privé `._connection` est le seul moyen de vérifier la vivacité
        # d'une connexion aiosqlite (aucun attribut public) ; get_db_conn()
        # lève quand la base n'est pas initialisée.
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

        try:
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
        finally:
            # Le commit doit TOUJOURS s'exécuter, même si une itération de la
            # boucle (INSERT ou UPDATE de statut ERROR) lève une exception.
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

        loader_kind = self._registry.resolve_loader(manifest)

        # S3 — V2 shadow: re-derive from the V1 manifest if the scan-time
        # shadow is missing (defensive; the registry keeps it across loads).
        if self._registry.get_v2_manifest(plugin_id) is None:
            try:
                v2 = _attach_raw_extras(
                    load_and_validate_manifest(manifest.model_dump(mode="json", exclude_none=True)),
                    manifest.model_dump(mode="json", exclude_none=True),
                )
                self._registry.set_v2_manifest(plugin_id, v2)
            except Exception as e:
                logger.warning("Dérivation du manifest V2 impossible pour '%s': %s", plugin_id, e)

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
            v1_pages = [p.model_dump() for p in manifest.pages]
            v2 = self._registry.get_v2_manifest(plugin_id)
            pages = project_legacy_pages(v2, v1_pages) if v2 is not None else v1_pages
            self.page_registry.register(plugin_id, pages)

        # S4 — build-then-swap, serve-then-swap: the atomic swap happens
        # BEFORE the plugin becomes observable as active (no flicker).
        await self._swap_registry()

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
            self.route_registrar.mount(
                plugin_id,
                [r.model_dump() for r in manifest.routes],
                wrapper,
                external_auth_domains=self._plugin_external_auth_domains(plugin_id),
            )

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
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception:
            # Ne pas laisser un module à moitié exécuté dans sys.modules
            sys.modules.pop(module_name, None)
            raise

        # S1 — snapshot BEFORE registration: the sweep only attributes subs
        # introduced by THIS load.
        hook_subs_before = _snapshot_hook_subs(self.hook_bus)

        # S1 — pre-check BEFORE any registration/instantiation: every
        # PluginBase subclass defined in THIS module must claim this
        # plugin's id (fail-closed on foreign-id classes).
        for name in list(vars(module)):
            if name.startswith("__"):
                continue
            value = getattr(module, name)
            if (
                isinstance(value, type)
                and issubclass(value, PluginBase)
                and value is not PluginBase
            ):
                claimed = getattr(value, "plugin_id", "")
                if claimed != plugin_id:
                    raise PluginNamespaceError(
                        f"Plugin '{plugin_id}' rejected by the S1 namespace sweep: "
                        f"module '{module.__name__}' defines class '{value.__name__}' "
                        f"claiming plugin_id '{claimed}'"
                    )

        plugin_class = PluginBase._decorated_registry.get(plugin_id)
        if plugin_class:
            # The registered class must be defined in the loaded module — a
            # foreign class registered under our id is a poisoned registry.
            if plugin_class.__module__ != module_name:
                raise PluginNamespaceError(
                    f"Plugin '{plugin_id}' rejected by the S1 namespace sweep: "
                    f"registered class '{plugin_class.__name__}' is defined in "
                    f"module '{plugin_class.__module__}' (expected '{module_name}')"
                )
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
                self.route_registrar.mount(
                    plugin_id,
                    instance.routes,
                    instance,
                    external_auth_domains=self._plugin_external_auth_domains(plugin_id),
                )

        elif hasattr(module, "register"):
            # Chemin legacy register(pm)
            module.register(self)

        # S1 — registry sweep AFTER registration: ONE violation → rollback
        # + reject the whole plugin (fail-closed).
        command_names: list[str] = []
        instance_ = self._instances.get(plugin_id)
        if instance_ is not None:
            command_names.extend(
                f"{plugin_id}.{r['handler']}" for r in instance_.routes
            )
        command_names.extend(
            f"{plugin_id}.{name}"
            for name, value in vars(module).items()
            if not name.startswith("__")
            and callable(value)
            and hasattr(value, "__plugin_route__")
        )
        violations = sweep_namespace_violations(
            plugin_id,
            instance=instance_,
            module=module,
            hook_bus=self.hook_bus,
            hook_subs_before=hook_subs_before,
            command_names=command_names,
        )
        if violations:
            await self._rollback_inprocess_load(plugin_id, instance_, hook_subs_before)
            raise PluginNamespaceError(
                f"Plugin '{plugin_id}' rejected by the S1 namespace sweep: "
                + "; ".join(violations)
            )

        self._plugin_modules[plugin_id] = module

    async def _rollback_inprocess_load(
        self,
        plugin_id: str,
        instance: PluginBase | None,
        hook_subs_before: set[tuple[str, str, int]],
    ) -> None:
        """Undo everything a rejected in-process load registered.

        Identity-based: only the hook subscriptions introduced by THIS load
        are removed (matched by (hook, plugin_name, id(fn))), so a plugin
        that registered under a foreign name can never clobber the real
        plugin's subscription sharing that name.
        """
        if self.hook_bus is not None:
            for hook_name in list(self.hook_bus._hooks):
                self.hook_bus._hooks[hook_name] = [
                    (pn, fn)
                    for pn, fn in self.hook_bus._hooks[hook_name]
                    if (hook_name, pn, id(fn)) in hook_subs_before
                ]
                if not self.hook_bus._hooks[hook_name]:
                    del self.hook_bus._hooks[hook_name]

        if self.route_registrar:
            self.route_registrar.unmount(plugin_id)

        if self.scheduler is not None and instance is not None:
            try:
                await self.scheduler.stop(plugin_id)
            except Exception:
                logger.exception("Échec de l'arrêt du scheduler lors du rollback de '%s'", plugin_id)

        self._instances.pop(plugin_id, None)
        self._plugin_modules.pop(plugin_id, None)
        sys.modules.pop(f"master.plugins.{plugin_id}", None)

    def _make_wrapper_proxy(self, wrapper: PluginProcessWrapper, hook_name: str) -> Callable:
        async def proxy(**kwargs: Any) -> Any:
            return await wrapper.call_hook(hook_name, **kwargs)
        return proxy

    async def _swap_registry(self, *, removed: str | None = None) -> None:
        """Atomically swap the served registry + command allowlist.

        Order inside the single lock: manifest removal FIRST, then the
        allowlist rebuild — an observer mid-swap never sees a stale
        allowlist entry for a removed manifest.

        T26 — l'événement SSE ``plugins.invalidated`` est diffusé APRÈS le
        compteur incrémenté : serve-then-swap, le nouveau registre est déjà
        observable par les clients qui revalident (aucun flicker, plan D2).
        """
        async with self._swap_lock:
            if removed is not None:
                self._swap_remove_manifest(removed)
            before = set(self._command_allowlist)
            self._swap_rebuild_allowlist()
            self._revision_counter += 1
            await self._broadcast_invalidation(removed=removed, before=before)

    async def _broadcast_invalidation(self, *, removed: str | None, before: set[str]) -> None:
        """T26 — publie l'invalidation sur l'EventBus (canal ``plugins.invalidated``).

        Contrat : ``{plugin_id, boot_id, revision: int, action}`` (plan §S4).
        - ``removed`` présent → un seul événement, action "unloaded".
        - sinon (swap de chargement) → un événement par plugin dont l'allowlist
          a gagné des commandes : "loaded" au premier chargement, "updated"
          lors d'un rechargement (déterminé par la présence préalable des
          commandes dans l'allowlist).
        Le diff d'allowlist évite de toucher à la signature publique du swap
        (un spy existant du test S4 s'y attend) tout en restant précis : un
        plugin sans commande code-derived (ex. sandbox) n'émet rien au
        chargement — il n'a aucun client /batch à invalider.
        """
        from master.core.event_bus import event_bus

        if removed is not None:
            affected: dict[str, str] = {removed: "unloaded"}
        else:
            affected = {
                entry.plugin_id: ("updated" if name in before else "loaded")
                for name, entry in self._command_allowlist.items()
                if name not in before
            }
        if not affected:
            return
        revision = self.revision
        for plugin_id, action in affected.items():
            try:
                await event_bus.publish(
                    "plugins.invalidated",
                    {
                        "plugin_id": plugin_id,
                        "boot_id": revision.boot_id,
                        "revision": revision.counter,
                        "action": action,
                    },
                )
            except Exception:
                logger.exception("Échec de la publication de l'invalidation pour '%s'", plugin_id)

    def _swap_remove_manifest(self, removed: str) -> None:
        self._registry.remove_v2_manifest(removed)

    def _swap_rebuild_allowlist(self) -> None:
        """Rebuild the code-derived command inventory from BOTH shapes:
        class-based instances and module-level register(pm) modules."""
        entries: list[CommandEntry] = []
        seen: set[tuple[str, str, str]] = set()
        # _instances and _plugin_modules may share the same plugin_id key —
        # merge per-shape (class routes + module functions) instead of
        # merging dicts (which would drop the instance scan).
        for sources in (self._instances, self._plugin_modules):
            for entry in scan_all_routes(sources):
                key = (entry.plugin_id, entry.path_template, entry.method)
                if key in seen:
                    continue
                seen.add(key)
                entries.append(entry)
        self._command_allowlist = {e.name: e for e in entries}

    @property
    def boot_id(self) -> str:
        return self._boot_id

    @property
    def revision_counter(self) -> int:
        return self._revision_counter

    @property
    def revision(self) -> PluginRevision:
        return PluginRevision(boot_id=self._boot_id, counter=self._revision_counter)

    def get_command_allowlist(self) -> dict[str, CommandEntry]:
        return dict(self._command_allowlist)

    def get_served_manifest(self, plugin_id: str) -> PluginManifestV2 | None:
        return self._registry.get_v2_manifest(plugin_id)

    def get_served_manifests(self) -> dict[str, PluginManifestV2]:
        return self._registry.get_all_v2_manifests()

    def _plugin_external_auth_domains(self, plugin_id: str) -> list[str] | None:
        """Domaines d'auth externe déclarés par le plugin (manifest brut).

        Lu depuis le shadow V2 du registre (store de scan, jamais remplacé
        par ``_swap_registry``) : c'est là que ``_attach_raw_extras`` a
        recopié ``external_auth_domains`` depuis le manifest V1. ``None``
        si le plugin n'en déclare aucun → aucun garde-fou monté.
        """
        v2 = self._registry.get_v2_manifest(plugin_id)
        if v2 is None or not v2.external_auth_domains:
            return None
        return list(v2.external_auth_domains)

    def get_served_pages(self) -> list[dict]:
        """Legacy pages[] projection over the canonical V2 registry (S3
        strangler seam): GET /api/plugins/pages will be swapped onto this."""
        result: list[dict] = []
        for pid, v2 in self._registry.get_all_v2_manifests().items():
            v1 = self._registry.get_manifest(pid)
            v1_pages = [p.model_dump() for p in v1.pages] if v1 else []
            result.extend(project_legacy_pages(v2, v1_pages))
        return result

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

        was_served = (
            plugin_id in self._instances
            or plugin_id in self._wrappers
            or plugin_id in self._plugin_modules
        )

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

        # S4 — atomic swap: manifest removed before allowlist rebuild, inside
        # one lock. Failed loads (never served) must NOT bump the revision.
        if was_served:
            await self._swap_registry(removed=plugin_id)

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

    def is_kill_switched(self, plugin_id: str) -> bool:
        """Check if a plugin is hard-disabled via the kill switch."""
        return plugin_id in self._kill_switch

    async def disable_plugin(
        self,
        plugin_id: str,
        hard: bool = False,
        reason: str = "",
        user_id: str = "",
    ) -> None:
        """Disable a plugin via the kill switch (Faille 6).

        Soft mode (hard=False): maintenance — drain in-flight calls, no new invocations,
        re-activatable without justification.
        Hard mode (hard=True): compromise — immediate tombstone, instant rejection of new calls,
        no drain, requires explicit justification to re-enable.
        """
        from master.core.event_bus import event_bus

        mode = "hard" if hard else "maintenance"
        self._kill_switch[plugin_id] = {
            "hard": hard,
            "disabled_at": time.time(),
            "reason": reason,
            "user_id": user_id,
        }

        await self.unload_plugin(plugin_id)

        if self.db:
            await self.db.execute(
                "UPDATE plugins SET status = 'DISABLED', enabled = 0 WHERE id = ?",
                (plugin_id,),
            )
            await self.db.commit()

        if self.db:
            from master.core.audit import log_action, AuditAction
            await log_action(
                self.db,
                user_id=user_id,
                action=AuditAction.DISABLE_PLUGIN,
                details={
                    "plugin_id": plugin_id,
                    "mode": mode,
                    "reason": reason,
                    "hard": hard,
                },
            )

        logger.info("Plugin '%s' kill-switched (mode=%s).", plugin_id, mode)

        await self._swap_registry(removed=plugin_id)
        revision = self.revision
        await event_bus.publish(
            "plugins.invalidated",
            {
                "plugin_id": plugin_id,
                "boot_id": revision.boot_id,
                "revision": revision.counter,
                "action": "disabled",
                "mode": mode,
            },
        )

    async def enable_plugin(self, plugin_id: str) -> None:
        """Re-enable a kill-switched plugin."""
        from master.core.event_bus import event_bus

        entry = self._kill_switch.pop(plugin_id, None)
        if entry is None:
            logger.warning("enable_plugin called for '%s' but no kill-switch entry exists.", plugin_id)
            return

        hard = entry.get("hard", False)
        was_hard = hard

        plugin_dir = None
        for dir_path in getattr(self._registry, "_manifest_dirs", {}).values():
            if canonical_plugin_id(plugin_id) in dir_path or plugin_file_stem(plugin_id) in dir_path:
                plugin_dir = dir_path
                break

        if plugin_dir is None:
            from master.config import settings
            plugin_dir = getattr(settings, "plugins_dir", None)

        if plugin_dir:
            await self.load_plugin(canonical_plugin_id(plugin_id), plugin_dir)
        else:
            logger.warning("Could not resolve plugin directory for '%s' to re-enable.", plugin_id)

        if self.db:
            from master.core.audit import log_action, AuditAction
            await log_action(
                self.db,
                user_id=entry.get("user_id", "system"),
                action=AuditAction.ENABLE_PLUGIN,
                details={
                    "plugin_id": plugin_id,
                    "was_hard": was_hard,
                },
            )
            await self.db.execute(
                "UPDATE plugins SET status = 'ACTIVE', enabled = 1 WHERE id = ?",
                (plugin_id,),
            )
            await self.db.commit()

        # Broadcast SSE invalidation
        await self._swap_registry(removed=None)
        revision = self.revision
        await event_bus.publish(
            "plugins.invalidated",
            {
                "plugin_id": plugin_id,
                "boot_id": revision.boot_id,
                "revision": revision.counter,
                "action": "enabled",
                "was_hard": was_hard,
            },
        )

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

    @property
    def loaded_plugins(self) -> list[str]:
        """Retourne les ids des plugins dont le statut est 'active'."""
        return [pid for pid, s in self._states.items() if s.status == "active"]

    @property
    def _loaded_plugins(self) -> list[str]:
        return self.loaded_plugins

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

    async def shutdown(self) -> None:
        for plugin_id in set(self._wrappers) | set(self._instances):
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


plugin_engine = PluginEngine()
plugin_manager = plugin_engine
