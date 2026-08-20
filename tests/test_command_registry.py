"""
Tests for the code-derived command registry scan (J1-T4).

Ground truth (verified against the plugin sources, 2026-08-13):

| Plugin  | @route count | Routes |
|---------|--------------|--------|
| metrics | 1            | GET /history (roles default → viewer) |
| docker  | 2            | GET /containers + POST /containers/{container_id}/{action} (admin, operator) |
| plex    | 15           | 11 GET + 3 POST + 1 DELETE, incl. /{node_id}/photo, /{node_id}/history, /{node_id}/stats |
| systemd | 2            | GET /services + POST /services/{service_name}/{action} (admin, operator) |

The plex manifest declares only 8 routes (missing /photo, /history, /stats,
/files, /transcodes, /sessions/{session_key}, /library/{section_id}/scan) —
the scan must be code-derived and expose all 15. The docker manifest was
GET-only while the frontend POSTs `/containers/{id}/{action}`
(DockerContainers.tsx:53) — 404 today; U2 added the POST route in code AND
manifest (2026-08-14): the scan now exposes 2 docker entries, the POST one
flagged mutation=True.

J4-T27-BE-1 (2026-08-15): the plex manifest.json was re-synced with the code
— all 15 @route decorators are now declared (photo/history/stats/transcodes/
files/library-scan/sessions-delete added). `test_plex_manifest_matches_code_routes`
locks code == manifest (≥15 each).
"""

from __future__ import annotations

import types

import pytest

from master.core.command_registry import (
    CommandEntry,
    scan_all_routes,
    scan_loaded_engine,
)
from master.core.plugin_base import PluginBase, PluginContext, route


def _make_instance(plugin_cls: type[PluginBase], plugin_id: str) -> PluginBase:
    ctx = PluginContext(plugin_id=plugin_id, config={}, db=None)
    return plugin_cls(ctx)


@pytest.fixture(scope="module")
def builtin_instances() -> dict[str, PluginBase]:
    """Instantiate the 4 built-in plugins without a DB."""
    from master.plugins.metrics import MetricsPlugin
    from master.plugins.docker import DockerPlugin
    from master.plugins.plex import PlexPlugin
    from master.plugins.systemd import SystemdPlugin

    return {
        "metrics": _make_instance(MetricsPlugin, "metrics"),
        "docker": _make_instance(DockerPlugin, "docker"),
        "plex": _make_instance(PlexPlugin, "plex"),
        "systemd": _make_instance(SystemdPlugin, "systemd"),
    }


# ---------------------------------------------------------------------------
# Per-plugin scans
# ---------------------------------------------------------------------------


def test_scan_discovers_metrics_routes(builtin_instances: dict[str, PluginBase]):
    entries = scan_all_routes({"metrics": builtin_instances["metrics"]})
    assert len(entries) == 1
    entry = entries[0]
    assert entry.plugin_id == "metrics"
    assert entry.name == "metrics.get_metrics_history"
    assert entry.method == "GET"
    assert entry.path_template == "/history"
    assert entry.mutation is False
    assert entry.roles == ("viewer",)  # default when @route omits roles
    assert entry.resource_contract == "metrics"


def test_scan_discovers_docker_routes(builtin_instances: dict[str, PluginBase]):
    entries = scan_all_routes({"docker": builtin_instances["docker"]})
    assert len(entries) == 2
    by_path = {(e.method, e.path_template): e for e in entries}
    get_entry = by_path[("GET", "/containers")]
    assert get_entry.name == "docker.list_containers_route"
    assert get_entry.method == "GET"
    assert get_entry.mutation is False
    assert get_entry.roles == ("admin", "operator")
    # U2 (2026-08-14): the frontend POST to /containers/{id}/{action}
    # (DockerContainers.tsx:53) is now backed by a real @route handler —
    # the scan exposes it as a mutation command (POST → mutation=True).
    post_entry = by_path[("POST", "/containers/{container_id}/{action}")]
    assert post_entry.name == "docker.container_action_route"
    assert post_entry.method == "POST"
    assert post_entry.mutation is True
    assert post_entry.roles == ("admin", "operator")
    assert post_entry.resource_contract == "docker"


def test_scan_docker_post_route_is_mutation(builtin_instances: dict[str, PluginBase]):
    """The docker container-action POST route must be flagged mutation=True.

    This is the U2 contract: the command is code-derived with
    method="POST" → mutation=True (command_registry._MUTATING_METHODS),
    so /batch rejects it with 403 and it stays on the ActionProposal channel.
    """
    entries = scan_all_routes({"docker": builtin_instances["docker"]})
    post = next(
        e for e in entries
        if e.path_template == "/containers/{container_id}/{action}"
    )
    assert post.name == "docker.container_action_route"
    assert post.method == "POST"
    assert post.mutation is True
    assert post.roles == ("admin", "operator")


def test_scan_discovers_plex_routes(builtin_instances: dict[str, PluginBase]):
    entries = scan_all_routes({"plex": builtin_instances["plex"]})
    assert len(entries) == 18, (
        f"plex has 18 @route in code vs 11 in manifest; got {len(entries)}: "
        f"{[e.path_template for e in entries]}"
    )

    paths = {(e.method, e.path_template) for e in entries}
    expected = {
        ("GET", "/{node_id}/detect"),
        ("GET", "/{node_id}/sessions"),
        ("DELETE", "/{node_id}/sessions/{session_key}"),  # plex-tabs addition
        ("GET", "/{node_id}/transcodes"),                 # plex-tabs addition
        ("GET", "/{node_id}/files"),                      # plex-tabs addition
        ("POST", "/{node_id}/library/{section_id}/scan"), # plex-tabs addition
        ("GET", "/{node_id}/photo"),                      # missing from manifest
        ("GET", "/{node_id}/library"),
        ("GET", "/{node_id}/users"),
        ("GET", "/{node_id}/history"),                    # missing from manifest
        ("GET", "/{node_id}/stats"),                      # missing from manifest
        ("POST", "/auth/pin"),
        ("POST", "/auth/verify"),
        ("GET", "/auth/status/stream"),                   # T27-BE-2 addition
        ("POST", "/plex.auth.start"),                     # T27-BE-2 addition
        ("POST", "/plex.auth.cancel"),                    # T27-BE-2 addition
        ("GET", "/servers"),
        ("POST", "/config/server"),
    }
    assert paths == expected

    # The 7 mutating routes (6 POST + 1 DELETE) are all flagged mutation=True
    mutations = [e for e in entries if e.mutation]
    assert len(mutations) == 7
    assert {e.path_template for e in mutations} == {
        "/auth/pin",
        "/auth/verify",
        "/plex.auth.start",
        "/plex.auth.cancel",
        "/config/server",
        "/{node_id}/library/{section_id}/scan",
        "/{node_id}/sessions/{session_key}",
    }
    assert all(e.method in ("POST", "DELETE") for e in mutations)

    # Photo proxy is MEDIA/BINARY but read-only
    photo = next(e for e in entries if e.path_template == "/{node_id}/photo")
    assert photo.method == "GET"
    assert photo.mutation is False
    assert photo.roles == ("operator", "viewer")


def test_plex_manifest_matches_code_routes(builtin_instances: dict[str, PluginBase]):
    """J4-T27-BE-1 : le manifest plex déclare désormais TOUTES les routes du code.

    Le manifest.json réel (master/plugins/plex/manifest.json) doit exposer le
    même jeu (method, path) que les @route du code — 15 routes de chaque côté.
    Toute nouvelle route ajoutée au code sans mise à jour du manifest casse ce
    test (sync obligatoire).
    """
    import json as _json
    from pathlib import Path

    manifest_path = (
        Path(__file__).resolve().parents[1] / "master" / "plugins" / "plex" / "manifest.json"
    )
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_routes = {(r["method"], r["path"]) for r in manifest["routes"]}

    code_entries = scan_all_routes({"plex": builtin_instances["plex"]})
    code_routes = {(e.method, e.path_template) for e in code_entries}

    assert len(manifest_routes) >= 15, f"manifest plex: {len(manifest_routes)} routes"
    assert len(code_routes) >= 15, f"code plex: {len(code_routes)} routes"
    assert manifest_routes == code_routes, (
        f"manifest/code désynchronisés — manifest: {sorted(manifest_routes)}, "
        f"code: {sorted(code_routes)}"
    )


def test_docker_manifest_matches_code_routes(builtin_instances: dict[str, PluginBase]):
    """T29 — registry diff test: docker manifest must match code routes."""
    import json as _json
    from pathlib import Path

    manifest_path = (
        Path(__file__).resolve().parents[1] / "master" / "plugins" / "docker" / "manifest.json"
    )
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_routes = {(r["method"], r["path"]) for r in manifest["routes"]}

    code_entries = scan_all_routes({"docker": builtin_instances["docker"]})
    code_routes = {(e.method, e.path_template) for e in code_entries}

    assert manifest_routes == code_routes, (
        f"manifest/code désynchronisés pour docker — manifest: {sorted(manifest_routes)}, "
        f"code: {sorted(code_routes)}"
    )


def test_systemd_manifest_matches_code_routes(builtin_instances: dict[str, PluginBase]):
    """T29 — registry diff test: systemd manifest must match code routes."""
    import json as _json
    from pathlib import Path

    manifest_path = (
        Path(__file__).resolve().parents[1] / "master" / "plugins" / "systemd" / "manifest.json"
    )
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_routes = {(r["method"], r["path"]) for r in manifest["routes"]}

    code_entries = scan_all_routes({"systemd": builtin_instances["systemd"]})
    code_routes = {(e.method, e.path_template) for e in code_entries}

    assert manifest_routes == code_routes, (
        f"manifest/code désynchronisés pour systemd — manifest: {sorted(manifest_routes)}, "
        f"code: {sorted(code_routes)}"
    )


def test_scan_discovers_systemd_routes(builtin_instances: dict[str, PluginBase]):
    entries = scan_all_routes({"systemd": builtin_instances["systemd"]})
    assert len(entries) == 2
    by_path = {(e.method, e.path_template): e for e in entries}
    get_entry = by_path[("GET", "/services")]
    assert get_entry.name == "systemd.list_services_route"
    assert get_entry.method == "GET"
    assert get_entry.mutation is False
    assert get_entry.roles == ("admin", "operator")
    # U2 (2026-08-14): the frontend POST to /services/{service_name}/{action}
    # (SystemdServices.tsx:51) is now backed by a real @route handler —
    # the scan exposes it as a mutation command (POST → mutation=True).
    post_entry = by_path[("POST", "/services/{service_name}/{action}")]
    assert post_entry.name == "systemd.service_action_route"
    assert post_entry.method == "POST"
    assert post_entry.mutation is True
    assert post_entry.roles == ("admin", "operator")
    assert post_entry.resource_contract == "systemd"


def test_scan_systemd_post_route_is_mutation(builtin_instances: dict[str, PluginBase]):
    """The systemd service-action POST route must be flagged mutation=True.

    This is the U2 contract: the command is code-derived with
    method="POST" → mutation=True (command_registry._MUTATING_METHODS),
    so /batch rejects it with 403 and it stays on the ActionProposal channel.
    """
    entries = scan_all_routes({"systemd": builtin_instances["systemd"]})
    post = next(
        e for e in entries
        if e.path_template == "/services/{service_name}/{action}"
    )
    assert post.name == "systemd.service_action_route"
    assert post.method == "POST"
    assert post.mutation is True
    assert post.roles == ("admin", "operator")


def test_scan_all_builtins_totals(builtin_instances: dict[str, PluginBase]):
    entries = scan_all_routes(builtin_instances)
    assert len(entries) == 23  # 1 + 2 + 18 + 2
    by_plugin = {pid: [e for e in entries if e.plugin_id == pid] for pid in ("metrics", "docker", "plex", "systemd")}
    assert len(by_plugin["plex"]) == 18
    assert len(by_plugin["metrics"]) == 1
    assert len(by_plugin["docker"]) == 2
    assert len(by_plugin["systemd"]) == 2


# ---------------------------------------------------------------------------
# Mutation flag semantics
# ---------------------------------------------------------------------------


class _FakePlugin(PluginBase):
    plugin_id = "fake"

    @route("/get", method="GET")
    def get_route(self) -> None:
        pass

    @route("/post", method="POST")
    def post_route(self) -> None:
        pass

    @route("/put", method="PUT")
    def put_route(self) -> None:
        pass

    @route("/delete", method="DELETE")
    def delete_route(self) -> None:
        pass

    @route("/patch", method="PATCH")
    def patch_route(self) -> None:
        pass


@pytest.fixture
def fake_plugin() -> PluginBase:
    yield _make_instance(_FakePlugin, "fake")
    PluginBase._decorated_registry.pop("fake", None)  # don't pollute the engine registry


def test_mutation_flag_for_post_put_delete(fake_plugin: PluginBase):
    entries = scan_all_routes({"fake": fake_plugin})
    by_path = {e.path_template: e for e in entries}
    assert by_path["/get"].mutation is False
    assert by_path["/post"].mutation is True
    assert by_path["/put"].mutation is True
    assert by_path["/delete"].mutation is True
    assert by_path["/patch"].mutation is True
    assert all(e.method in ("GET", "POST", "PUT", "DELETE", "PATCH") for e in entries)


# ---------------------------------------------------------------------------
# Module-level registration shape (legacy register(pm))
# ---------------------------------------------------------------------------


def test_module_level_route_shape():
    module = types.ModuleType("fake_legacy_plugin")

    def legacy_route():
        pass

    legacy_route.__plugin_route__ = {"path": "/legacy", "method": "POST", "roles": ["admin"]}
    module.legacy_route = legacy_route

    entries = scan_all_routes({"legacy": module})
    assert len(entries) == 1
    entry = entries[0]
    assert entry.name == "legacy.legacy_route"
    assert entry.method == "POST"
    assert entry.mutation is True
    assert entry.roles == ("admin",)


def test_metrics_module_level_register_has_no_routes():
    """metrics exposes BOTH shapes: class-based routes + module-level register().

    The module-level register(pm) only subscribes hooks — the scan must not
    fabricate routes from it (the single /history route comes from the class).
    """
    from master.plugins import metrics as metrics_module
    from master.plugins.metrics import MetricsPlugin

    instances = {"metrics": _make_instance(MetricsPlugin, "metrics")}
    modules = {"metrics": metrics_module}
    assert scan_all_routes(modules) == []  # no module-level @route functions
    assert len(scan_all_routes(instances)) == 1


# ---------------------------------------------------------------------------
# Scan semantics
# ---------------------------------------------------------------------------


def test_dedup_on_plugin_path_method(fake_plugin: PluginBase):
    """Same (plugin_id, path, method) from two sources → one entry."""
    module = types.ModuleType("fake_module")
    module.get_route = _FakePlugin.get_route  # same decorated function object
    module.get_route_alias = _FakePlugin.get_route  # re-exported under another name

    entries = scan_all_routes({"fake": module})
    assert len(entries) == 1  # deduplicated, not 2
    assert entries[0].name == "fake.get_route"

    # Instance + module under the same plugin_id also dedupe
    plugins: dict[str, object] = {"fake": fake_plugin}
    plugins["fake"] = module  # module wins the key — still only 1 route
    assert len(scan_all_routes(plugins)) == 1


def test_results_sorted_deterministically(builtin_instances: dict[str, PluginBase]):
    first = scan_all_routes(builtin_instances)
    second = scan_all_routes(builtin_instances)
    assert [(e.plugin_id, e.path_template, e.method) for e in first] == [
        (e.plugin_id, e.path_template, e.method) for e in second
    ]
    keys = [(e.plugin_id, e.path_template, e.method) for e in first]
    assert keys == sorted(keys)


def test_scan_loaded_engine_wrapper(builtin_instances: dict[str, PluginBase]):
    class _FakeEngine:
        _instances = builtin_instances

    entries = scan_loaded_engine(_FakeEngine())
    assert len(entries) == 23

    class _EmptyEngine:
        pass

    assert scan_loaded_engine(_EmptyEngine()) == []


def test_command_entry_is_frozen():
    entry = CommandEntry(
        plugin_id="p",
        name="p.r",
        method="GET",
        path_template="/x",
        mutation=False,
        roles=("viewer",),
        resource_contract="p",
    )
    with pytest.raises(AttributeError):
        entry.name = "p.other"  # type: ignore[misc]
