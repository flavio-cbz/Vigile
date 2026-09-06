"""
T14 — S1 namespace enforcement tests (J3a).

Contract (docs/contracts/block-contract-v2.md §8.1):
  - The @route decoration-time check is advisory. Enforcement is the
    load-time registry sweep in ``plugin_engine._load_inprocess``.
  - Attribution is PER MODULE and covers BOTH registration shapes
    (metrics: module-level ``register(pm)`` AND class-based ``PluginBase``).
  - The prefix is ``id + "."`` (NOT plain ``id`` — avoids docker/docker2
    collisions).
  - ONE violation → reject the whole plugin (fail-closed).
  - Rollback is identity-based (subs introduced by THIS load only), so a
    plugin registering under a foreign name can never clobber a real
    plugin's hook subscriptions.

Pure-function tests exercise ``sweep_namespace_violations`` directly;
engine-level tests prove the sweep is wired into ``_load_inprocess`` with
full rollback and no residue.
"""

from __future__ import annotations

import json
import sys
import types

import pytest

from master.core.hook_bus import HookBus
from master.core.plugin_base import PluginBase, PluginContext
from master.core.plugin_engine import (
    PluginEngine,
    PluginNamespaceError,
    sweep_namespace_violations,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GOOD_CLASS_CODE = (
    "from master.core.plugin_base import PluginBase, route\n"
    "class GoodPkg(PluginBase):\n"
    "    plugin_id = 'goodpkg'\n"
    "    @route('/list')\n"
    "    def list_items(self):\n"
    "        return []\n"
)

MODULE_CLEAN = (
    "def register(pm):\n"
    "    pm.register('on_status_report', _handle, plugin_name='goodmod')\n"
    "def _handle(**kwargs):\n"
    "    return 'ok'\n"
)

MODULE_FOREIGN_HOOK = (
    "def register(pm):\n"
    "    pm.register('on_status_report', _handle, plugin_name='docker')\n"
    "def _handle(**kwargs):\n"
    "    return 'ok'\n"
)

DOCKER2_MASQUERADE = (
    "def register(pm):\n"
    "    # docker_plugin is the FILE STEM form of the real docker plugin —\n"
    "    # claiming it from 'docker2' must be rejected.\n"
    "    pm.register('on_status_report', _handle, plugin_name='docker_plugin')\n"
    "def _handle(**kwargs):\n"
    "    return 'ok'\n"
)

CLASS_FOREIGN_ID = (
    "from master.core.plugin_base import PluginBase, route\n"
    "class Evil(PluginBase):\n"
    "    plugin_id = 'other'\n"
    "    @route('/x')\n"
    "    def x(self):\n"
    "        return []\n"
)

OTHER_MODULE = (
    "def register(pm):\n"
    "    pm.register('on_status_report', _handle, plugin_name='other')\n"
    "def _handle(**kwargs):\n"
    "    return 'ok'\n"
)


def _make_module(name: str, code: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    exec(code, mod.__dict__)
    return mod


def _snapshot(bus: HookBus) -> set[tuple[str, str, int]]:
    return {(h, pn, id(fn)) for h, subs in bus._hooks.items() for pn, fn in subs}


def _write_plugin(tmp_path, pid: str, code: str, manifest: dict | None = None) -> str:
    pkg = tmp_path / pid
    pkg.mkdir()
    (pkg / "manifest.json").write_text(
        json.dumps(
            manifest
            or {
                "id": pid,
                "name": f"Test {pid}",
                "version": "1.0.0",
                "trusted": True,
            }
        )
    )
    (pkg / "__init__.py").write_text(code)
    return str(tmp_path)


@pytest.fixture(autouse=True)
def _cleanup_plugin_runtime():
    """Pop class-registry + sys.modules pollution from executed plugin modules."""
    yield
    for pid in (
        "goodpkg", "goodmod", "evilmod", "docker2", "badcls", "other",
        "purepkg", "stranger",
    ):
        PluginBase._decorated_registry.pop(pid, None)
        sys.modules.pop(f"master.plugins.{pid}", None)


async def _load_pkg(engine: PluginEngine, plugins_dir: str, pid: str) -> None:
    await engine._registry.scan(plugins_dir)
    manifest = engine._registry.get_manifest(pid)
    assert manifest is not None, f"manifest {pid} not discovered"
    await engine._load(pid, manifest, plugins_dir)


# ---------------------------------------------------------------------------
# Rule A — class attribution
# ---------------------------------------------------------------------------


def test_sweep_clean_class_based():
    mod = _make_module("master.plugins.goodpkg", GOOD_CLASS_CODE)
    inst = mod.GoodPkg(PluginContext(plugin_id="goodpkg", config={}, db=None))
    violations = sweep_namespace_violations("goodpkg", instance=inst, module=mod)
    assert violations == []


def test_sweep_class_claiming_foreign_id():
    code = GOOD_CLASS_CODE.replace('plugin_id = \'goodpkg\'', 'plugin_id = \'other\'')
    mod = _make_module("master.plugins.goodpkg", code)
    inst = mod.GoodPkg(PluginContext(plugin_id="goodpkg", config={}, db=None))
    violations = sweep_namespace_violations("goodpkg", instance=inst, module=mod)
    assert len(violations) == 1
    assert "goodpkg" in violations[0] and "other" in violations[0]


def test_sweep_class_from_foreign_module():
    foreign = _make_module("master.plugins.other", GOOD_CLASS_CODE)
    inst = foreign.GoodPkg(PluginContext(plugin_id="goodpkg", config={}, db=None))
    mod = _make_module("master.plugins.goodpkg", "x = 1")
    violations = sweep_namespace_violations("goodpkg", instance=inst, module=mod)
    assert len(violations) == 1
    assert "master.plugins.other" in violations[0]


def test_sweep_metrics_dual_shape_clean():
    """The contract's reference plugin: metrics registers BOTH shapes."""
    import master.plugins.metrics as metrics_module
    from master.plugins.metrics import MetricsPlugin

    inst = MetricsPlugin(PluginContext(plugin_id="metrics", config={}, db=None))
    names = [f"metrics.{r['handler']}" for r in inst.routes]
    names += [
        f"metrics.{n}"
        for n, v in vars(metrics_module).items()
        if callable(v) and hasattr(v, "__plugin_route__")
    ]
    violations = sweep_namespace_violations(
        "metrics", instance=inst, module=metrics_module, command_names=names
    )
    assert violations == []


# ---------------------------------------------------------------------------
# Rule B — hook attribution
# ---------------------------------------------------------------------------


def test_sweep_clean_hook_attribution():
    bus = HookBus()
    before = _snapshot(bus)
    bus.register("on_status_report", lambda **kw: None, plugin_name="goodpkg")
    violations = sweep_namespace_violations(
        "goodpkg", hook_bus=bus, hook_subs_before=before
    )
    assert violations == []


def test_sweep_foreign_hook_attribution():
    bus = HookBus()
    before = _snapshot(bus)
    bus.register("on_status_report", lambda **kw: None, plugin_name="other")
    violations = sweep_namespace_violations(
        "goodpkg", hook_bus=bus, hook_subs_before=before
    )
    assert len(violations) == 1
    assert "other" in violations[0]


def test_sweep_hook_attribution_accepts_id_forms():
    """docker_plugin (file stem) and docker (canonical) are both docker's."""
    bus = HookBus()
    before = _snapshot(bus)
    bus.register("on_status_report", lambda **kw: None, plugin_name="docker_plugin")
    violations = sweep_namespace_violations(
        "docker", hook_bus=bus, hook_subs_before=before
    )
    assert violations == []


def test_sweep_ignores_preexisting_subs():
    bus = HookBus()
    bus.register("on_status_report", lambda **kw: None, plugin_name="stranger")
    before = _snapshot(bus)  # stranger already present BEFORE this load
    bus.register("on_status_report", lambda **kw: None, plugin_name="goodpkg")
    violations = sweep_namespace_violations(
        "goodpkg", hook_bus=bus, hook_subs_before=before
    )
    assert violations == []


# ---------------------------------------------------------------------------
# Rule C — command namespace (dotted prefix: id + ".")
# ---------------------------------------------------------------------------


def test_sweep_clean_command_namespace():
    assert (
        sweep_namespace_violations(
            "goodpkg", command_names=["goodpkg", "goodpkg.list_items"]
        )
        == []
    )


def test_sweep_rejects_docker2_prefix_collision():
    """'docker2.containers' must NOT pass docker's namespace — a plain
    startswith('docker') check would wrongly accept it (docker/docker2)."""
    violations = sweep_namespace_violations(
        "docker", command_names=["docker2.containers"]
    )
    assert len(violations) == 1
    assert "docker2.containers" in violations[0]


def test_sweep_accepts_exact_docker_command():
    assert (
        sweep_namespace_violations("docker", command_names=["docker.containers"]) == []
    )


def test_sweep_rejects_bare_prefix_attacker():
    """An attacker's command 'docker_containers' (underscore, not dot) is
    not docker's — only id + '.' (or exact id) is inside the namespace."""
    violations = sweep_namespace_violations(
        "docker", command_names=["docker_containers"]
    )
    assert len(violations) == 1


# ---------------------------------------------------------------------------
# Engine-level: sweep wired into _load_inprocess
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_loads_well_behaved_class_plugin(tmp_path):
    engine = PluginEngine(hook_bus=HookBus())
    d = _write_plugin(tmp_path, "goodpkg", GOOD_CLASS_CODE)
    await _load_pkg(engine, d, "goodpkg")
    assert engine.loaded_plugins == ["goodpkg"]
    allowlist = engine.get_command_allowlist()
    assert "goodpkg.list_items" in allowlist
    assert allowlist["goodpkg.list_items"].plugin_id == "goodpkg"


@pytest.mark.asyncio
async def test_engine_loads_well_behaved_module_plugin(tmp_path):
    engine = PluginEngine(hook_bus=HookBus())
    d = _write_plugin(tmp_path, "goodmod", MODULE_CLEAN)
    await _load_pkg(engine, d, "goodmod")
    assert engine.loaded_plugins == ["goodmod"]
    assert engine.has_hook("on_status_report")


@pytest.mark.asyncio
async def test_engine_rejects_module_registering_foreign_hook(tmp_path):
    engine = PluginEngine(hook_bus=HookBus())
    d = _write_plugin(tmp_path, "evilmod", MODULE_FOREIGN_HOOK)
    await engine._registry.scan(d)
    manifest = engine._registry.get_manifest("evilmod")

    with pytest.raises(PluginNamespaceError):
        await engine._load("evilmod", manifest, d)

    assert engine.loaded_plugins == []
    assert "evilmod" not in engine._instances
    assert "evilmod" not in engine._plugin_modules
    assert "master.plugins.evilmod" not in sys.modules
    # The foreign 'docker' sub introduced by the failed load must be GONE —
    # identity rollback, never name-based (a real docker sub must survive).
    docker_subs = [
        pn
        for hook, subs in engine.hook_bus._hooks.items()
        for pn, _ in subs
        if pn == "docker"
    ]
    assert docker_subs == []


@pytest.mark.asyncio
async def test_load_plugin_returns_false_and_cleans(tmp_path):
    engine = PluginEngine(hook_bus=HookBus())
    d = _write_plugin(tmp_path, "evilmod", MODULE_FOREIGN_HOOK)
    ok = await engine.load_plugin("evilmod", d)
    assert ok is False
    assert engine.loaded_plugins == []
    assert "evilmod" not in engine._instances
    assert "master.plugins.evilmod" not in sys.modules


@pytest.mark.asyncio
async def test_engine_rejects_class_claiming_foreign_id(tmp_path):
    engine = PluginEngine(hook_bus=HookBus())
    d = _write_plugin(tmp_path, "badcls", CLASS_FOREIGN_ID)
    await engine._registry.scan(d)
    manifest = engine._registry.get_manifest("badcls")

    with pytest.raises(PluginNamespaceError):
        await engine._load("badcls", manifest, d)

    assert engine.loaded_plugins == []
    assert "badcls" not in engine._instances


@pytest.mark.asyncio
async def test_foreign_class_poisons_other_plugin_load(tmp_path):
    """A class claiming 'other' while defined in badcls' module poisons the
    decorated registry: loading the register-shape plugin 'other' finds the
    foreign class and must fail closed on the module mismatch."""
    engine = PluginEngine(hook_bus=HookBus())
    d1 = _write_plugin(tmp_path, "badcls", CLASS_FOREIGN_ID)
    await engine._registry.scan(d1)
    m1 = engine._registry.get_manifest("badcls")
    with pytest.raises(PluginNamespaceError):
        await engine._load("badcls", m1, d1)

    d2 = _write_plugin(tmp_path, "other", OTHER_MODULE)
    await engine._registry.scan(d2)
    m2 = engine._registry.get_manifest("other")
    with pytest.raises(PluginNamespaceError):
        await engine._load("other", m2, d2)

    assert engine.loaded_plugins == []
    assert "other" not in engine._instances


@pytest.mark.asyncio
async def test_engine_rejects_docker2_hook_masquerade(tmp_path):
    """docker2 claiming docker's file-stem identity must be rejected AND
    must leave zero residue in the hook bus."""
    engine = PluginEngine(hook_bus=HookBus())
    d = _write_plugin(tmp_path, "docker2", DOCKER2_MASQUERADE)
    await engine._registry.scan(d)
    manifest = engine._registry.get_manifest("docker2")

    with pytest.raises(PluginNamespaceError):
        await engine._load("docker2", manifest, d)

    assert engine.loaded_plugins == []
    docker_subs = [
        pn
        for hook, subs in engine.hook_bus._hooks.items()
        for pn, _ in subs
        if pn == "docker_plugin"
    ]
    assert docker_subs == []
