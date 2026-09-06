from __future__ import annotations

"""
Tests for master.core.plugin_manifest.PluginManifestV2 and the raw pre-pass
validator `validate_manifest_v2_raw`.

The V2 meta-schema is the declarative manifest contract introduced by the
plugin-engine migration. Two defense layers are tested:

1. Pre-pass on raw JSON bytes (hostile input, fail-closed):
   - size cap 64 KB
   - JSON parseable
   - nesting depth <= 5
2. Pydantic v2 model validation (extra="forbid" everywhere, required fields,
   id/version patterns).
"""

import json

import pytest
from pydantic import ValidationError

from master.core.plugin_engine import PageRegistry
from master.core.plugin_manifest import (
    MAX_MANIFEST_V2_BYTES,
    META_SCHEMA_REGISTRY,
    ManifestPage,
    PluginManifest,
    PluginManifestV2,
    load_and_validate_manifest,
    migrate_manifest,
    project_legacy_pages,
    validate_manifest_v2_raw,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_manifest_dict() -> dict:
    """Return a fully-populated, valid V2 manifest as a plain dict."""
    return {
        "schema_version": 2,
        "id": "widget_manager",
        "version": "1.2.3",
        "hooks": ["on_node_connect", "on_plugin_page_load"],
        "pages": [
            {
                "id": "widgets",
                "title": "Widgets",
                "component": "WidgetAdmin",
                "sidebar": True,
                "params": ["containerId"],
                "roles": ["admin"],
            }
        ],
        "routes": [
            {
                "path": "/api/widgets",
                "method": "GET",
                "handler": "master.plugins.widget_manager.views.list",
                "roles": ["admin", "operator"],
            }
        ],
        "config_schema": {
            "enabled": {"type": "boolean", "title": "Enabled"},
            "refresh_interval": {"type": "integer", "default": 60},
        },
        "permissions": [
            {"name": "restart_service", "description": "Restart a service"},
        ],
        "external_auth_domains": ["plex.tv"],
    }


def _manifest_of_exact_size(target: int) -> bytes:
    """Serialize a valid V2 manifest padded to exactly `target` bytes.

    The padding lives in ``config_schema.blob`` (plain 'x' chars, no JSON
    escaping), so the byte length is strictly linear in the blob length and
    the loop converges in two iterations.
    """
    manifest = _valid_manifest_dict()
    manifest["config_schema"] = {"blob": ""}
    for _ in range(10):
        data = json.dumps(manifest).encode("utf-8")
        delta = target - len(data)
        if delta == 0:
            return data
        blob_len = max(0, len(manifest["config_schema"]["blob"]) + delta)
        manifest["config_schema"]["blob"] = "x" * blob_len
    raise AssertionError("Could not reach exact target size")


# ---------------------------------------------------------------------------
# Valid manifests
# ---------------------------------------------------------------------------


def test_valid_v2_manifest_accepted():
    """A fully-populated V2 manifest validates and exposes all fields."""
    manifest = PluginManifestV2.model_validate(_valid_manifest_dict())

    assert manifest.schema_version == 2
    assert manifest.id == "widget_manager"
    assert manifest.version == "1.2.3"
    assert manifest.hooks == ["on_node_connect", "on_plugin_page_load"]

    assert len(manifest.pages) == 1
    page = manifest.pages[0]
    assert page.id == "widgets"
    assert page.title == "Widgets"
    assert page.component == "WidgetAdmin"
    assert page.sidebar is True
    assert page.params == ["containerId"]
    assert page.roles == ["admin"]

    assert len(manifest.routes) == 1
    route = manifest.routes[0]
    assert route.path == "/api/widgets"
    assert route.method == "GET"
    assert route.handler == "master.plugins.widget_manager.views.list"
    assert route.roles == ["admin", "operator"]

    assert manifest.config_schema["enabled"] == {"type": "boolean", "title": "Enabled"}

    assert len(manifest.permissions) == 1
    assert manifest.permissions[0].name == "restart_service"
    assert manifest.permissions[0].description == "Restart a service"

    assert manifest.external_auth_domains == ["plex.tv"]


def test_prepass_returns_parsed_dict():
    """The raw pre-pass parses valid JSON bytes back into a dict."""
    parsed = validate_manifest_v2_raw(json.dumps(_valid_manifest_dict()).encode())

    assert isinstance(parsed, dict)
    assert parsed["id"] == "widget_manager"
    assert parsed["schema_version"] == 2


def test_valid_manifest_roundtrip():
    """Raw bytes -> pre-pass dict -> Pydantic model."""
    raw = json.dumps(_valid_manifest_dict()).encode()
    manifest = PluginManifestV2.model_validate(validate_manifest_v2_raw(raw))

    assert manifest.id == "widget_manager"
    assert manifest.schema_version == 2


def test_schema_version_defaults_to_2():
    """schema_version is optional and defaults to 2."""
    manifest = PluginManifestV2(id="widget", version="1.0.0")
    assert manifest.schema_version == 2


def test_minimal_v2_manifest():
    """Only id + version are required; lists default empty, optionals None."""
    manifest = PluginManifestV2(id="widget", version="1.0.0")

    assert manifest.hooks == []
    assert manifest.pages == []
    assert manifest.routes == []
    assert manifest.config_schema is None
    assert manifest.permissions is None
    assert manifest.external_auth_domains is None


# ---------------------------------------------------------------------------
# Missing / invalid required fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["id", "version"])
def test_missing_required_field_rejected(missing):
    """Removing any required field must raise ValidationError."""
    data = _valid_manifest_dict()
    del data[missing]
    with pytest.raises(ValidationError):
        PluginManifestV2.model_validate(data)


@pytest.mark.parametrize(
    "bad_id",
    ["WidgetManager", "1widget", "widget-manager", "widget!", "", "w"],
)
def test_invalid_plugin_id_rejected(bad_id):
    """V2 keeps the V1 stable-id pattern ^[a-z][a-z0-9_]+$."""
    data = _valid_manifest_dict()
    data["id"] = bad_id
    with pytest.raises(ValidationError):
        PluginManifestV2.model_validate(data)


@pytest.mark.parametrize("bad_version", ["1.0", "v1.0.0", "1.0.0-beta", ""])
def test_invalid_version_rejected(bad_version):
    """V2 keeps the V1 semver pattern ^\\d+\\.\\d+\\.\\d+$."""
    data = _valid_manifest_dict()
    data["version"] = bad_version
    with pytest.raises(ValidationError):
        PluginManifestV2.model_validate(data)


# ---------------------------------------------------------------------------
# extra="forbid"
# ---------------------------------------------------------------------------


def test_unknown_top_level_field_rejected():
    """Unknown top-level fields are rejected (extra='forbid')."""
    data = _valid_manifest_dict()
    data["unexpected"] = "boom"
    with pytest.raises(ValidationError):
        PluginManifestV2.model_validate(data)


def test_unknown_page_field_rejected():
    """Unknown fields inside a page definition are rejected."""
    data = _valid_manifest_dict()
    data["pages"][0]["bogus"] = True
    with pytest.raises(ValidationError):
        PluginManifestV2.model_validate(data)


def test_unknown_route_field_rejected():
    """Unknown fields inside a route definition are rejected."""
    data = _valid_manifest_dict()
    data["routes"][0]["bogus"] = True
    with pytest.raises(ValidationError):
        PluginManifestV2.model_validate(data)


def test_unknown_permission_field_rejected():
    """Unknown fields inside a permission entry are rejected."""
    data = _valid_manifest_dict()
    data["permissions"][0]["bogus"] = True
    with pytest.raises(ValidationError):
        PluginManifestV2.model_validate(data)


# ---------------------------------------------------------------------------
# Pre-pass: size cap
# ---------------------------------------------------------------------------


def test_exact_64kb_boundary_accepted():
    """A manifest of exactly 64 KB passes the size cap."""
    raw = _manifest_of_exact_size(MAX_MANIFEST_V2_BYTES)

    assert len(raw) == MAX_MANIFEST_V2_BYTES
    manifest = PluginManifestV2.model_validate(validate_manifest_v2_raw(raw))
    assert manifest.id == "widget_manager"


def test_oversized_json_rejected():
    """A manifest over 64 KB is rejected by the pre-pass before Pydantic."""
    raw = _manifest_of_exact_size(MAX_MANIFEST_V2_BYTES + 1)

    with pytest.raises(ValueError, match="size limit"):
        validate_manifest_v2_raw(raw)


# ---------------------------------------------------------------------------
# Pre-pass: parseability
# ---------------------------------------------------------------------------


def test_invalid_json_rejected():
    """Malformed JSON is rejected with ValueError."""
    with pytest.raises(ValueError, match="parseable"):
        validate_manifest_v2_raw(b'{"id": "broken"')


def test_non_object_json_rejected():
    """A JSON array (not an object) is rejected."""
    with pytest.raises(ValueError, match="object"):
        validate_manifest_v2_raw(b'[1, 2, 3]')


# ---------------------------------------------------------------------------
# Pre-pass: nesting depth
# ---------------------------------------------------------------------------


def _nest(depth: int) -> dict:
    """Build a nested dict with `depth` dict containers under the value."""
    nested: dict = {"a": {}}
    for _ in range(depth - 1):
        nested = {"a": nested}
    return nested


def test_depth_5_accepted():
    """Nesting depth exactly 5 (root + 4 containers) is accepted.

    config_schema sits at level 2, so 3 nested 'a' containers reach level 5.
    """
    data = _valid_manifest_dict()
    data["config_schema"] = _nest(3)

    parsed = validate_manifest_v2_raw(json.dumps(data).encode())
    assert isinstance(parsed, dict)


def test_deep_json_rejected():
    """Nesting depth over 5 is rejected by the pre-pass."""
    data = _valid_manifest_dict()
    data["config_schema"] = _nest(4)

    with pytest.raises(ValueError, match="depth"):
        validate_manifest_v2_raw(json.dumps(data).encode())


# ---------------------------------------------------------------------------
# Meta-schema registry & V1→V2 migration (J1-T2)
# ---------------------------------------------------------------------------
# Fixtures below are verbatim copies of the real production V1 manifests
# (master/plugins/docker/manifest.json, master/plugins/plex/manifest.json)
# so the round-trip tests exercise genuine V1 shapes: flat config_schema
# (docker), wrapper config_schema (plex), POST routes (plex), page icons
# (dropped by design — PageV2 has no icon field), trusted (backend-only).

_DOCKER_V1 = {
    "id": "docker",
    "name": "Docker Container Orchestrator",
    "version": "1.0.0",
    "author": "Vigile",
    "trusted": True,
    "category": "containers",
    "description_short": "Manage container lifecycles: list, inspect, start, stop, and restart across worker nodes.",
    "hooks": ["get_supported_actions"],
    "copilot_actions": {
        "LIST_CONTAINERS": {"risk_level": "LOW"},
        "RESTART_CONTAINER": {"risk_level": "MEDIUM", "target_resolver": "container_target"},
    },
    "config_schema": {
        "docker_host": {
            "type": "string",
            "title": "Docker Host Socket",
            "default": "unix:///var/run/docker.sock",
            "description": "Unix socket path or TCP endpoint to connect to the Docker daemon.",
        },
        "auto_restart_failed": {
            "type": "boolean",
            "title": "Auto Restart Failed Containers",
            "default": False,
            "description": "Whether the orchestrator should automatically restart containers that exit with a non-zero code.",
        },
    },
    "pages": [
        {
            "id": "containers",
            "title": "Conteneurs",
            "icon": "docker",
            "sidebar": False,
            "component": "DockerContainers",
            "roles": ["admin", "operator"],
        }
    ],
    "routes": [
        {
            "path": "/containers",
            "method": "GET",
            "handler": "list_containers_route",
            "roles": ["admin", "operator"],
        }
    ],
}

_PLEX_V1 = {
    "id": "plex",
    "name": "Plex Media Server Integration",
    "version": "1.0.0",
    "author": "Vigile",
    "trusted": True,
    "description": "Auto-detect Plex Media Server, report active streaming sessions, and diagnose CPU load spikes.",
    "hooks": ["on_status_report", "get_heavy_process_patterns"],
    "pages": [
        {
            "id": "plex",
            "title": "Plex",
            "icon": "play",
            "sidebar": True,
            "component": "PlexAdmin",
            "roles": ["admin", "operator"],
        }
    ],
    "routes": [
        {"path": "/auth/pin", "method": "POST", "handler": "auth_pin_route", "roles": ["admin", "operator"]},
        {"path": "/auth/verify", "method": "POST", "handler": "auth_verify_route", "roles": ["admin", "operator"]},
        {"path": "/servers", "method": "GET", "handler": "servers_route", "roles": ["admin", "operator"]},
        {"path": "/config/server", "method": "POST", "handler": "save_server_config_route", "roles": ["admin", "operator"]},
        {"path": "/{node_id}/detect", "method": "GET", "handler": "detect_route", "roles": ["operator", "viewer"]},
        {"path": "/{node_id}/sessions", "method": "GET", "handler": "sessions_route", "roles": ["operator", "viewer"]},
        {"path": "/{node_id}/library", "method": "GET", "handler": "library_route", "roles": ["operator", "viewer"]},
        {"path": "/{node_id}/users", "method": "GET", "handler": "users_route", "roles": ["operator", "viewer"]},
    ],
    "config_schema": {
        "name": "Plex Media Server",
        "description": "Auto-detects Plex instances, reports active library streaming sessions, and automates load-heavy investigation.",
        "category": "Media",
        "schema": {
            "plex_token": {"type": "string", "title": "Plex Auth Token", "default": "", "description": "Auth token to communicate with Plex API (can be auto-configured via OAuth login)."},
            "plex_server_url": {"type": "string", "title": "Plex Server URL", "default": "", "description": "Selected Plex Server address (e.g. http://192.168.1.50:32400 or leave empty for auto-detection)."},
            "plex_server_name": {"type": "string", "title": "Plex Server Name", "default": "", "description": "Friendly name of the selected Plex server."},
            "plex_port_override": {"type": "integer", "title": "Plex Port Override", "default": 0, "description": "Override detected port (leave 0 for auto-detection or 32400 default)."},
            "cpu_threshold": {"type": "integer", "title": "CPU Threshold (%)", "default": 80, "description": "Alert diagnostic threshold."},
        },
    },
}


def _rich_v1_manifest() -> dict:
    """A V1 manifest carrying every V1-only field (drop coverage)."""
    return {
        "id": "widget_manager",
        "name": "Widget Manager",
        "version": "1.2.3",
        "author": "Vigile Team",
        "description": "A widget management plugin.",
        "description_short": "Manages widgets.",
        "icon": "widgets",
        "loader": "class_based",
        "category": "Maintenance",
        "trusted": True,
        "min_master_version": "0.5.0",
        "hooks": ["on_node_connect"],
        "database": {"widgets": [{"name": "id", "type": "TEXT", "pk": True}]},
        "scheduler": [{"name": "refresh", "interval_secs": 60, "handler": "x.y"}],
        "copilot_actions": {"REBOOT": {"risk_level": "HIGH"}},
        "config_schema": {"enabled": {"type": "boolean", "default": True}},
        "pages": [
            {
                "id": "widgets",
                "title": "Widgets",
                "icon": "widgets",
                "component": "WidgetAdmin",
                "sidebar": True,
                "roles": ["admin"],
            }
        ],
        "routes": [{"path": "/api/widgets", "method": "GET", "handler": "x.y.list", "roles": ["admin"]}],
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_meta_schema_registry_contains_v1_and_v2():
    """The registry maps schema versions to their model classes."""
    assert META_SCHEMA_REGISTRY == {1: PluginManifest, 2: PluginManifestV2}


def test_fixtures_are_valid_v1_manifests():
    """Guard: the real-manifest fixtures genuinely validate as V1."""
    for data in (_DOCKER_V1, _PLEX_V1):
        PluginManifest.model_validate(data)


def test_v1_manifest_accepts_external_auth_domains():
    """T27-BE-2 regression: a V1 manifest declaring ``external_auth_domains``
    — exactly as ``master/plugins/plex/manifest.json`` does — must parse via
    the V1 ``PluginManifest`` directly. V1 fail-closed (``extra='forbid'``)
    must NOT reject the field, otherwise the engine's V1 scan path
    (``PluginManifest(**data)`` at plugin_engine.py:316) falls through to the
    V2-only fallback and the External-Auth flow never sees the manifest.
    """
    v1 = {
        "id": "plex",
        "name": "Plex Media Server Integration",
        "version": "1.0.0",
        "author": "Vigile",
        "trusted": True,
        "description": "Auto-detect Plex Media Server.",
        "external_auth_domains": ["plex.tv"],
        "routes": [],
    }
    manifest = PluginManifest(**v1)
    assert manifest.external_auth_domains == ["plex.tv"]


# ---------------------------------------------------------------------------
# V1→V2 round-trip (real production manifests)
# ---------------------------------------------------------------------------


def test_v1_docker_roundtrip_produces_valid_v2():
    """The real docker V1 manifest migrates to a valid V2 manifest."""
    manifest = load_and_validate_manifest(_DOCKER_V1)

    assert isinstance(manifest, PluginManifestV2)
    assert manifest.schema_version == 2
    assert manifest.id == "docker"
    assert manifest.version == "1.0.0"
    assert manifest.hooks == ["get_supported_actions"]

    assert len(manifest.pages) == 1
    page = manifest.pages[0]
    assert page.id == "containers"
    assert page.title == "Conteneurs"
    assert page.component == "DockerContainers"
    assert page.sidebar is False
    assert page.roles == ["admin", "operator"]

    assert len(manifest.routes) == 1
    route = manifest.routes[0]
    assert route.path == "/containers"
    assert route.method == "GET"
    assert route.handler == "list_containers_route"
    assert route.roles == ["admin", "operator"]

    assert manifest.config_schema["docker_host"]["default"] == "unix:///var/run/docker.sock"
    assert manifest.permissions is None
    assert manifest.external_auth_domains is None


def test_v1_plex_roundtrip_produces_valid_v2():
    """The real plex V1 manifest migrates: POST routes + wrapper config_schema."""
    manifest = load_and_validate_manifest(_PLEX_V1)

    assert manifest.id == "plex"
    assert len(manifest.pages) == 1
    assert manifest.pages[0].component == "PlexAdmin"
    assert manifest.pages[0].sidebar is True

    methods = [r.method for r in manifest.routes]
    assert methods.count("POST") == 3
    assert methods.count("GET") == 5
    assert manifest.routes[0].path == "/auth/pin"

    # Wrapper config_schema shape (name/description/category/schema) survives.
    assert manifest.config_schema["schema"]["plex_token"]["type"] == "string"
    assert manifest.config_schema["category"] == "Media"


def test_migrated_output_validates_against_v2_model():
    """migrate_manifest output validates directly against PluginManifestV2."""
    migrated = migrate_manifest(_DOCKER_V1, from_version=1, to_version=2)
    manifest = PluginManifestV2.model_validate(migrated)
    assert manifest.id == "docker"
    assert manifest.schema_version == 2


def test_migrate_minimal_v1_manifest():
    """A minimal V1 manifest ({id, version}) migrates to a minimal V2 dict."""
    migrated = migrate_manifest({"id": "tiny", "version": "0.1.0"}, 1, 2)
    assert migrated == {"schema_version": 2, "id": "tiny", "version": "0.1.0"}

    manifest = load_and_validate_manifest({"id": "tiny", "version": "0.1.0"})
    assert manifest.id == "tiny"
    assert manifest.hooks == []
    assert manifest.pages == []
    assert manifest.routes == []


# ---------------------------------------------------------------------------
# V1-only fields are dropped (V2 meta-schema is stricter, extra="forbid")
# ---------------------------------------------------------------------------


def test_migrate_drops_v1_only_fields():
    """V1-only declarations never leak into the V2 output."""
    migrated = migrate_manifest(_rich_v1_manifest(), 1, 2)

    for dropped in (
        "name",
        "author",
        "description",
        "description_short",
        "icon",
        "loader",
        "category",
        "trusted",
        "min_master_version",
        "database",
        "scheduler",
        "copilot_actions",
    ):
        assert dropped not in migrated, f"{dropped} must not survive migration"

    assert PluginManifestV2.model_validate(migrated).id == "widget_manager"


def test_migrate_drops_v1_page_extra_fields():
    """PageV2 accepts exactly {id, title, component, sidebar, params, roles};
    V1-only page fields (icon, route, ...) are dropped, not carried over."""
    migrated = migrate_manifest(_rich_v1_manifest(), 1, 2)

    page = migrated["pages"][0]
    assert set(page) == {"id", "title", "component", "sidebar", "roles"}
    assert "icon" not in page


def test_migrate_bad_pages_shape_rejected_by_v2_validation():
    """A non-list pages value survives migration and is rejected by Pydantic."""
    data = dict(_DOCKER_V1)
    data["pages"] = "not-a-list"
    with pytest.raises(ValidationError):
        load_and_validate_manifest(data)


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------


def test_v1_missing_schema_version_autodetected():
    """A manifest without schema_version is treated as V1 and migrated."""
    assert "schema_version" not in _DOCKER_V1
    manifest = load_and_validate_manifest(_DOCKER_V1)
    assert manifest.schema_version == 2
    assert manifest.id == "docker"


def test_explicit_v1_schema_version_accepted():
    """schema_version: 1 is explicit and follows the same migration path."""
    data = dict(_DOCKER_V1)
    data["schema_version"] = 1
    manifest = load_and_validate_manifest(data)
    assert manifest.schema_version == 2


def test_v2_passthrough_unchanged():
    """A V2 manifest validates directly; input dict is not mutated."""
    data = _valid_manifest_dict()
    manifest = load_and_validate_manifest(data)

    assert manifest.schema_version == 2
    assert manifest.model_dump() == data
    assert data["schema_version"] == 2  # input untouched


# ---------------------------------------------------------------------------
# Unknown / invalid versions (fail-closed)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [3, 0, -1, 99])
def test_unknown_schema_version_rejected(bad):
    """Versions outside the registry are rejected with a clear error."""
    data = _valid_manifest_dict()
    data["schema_version"] = bad
    with pytest.raises(ValueError, match="Unknown manifest schema version"):
        load_and_validate_manifest(data)


@pytest.mark.parametrize("bad", ["2", 2.0, None, True])
def test_non_integer_schema_version_rejected(bad):
    """Non-integer schema_version values are rejected (bool is not a version)."""
    data = _valid_manifest_dict()
    data["schema_version"] = bad
    with pytest.raises(ValueError, match="schema_version"):
        load_and_validate_manifest(data)


def test_load_rejects_non_dict():
    """The loader only accepts JSON objects."""
    with pytest.raises(ValueError, match="dict"):
        load_and_validate_manifest(["not", "a", "dict"])


@pytest.mark.parametrize("src,dst", [(3, 2), (0, 1), (1, 3), (2, 1)])
def test_migrate_unknown_or_downgrade_rejected(src, dst):
    """Unknown versions and unsupported paths (e.g. 2→1) raise ValueError."""
    with pytest.raises(ValueError, match="schema version"):
        migrate_manifest({}, src, dst)


def test_migrate_same_version_passthrough():
    """Same-version migration returns an equal copy (no aliasing)."""
    data = _valid_manifest_dict()
    out = migrate_manifest(data, 2, 2)
    assert out == data
    assert out is not data


# ---------------------------------------------------------------------------
# Legacy pages[] projection (J1-T3)
# ---------------------------------------------------------------------------
# project_legacy_pages derives the V1 pages[] format from a V2 manifest so
# GET /api/plugins/pages keeps working during the strangler migration.
# PageV2 drops V1-only page extras (icon) by design; the projection merges
# them back from the caller-supplied original V1 pages[] (migration source),
# matched by page id. Fixtures below are verbatim copies of the remaining
# real production manifests (metrics, systemd) — docker/plex live above.

_METRICS_V1 = {
    "id": "metrics",
    "name": "Metrics Collector",
    "version": "1.0.0",
    "author": "Vigile",
    "trusted": True,
    "description": "Collect and persist CPU, memory, disk, network, and process telemetry from worker nodes.",
    "hooks": [
        "get_supported_actions",
        "normalize_status_report",
        "on_status_report",
    ],
    "database": {
        "metrics_snapshots": [
            {"name": "id", "type": "TEXT", "pk": True},
            {"name": "node_id", "type": "TEXT", "not_null": True},
            {"name": "collected_at", "type": "REAL", "not_null": True},
            {"name": "created_at", "type": "REAL", "not_null": True},
            {"name": "cpu_percent", "type": "REAL"},
            {"name": "cpu_load_1m", "type": "REAL"},
            {"name": "cpu_load_5m", "type": "REAL"},
            {"name": "cpu_load_15m", "type": "REAL"},
            {"name": "cpu_cores", "type": "INTEGER"},
            {"name": "mem_total_bytes", "type": "INTEGER"},
            {"name": "mem_used_bytes", "type": "INTEGER"},
            {"name": "mem_percent", "type": "REAL"},
            {"name": "swap_total_bytes", "type": "INTEGER"},
            {"name": "swap_used_bytes", "type": "INTEGER"},
            {"name": "disk_total_bytes", "type": "INTEGER"},
            {"name": "disk_used_bytes", "type": "INTEGER"},
            {"name": "disk_percent", "type": "REAL"},
            {"name": "uptime_seconds", "type": "REAL"},
            {"name": "processes", "type": "INTEGER"},
            {"name": "disks_json", "type": "TEXT"},
            {"name": "top_processes_json", "type": "TEXT"},
            {"name": "net_bytes_recv", "type": "INTEGER"},
            {"name": "net_bytes_sent", "type": "INTEGER"},
            {"name": "net_packets_recv", "type": "INTEGER"},
            {"name": "net_packets_sent", "type": "INTEGER"},
            {"name": "net_errors_in", "type": "INTEGER"},
            {"name": "net_errors_out", "type": "INTEGER"},
            {"name": "net_drops_in", "type": "INTEGER"},
            {"name": "net_drops_out", "type": "INTEGER"},
            {"name": "disk_reads", "type": "INTEGER"},
            {"name": "disk_writes", "type": "INTEGER"},
            {"name": "disk_read_bytes", "type": "INTEGER"},
            {"name": "disk_write_bytes", "type": "INTEGER"},
            {"name": "temp_celsius", "type": "REAL"},
            {"name": "psi_cpu_avg10", "type": "REAL"},
            {"name": "psi_mem_avg10", "type": "REAL"},
            {"name": "psi_io_avg10", "type": "REAL"},
            {"name": "file_handles_used", "type": "INTEGER"},
            {"name": "file_handles_max", "type": "INTEGER"},
            {"name": "entropy_avail", "type": "INTEGER"},
            {"name": "context_switches", "type": "INTEGER"},
            {"name": "cpu_throttled_count", "type": "INTEGER"},
        ]
    },
    "config_schema": {
        "polling_interval": {
            "type": "integer",
            "title": "Polling Interval (seconds)",
            "default": 60,
            "description": "Frequency of metrics collection reports sent from the worker.",
        },
        "retention_days": {
            "type": "integer",
            "title": "Metrics Retention (days)",
            "default": 30,
            "description": "Number of days to keep historical metrics snapshots in the database.",
        },
    },
    "pages": [
        {
            "id": "history",
            "title": "Historique",
            "icon": "trending",
            "sidebar": True,
            "component": "MetricsHistory",
            "roles": ["admin", "operator", "viewer"],
        }
    ],
    "routes": [
        {
            "path": "/history",
            "method": "GET",
            "handler": "get_metrics_history",
            "roles": ["admin", "operator", "viewer"],
        }
    ],
}

_SYSTEMD_V1 = {
    "id": "systemd",
    "name": "Systemd Service Manager",
    "version": "1.0.0",
    "author": "Vigile",
    "trusted": True,
    "description": "Declare, inspect and restart systemd services across worker nodes. Category: system. Copilot actions: LIST_SERVICES, STATUS_SERVICE, RESTART_SERVICE (all LOW risk).",
    "hooks": ["get_supported_actions"],
    "pages": [
        {
            "id": "services",
            "title": "Services",
            "icon": "activity",
            "sidebar": False,
            "component": "SystemdServices",
            "roles": ["admin", "operator"],
        }
    ],
    "routes": [
        {
            "path": "/services",
            "method": "GET",
            "handler": "list_services_route",
            "roles": ["admin", "operator"],
        }
    ],
}

_ALL_REAL_V1 = {
    "docker": _DOCKER_V1,
    "metrics": _METRICS_V1,
    "systemd": _SYSTEMD_V1,
    "plex": _PLEX_V1,
}


def _current_engine_pages(plugin_id: str, v1_pages: list[dict]) -> list[dict]:
    """Reproduce the CURRENT GET /api/plugins/pages output for V1 pages.

    Mirrors plugin_engine._load: pages are registered as ManifestPage
    model_dumps (icon dropped by Pydantic's default extra='ignore'), then
    PageRegistry.get_all_pages() enriches each entry with plugin_id + route.
    """
    registry = PageRegistry()
    registry.register(
        plugin_id, [ManifestPage.model_validate(p).model_dump() for p in v1_pages]
    )
    return registry.get_all_pages()


def test_projection_fixtures_cover_all_four_real_plugins():
    """Guard: the projection fixtures cover the 4 real production plugins."""
    assert set(_ALL_REAL_V1) == {"docker", "metrics", "systemd", "plex"}


def test_projection_fixtures_are_valid_v1_manifests():
    """Guard: the metrics/systemd fixtures genuinely validate as V1."""
    for data in (_METRICS_V1, _SYSTEMD_V1):
        PluginManifest.model_validate(data)


@pytest.mark.parametrize("plugin_id", ["docker", "metrics", "systemd", "plex"])
def test_projection_matches_current_engine_output(plugin_id):
    """Round-trip v1_pages -> migrate -> project reproduces the CURRENT
    GET /api/plugins/pages shape for every real plugin.

    Every field the engine emits today (id, title, component, sidebar,
    params, roles, plugin_id, route) must be preserved identically; the
    projection adds exactly one field — icon, sourced from the V1 side.
    """
    raw = _ALL_REAL_V1[plugin_id]
    v2 = load_and_validate_manifest(raw)
    projected = project_legacy_pages(v2, v1_pages=raw["pages"])
    current = _current_engine_pages(plugin_id, raw["pages"])

    assert len(projected) == len(current) == len(raw["pages"])
    v1_by_id = {p["id"]: p for p in raw["pages"]}
    for proj, cur in zip(projected, current):
        for key, value in cur.items():
            assert proj[key] == value, f"{plugin_id}: field {key!r} drifted"
        assert set(proj) == set(cur) | {"icon"}
        assert proj["icon"] == v1_by_id[proj["id"]]["icon"]


def test_projection_no_pages_returns_empty_list():
    """A V2 manifest without pages projects to an empty list."""
    v2 = PluginManifestV2(id="bare", version="1.0.0")
    assert project_legacy_pages(v2) == []
    # Stale V1 pages without a V2 counterpart are ignored (V2 is canonical).
    assert project_legacy_pages(v2, v1_pages=[{"id": "ghost", "icon": "x"}]) == []


def test_projection_preserves_required_v1_fields():
    """Every projected entry carries the full V1 field set with V1 values."""
    v2 = load_and_validate_manifest(_DOCKER_V1)
    projected = project_legacy_pages(v2, v1_pages=_DOCKER_V1["pages"])

    assert len(projected) == 1
    entry = projected[0]
    for field in (
        "id",
        "title",
        "icon",
        "route",
        "roles",
        "component",
        "sidebar",
        "params",
        "plugin_id",
    ):
        assert field in entry, f"missing V1 field {field!r}"

    assert entry["id"] == "containers"
    assert entry["title"] == "Conteneurs"
    assert entry["icon"] == "docker"
    assert entry["route"] == "/plugins/docker/containers"
    assert entry["roles"] == ["admin", "operator"]
    assert entry["component"] == "DockerContainers"
    assert entry["sidebar"] is False
    assert entry["params"] == []
    assert entry["plugin_id"] == "docker"


def test_projection_route_includes_params():
    """route = /plugins/{plugin_id}/{page_id} + /:{param} per param."""
    v2 = PluginManifestV2.model_validate(_valid_manifest_dict())
    projected = project_legacy_pages(v2)

    assert projected[0]["route"] == "/plugins/widget_manager/widgets/:containerId"


def test_projection_icon_none_without_v1_pages():
    """Without the V1 side, icon is None (frontend contract: string | null)."""
    v2 = PluginManifestV2.model_validate(_valid_manifest_dict())
    projected = project_legacy_pages(v2)

    assert projected[0]["icon"] is None
    assert projected[0]["route"] == "/plugins/widget_manager/widgets/:containerId"


def test_projection_merges_v1_icon_by_page_id():
    """V1-only page values (icon) are merged onto V2 entries by page id."""
    v2 = PluginManifestV2.model_validate(_valid_manifest_dict())
    projected = project_legacy_pages(v2, v1_pages=[{"id": "widgets", "icon": "widget-icon"}])

    assert projected[0]["icon"] == "widget-icon"


def test_projection_ignores_v1_pages_not_in_v2():
    """V1 pages absent from the V2 manifest are dropped (V2 is canonical)."""
    v2 = load_and_validate_manifest(_DOCKER_V1)
    stale = [{"id": "stale", "icon": "ghost", "component": "Ghost"}]
    projected = project_legacy_pages(v2, v1_pages=_DOCKER_V1["pages"] + stale)

    assert [p["id"] for p in projected] == ["containers"]
