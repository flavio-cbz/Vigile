"""
T17 — S4 revision-based hot-reload tests (J3a).

Contract (docs/contracts/block-contract-v2.md §8.4):
  - Revision = pair (boot_id, counter). boot_id is a UUID regenerated at
    master process start (faille 7) — a different boot_id ⇒ full reload,
    never partial reconciliation.
  - Atomic build-then-swap, serve-then-swap: the manifest is removed BEFORE
    the allowlist is rebuilt, inside the same locked swap; the plugin is
    never observable as active mid-swap (no flicker).
  - Flags gate ROUTING only, never the registry state (D4): sandbox=False
    still populates the served manifest + command allowlist.
  - V2 shadow: manifests are validated against the V2 meta-schema at scan
    time; V1 discovery is never blocked by a V2 validation failure, and a
    V2-only manifest (V1-rejected) still shadows correctly.
"""

from __future__ import annotations

import json
import sys
import uuid

import pytest

from master.core.hook_bus import HookBus
from master.core.plugin_base import PluginBase
from master.core.plugin_engine import (
    PluginEngine,
    PluginRegistry,
    PluginRevision,
)

SWAP_CLASS_CODE = (
    "from master.core.plugin_base import PluginBase, route\n"
    "class SwapPkg(PluginBase):\n"
    "    plugin_id = 'swappkg'\n"
    "    @route('/list')\n"
    "    def list_items(self):\n"
    "        return []\n"
)


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
    yield
    PluginBase._decorated_registry.pop("swappkg", None)
    sys.modules.pop("master.plugins.swappkg", None)


async def _load_pkg(engine: PluginEngine, plugins_dir: str, pid: str) -> None:
    await engine._registry.scan(plugins_dir)
    manifest = engine._registry.get_manifest(pid)
    assert manifest is not None, f"manifest {pid} not discovered"
    await engine._load(pid, manifest, plugins_dir)


# ---------------------------------------------------------------------------
# boot_id — per-process UUID, injectable
# ---------------------------------------------------------------------------


def test_boot_id_is_uuid_and_shared_per_process():
    e1 = PluginEngine()
    e2 = PluginEngine()
    uuid.UUID(e1.boot_id)
    assert e1.boot_id == e2.boot_id  # same master process → same boot_id


def test_boot_id_injectable():
    engine = PluginEngine(boot_id="test-boot")
    assert engine.boot_id == "test-boot"


def test_boot_id_regenerated_when_process_constant_changes(monkeypatch):
    monkeypatch.setattr("master.core.plugin_engine._PROCESS_BOOT_ID", "fresh-boot")
    assert PluginEngine().boot_id == "fresh-boot"


# ---------------------------------------------------------------------------
# Revision dataclass + initial state
# ---------------------------------------------------------------------------


def test_revision_initial_state():
    engine = PluginEngine(boot_id="b1")
    assert engine.revision_counter == 0
    assert engine.revision == PluginRevision(boot_id="b1", counter=0)


def test_revision_dataclass_equality():
    assert PluginRevision(boot_id="b1", counter=1) == PluginRevision(
        boot_id="b1", counter=1
    )
    assert PluginRevision(boot_id="b1", counter=1) != PluginRevision(
        boot_id="b1", counter=2
    )


# ---------------------------------------------------------------------------
# Swap ordering — manifest removed BEFORE allowlist rebuild
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_swap_ordering_manifest_removed_before_allowlist(tmp_path, monkeypatch):
    engine = PluginEngine(hook_bus=HookBus())
    d = _write_plugin(tmp_path, "swappkg", SWAP_CLASS_CODE)
    await engine._registry.scan(d)
    manifest = engine._registry.get_manifest("swappkg")

    calls: list[str] = []
    orig_remove = engine._swap_remove_manifest
    orig_rebuild = engine._swap_rebuild_allowlist

    def rec_remove(removed: str | None) -> None:
        calls.append(f"remove:{removed}")
        return orig_remove(removed)

    def rec_rebuild() -> None:
        calls.append("rebuild")
        return orig_rebuild()

    monkeypatch.setattr(engine, "_swap_remove_manifest", rec_remove)
    monkeypatch.setattr(engine, "_swap_rebuild_allowlist", rec_rebuild)

    await engine._load("swappkg", manifest, d)
    assert calls == ["rebuild"]  # nothing to remove on load

    calls.clear()
    await engine.unload_plugin("swappkg")
    assert calls == ["remove:swappkg", "rebuild"]


# ---------------------------------------------------------------------------
# Build-then-swap, serve-then-swap (no flicker)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_swap_happens_between_build_and_serve(tmp_path, monkeypatch):
    engine = PluginEngine(hook_bus=HookBus())
    d = _write_plugin(tmp_path, "swappkg", SWAP_CLASS_CODE)
    await engine._registry.scan(d)
    manifest = engine._registry.get_manifest("swappkg")

    seen: dict[str, bool] = {}
    orig = engine._swap_registry

    async def spy(*, removed: str | None = None) -> None:
        seen["built"] = "swappkg" in engine._instances
        seen["served"] = "swappkg" in engine.loaded_plugins
        await orig(removed=removed)

    monkeypatch.setattr(engine, "_swap_registry", spy)

    await engine._load("swappkg", manifest, d)

    assert seen["built"] is True  # instance exists BEFORE the swap
    assert seen["served"] is False  # not yet observable as active DURING swap
    assert "swappkg" in engine.loaded_plugins  # served right AFTER


# ---------------------------------------------------------------------------
# Revision counter across load/unload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_bumps_revision_and_serves_manifest(tmp_path):
    engine = PluginEngine(hook_bus=HookBus())
    assert engine.revision_counter == 0

    d = _write_plugin(tmp_path, "swappkg", SWAP_CLASS_CODE)
    await _load_pkg(engine, d, "swappkg")

    assert engine.revision_counter == 1
    assert engine.revision == PluginRevision(
        boot_id=engine.boot_id, counter=1
    )
    allowlist = engine.get_command_allowlist()
    assert "swappkg.list_items" in allowlist
    assert allowlist["swappkg.list_items"].plugin_id == "swappkg"
    served = engine.get_served_manifest("swappkg")
    assert served is not None
    assert served.schema_version == 2
    assert "swappkg" in engine.get_served_manifests()


@pytest.mark.asyncio
async def test_unload_bumps_revision_and_drops_manifest(tmp_path):
    engine = PluginEngine(hook_bus=HookBus())
    d = _write_plugin(tmp_path, "swappkg", SWAP_CLASS_CODE)
    await _load_pkg(engine, d, "swappkg")
    assert engine.revision_counter == 1

    await engine.unload_plugin("swappkg")

    assert engine.revision_counter == 2
    assert engine.get_served_manifest("swappkg") is None
    assert engine.get_command_allowlist() == {}
    assert engine.loaded_plugins == []


# ---------------------------------------------------------------------------
# D4 — sandbox flag gates ROUTING only, never registry state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sandbox_disabled_still_populates_registry_state(tmp_path):
    engine = PluginEngine(hook_bus=HookBus())
    engine._sandbox = False
    # No "trusted" flag → resolve_loader says sandbox; global sandbox=False
    # forces class_based, but the served manifest + allowlist must be built.
    d = _write_plugin(
        tmp_path,
        "swappkg",
        SWAP_CLASS_CODE,
        manifest={"id": "swappkg", "name": "Swap", "version": "1.0.0"},
    )
    await _load_pkg(engine, d, "swappkg")

    assert "swappkg.list_items" in engine.get_command_allowlist()
    assert engine.get_served_manifest("swappkg") is not None
    assert engine.loaded_plugins == ["swappkg"]


# ---------------------------------------------------------------------------
# Scan-time V2 shadow (PluginRegistry seam)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_shadows_v2_only_manifest(tmp_path):
    """A V2 manifest that V1 rejects (no 'name') must still shadow."""
    reg = PluginRegistry()
    d = _write_plugin(
        tmp_path,
        "v2only",
        "x = 1",
        manifest={"schema_version": 2, "id": "v2only", "version": "1.0.0"},
    )
    await reg.scan(d)

    v2 = reg.get_v2_manifest("v2only")
    assert v2 is not None
    assert v2.schema_version == 2
    assert reg.get_manifest("v2only") is None  # no V1 shadow
    assert reg.get_errors() == {}


@pytest.mark.asyncio
async def test_scan_shadows_v2_alongside_valid_v1(tmp_path):
    reg = PluginRegistry()
    d = _write_plugin(
        tmp_path,
        "dual",
        "x = 1",
        manifest={"id": "dual", "name": "Dual", "version": "1.0.0", "trusted": True},
    )
    await reg.scan(d)

    assert reg.get_manifest("dual") is not None  # V1 discovery intact
    v2 = reg.get_v2_manifest("dual")
    assert v2 is not None
    assert v2.schema_version == 2
    assert reg.get_errors() == {}


@pytest.mark.asyncio
async def test_scan_rejects_invalid_v2_with_error(tmp_path):
    reg = PluginRegistry()
    d = _write_plugin(
        tmp_path,
        "badv2",
        "x = 1",
        manifest={
            "schema_version": 2,
            "id": "badv2",
            "version": "1.0.0",
            "bogus_field": 1,  # extra="forbid" → V2 must reject
        },
    )
    await reg.scan(d)

    assert reg.get_v2_manifest("badv2") is None
    assert "badv2" in reg.get_errors()


# ---------------------------------------------------------------------------
# Served pages projection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_served_pages_projection(tmp_path):
    engine = PluginEngine(hook_bus=HookBus())
    d = _write_plugin(
        tmp_path,
        "swappkg",
        SWAP_CLASS_CODE,
        manifest={
            "id": "swappkg",
            "name": "Swap",
            "version": "1.0.0",
            "trusted": True,
            "pages": [
                {
                    "id": "main",
                    "title": "Main",
                    "component": "MainView",
                    "sidebar": True,
                }
            ],
        },
    )
    await _load_pkg(engine, d, "swappkg")

    pages = engine.get_served_pages()
    assert len(pages) == 1
    p = pages[0]
    assert p["id"] == "main"
    assert p["plugin_id"] == "swappkg"
    assert p["route"] == "/plugins/swappkg/main"
    assert p["icon"] is None  # V1 pages carry no icon; projection adds the key

    # The legacy PageRegistry received the same projection (strangler parity)
    reg_pages = engine.page_registry.get_all_pages()
    assert any(pp["route"] == "/plugins/swappkg/main" for pp in reg_pages)
