from __future__ import annotations

"""
Vigile — Plugin Manifest Model

Pydantic v2 model describing a plugin's declarative manifest: identity,
routes, hooks, database tables, scheduled tasks, and compatibility.

A manifest is the contract the PluginManager reads to register a plugin's
contributions without executing plugin code at load time. The
`manifest_hash` property yields a deterministic SHA-256 of the canonical
JSON serialization, used for integrity tracking and cache busting.
"""

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class RouteSpec(BaseModel):
    """A single HTTP route contributed by the plugin."""

    path: str = Field(..., description="URL path, e.g. '/api/widgets/foo'")
    method: str = Field(..., description="HTTP method, e.g. 'GET'")
    handler: str = Field(
        ...,
        description="Dotted import path of the handler callable, e.g. 'master.plugins.foo.views.list'",
    )
    roles: list[str] = Field(
        default_factory=list,
        description="Roles allowed to call this route. Empty list = public.",
    )


class ColumnSpec(BaseModel):
    """A column declaration for a plugin-managed SQLite table."""

    name: str = Field(..., description="Column name")
    type: str = Field(..., description="SQLite column type, e.g. 'TEXT', 'INTEGER'")
    pk: bool = Field(default=False, description="Whether this column is part of the PRIMARY KEY")
    not_null: bool = Field(default=False, description="NOT NULL constraint")
    # SQLite defaults can be literals, expressions, or null. Any is intentional.
    default: Any = Field(default=None, description="Default value (Pydantic Any)")


class ScheduleSpec(BaseModel):
    """A scheduled task contributed by the plugin."""

    name: str = Field(..., description="Unique schedule name within the plugin")
    interval_secs: int = Field(
        ...,
        ge=1,
        description="Interval between runs in seconds. Must be >= 1.",
    )
    handler: str = Field(
        ...,
        description="Dotted import path of the async handler callable",
    )


class ManifestPage(BaseModel):
    """A UI page contributed by a plugin, consumed by PageRegistry for route registration."""

    id: str = Field(..., description="Page identifier, used to build the route slug")
    title: str = Field(..., min_length=1, description="Human-readable page title")
    component: str = Field(..., description="React component name to render for this page")
    sidebar: bool = Field(default=False, description="Whether to show this page in the sidebar")
    params: list[str] = Field(
        default_factory=list,
        description="Dynamic route parameters, e.g. ['containerId']",
    )
    roles: list[str] = Field(
        default_factory=list,
        description="Roles allowed to view this page. Empty list = public.",
    )


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


class ConfigFieldSpec(BaseModel):
    """
    A single configurable field declared inside a plugin's config_schema.

    Manifests use two shapes:
      - flat:    {field_name: ConfigFieldSpec, ...}
      - wrapper: {name, description, category, schema: {field_name: ConfigFieldSpec, ...}}

    Both shapes are accepted; the frontend PluginConfigForm is responsible for
    reading whichever shape the plugin declares. This model normalizes the leaf
    field descriptor so backend-side validation still rejects malformed leaves.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    type: str = Field(..., description="Field type: string|integer|boolean|number|enum")
    title: str | None = Field(default=None, description="Human-readable label")
    description: str | None = Field(default=None, description="Optional help text")
    default: Any = Field(default=None, description="Default value when unset")
    # Some manifests add an inner `name`/`category` for grouping — allow extras.


class PluginManifest(BaseModel):
    """
    Declarative manifest describing a Vigile plugin.

    Captures everything the PluginManager needs to register a plugin's
    contributions (routes, hooks, schema, schedules) without executing
    plugin code at load time. Validation enforces stable identity and
    semantic versioning so manifests are reproducible and comparable.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    schema_version: int | None = Field(
        default=None,
        description="Optional schema version (1 for legacy, 2 for V2 declarative manifest)",
    )
    id: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_]+$",
        description="Stable plugin identifier. Lowercase, starts with a letter.",
    )
    name: str = Field(..., min_length=1, description="Human-readable plugin name")
    version: str = Field(
        ...,
        pattern=r"^\d+\.\d+\.\d+$",
        description="Semantic version, MAJOR.MINOR.PATCH",
    )
    author: str | None = Field(default=None, description="Optional author name")
    description: str | None = Field(default=None, description="Optional short description")
    description_short: str | None = Field(
        default=None, description="Optional one-line tagline used in the plugin registry."
    )
    icon: str | None = Field(default=None, description="Optional icon name or URL")
    loader: str | None = Field(default=None, description="Optional loader strategy ('class_based' or 'legacy')")
    category: str | None = Field(
        default=None, description="Optional high-level grouping (e.g. 'Maintenance', 'Media', 'containers')"
    )
    routes: list[RouteSpec] = Field(
        default_factory=list,
        description="HTTP routes contributed by the plugin",
    )
    hooks: list[str] = Field(
        default_factory=list,
        description="Hook names the plugin subscribes to, e.g. 'on_node_connect'",
    )
    database: dict[str, list[ColumnSpec]] = Field(
        default_factory=dict,
        description="Map of table_name -> list of column declarations",
    )
    scheduler: list[ScheduleSpec] = Field(
        default_factory=list,
        description="Scheduled tasks contributed by the plugin",
    )
    pages: list[ManifestPage] = Field(
        default_factory=list,
        description="UI pages contributed by the plugin",
    )
    # Plugin-defined copilot actions: action_name -> {risk_level, target_resolver?, ...}
    copilot_actions: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Copilot intents this plugin contributes (action name -> metadata)",
    )
    # Plugin configuration schema (consumed by the frontend PluginConfigForm).
    # Accepts both flat and wrapper shapes — see ConfigFieldSpec docstring.
    config_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="Plugin configuration schema consumed by the frontend plugin config form",
    )
    min_master_version: str | None = Field(
        default=None,
        description="Optional minimum compatible Master version (semver string)",
    )
    trusted: bool = Field(
        default=False,
        description="If true, plugin runs in-process without sandbox. Reserved for built-in system plugins.",
    )
    # Declared by V1 plugins that contribute external OAuth routes (e.g. plex
    # with "external_auth_domains": ["plex.tv"]). Mirrors PluginManifestV2;
    # the V1→V2 migration (`_migrate_v1_to_v2`) only copies V1-known fields,
    # so the engine reads this both from the V1 manifest (V1 parse path) and
    # via `_attach_raw_extras` on the V2 shadow — keeping a V1 manifest with
    # this field loadable (not demoted to V2-only/unreachable by `load_plugin`).
    external_auth_domains: list[str] | None = Field(
        default=None,
        description="External auth domains allowed for this plugin's POST routes (e.g. ['plex.tv']).",
    )

    @property
    def manifest_hash(self) -> str:
        """
        Deterministic SHA-256 of the canonical manifest serialization.

        Produces a stable digest regardless of field insertion order by
        dumping the model to a dict and serializing with ``sort_keys=True``.
        Pydantic 2.9's ``model_dump_json`` does not accept ``sort_keys``,
        so we canonicalize via ``json.dumps`` on the mode='json' dump,
        which renders nested models as plain JSON-compatible mappings.
        """
        payload = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# V2 meta-schema (declarative manifest contract)
# ---------------------------------------------------------------------------
# Versioned declarative contract of the plugin-engine migration. Two
# hostile-input layers, fail-closed: the raw pre-pass caps size/depth before
# any Pydantic parsing, and extra="forbid" rejects unknown fields at every
# nesting level. V1 remains untouched (registry routes on schema_version).


MAX_MANIFEST_V2_BYTES = 64 * 1024  # 64 KB raw JSON size cap
MAX_MANIFEST_V2_DEPTH = 5  # max JSON nesting levels (root = level 1)


def _max_json_depth(value: Any, level: int = 1) -> int:
    """Deepest nesting level reached by any value in a JSON-like structure.

    The root container is level 1; each nested dict/list adds one level.
    """
    if isinstance(value, dict):
        children = [_max_json_depth(v, level + 1) for v in value.values()]
    elif isinstance(value, list):
        children = [_max_json_depth(v, level + 1) for v in value]
    else:
        return level
    return max([level, *children])


def validate_manifest_v2_raw(json_bytes: bytes) -> dict:
    """
    Pre-pass validation of raw V2 manifest JSON before Pydantic parsing.

    Guards the parser against hostile payloads, fail-closed:
      - size cap: 64 KB max (``MAX_MANIFEST_V2_BYTES``)
      - must parse as a JSON object
      - nesting depth cap: 5 levels max (``MAX_MANIFEST_V2_DEPTH``)

    Returns the parsed dict, or raises ValueError with a descriptive message.
    """
    if len(json_bytes) > MAX_MANIFEST_V2_BYTES:
        raise ValueError(
            f"Manifest JSON exceeds the {MAX_MANIFEST_V2_BYTES}-byte size limit"
        )
    try:
        data = json.loads(json_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
        raise ValueError(f"Manifest JSON is not parseable: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Manifest JSON must be a JSON object")
    if _max_json_depth(data) > MAX_MANIFEST_V2_DEPTH:
        raise ValueError(
            f"Manifest JSON nesting exceeds the {MAX_MANIFEST_V2_DEPTH}-level depth limit"
        )
    return data


class RouteV2(BaseModel):
    """A single HTTP route contributed by a V2 plugin (declarative)."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., description="URL path, e.g. '/api/widgets/foo'")
    method: str = Field(..., description="HTTP method, e.g. 'GET'")
    handler: str = Field(
        ...,
        description="Dotted import path of the handler callable",
    )
    roles: list[str] = Field(
        default_factory=list,
        description="Roles allowed to call this route. Empty list = public.",
    )


class PageV2(BaseModel):
    """A declarative UI page contributed by a V2 plugin."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Page identifier, used to build the route slug")
    title: str = Field(..., min_length=1, description="Human-readable page title")
    component: str = Field(..., description="React component name to render")
    sidebar: bool = Field(default=False, description="Show this page in the sidebar")
    params: list[str] = Field(
        default_factory=list,
        description="Dynamic route parameters, e.g. ['containerId']",
    )
    roles: list[str] = Field(
        default_factory=list,
        description="Roles allowed to view this page. Empty list = public.",
    )


class PermissionV2(BaseModel):
    """A single permission entry declared by a V2 plugin.

    The permission *catalog* is closed and core-owned; a plugin may only
    request membership of catalog entries by name (intersection is applied
    at dispatch time by the permission engine).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        description="Catalog permission id, e.g. 'restart_service'",
    )
    description: str | None = Field(
        default=None, description="Optional human-readable description"
    )


class PluginManifestV2(BaseModel):
    """
    V2 declarative manifest — the meta-schema of the plugin migration.

    Smaller and stricter than V1: no executable-ish declarations (scheduler,
    database, copilot_actions) — only declarative UI pages, routes, config
    schema, permission requests and external auth domains. Every layer is
    fail-closed (extra="forbid") and the raw JSON is pre-filtered by
    ``validate_manifest_v2_raw`` before this model ever sees it.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    schema_version: int = Field(
        default=2,
        description="Meta-schema version. The registry routes on this value.",
    )
    id: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_]+$",
        description="Stable plugin identifier. Lowercase, starts with a letter.",
    )
    version: str = Field(
        ...,
        pattern=r"^\d+\.\d+\.\d+$",
        description="Semantic version, MAJOR.MINOR.PATCH",
    )
    hooks: list[str] = Field(
        default_factory=list,
        description="Hook names the plugin subscribes to, e.g. 'on_node_connect'",
    )
    pages: list[PageV2] = Field(
        default_factory=list,
        description="Declarative UI pages contributed by the plugin",
    )
    routes: list[RouteV2] = Field(
        default_factory=list,
        description="Declarative HTTP routes contributed by the plugin",
    )
    config_schema: dict | None = Field(
        default=None,
        description="Plugin configuration schema consumed by the frontend config form",
    )
    permissions: list[PermissionV2] | None = Field(
        default=None,
        description="Permission entries this plugin requests from the core catalog",
    )
    external_auth_domains: list[str] | None = Field(
        default=None,
        description=(
            "External domains the plugin may open in an auth popup "
            "(e.g. ['plex.tv']); validated against the core allowlist"
        ),
    )


# ---------------------------------------------------------------------------
# Meta-schema registry & data migrator
# ---------------------------------------------------------------------------
# One canonical registry {schema_version -> model class}; the loader routes on
# ``schema_version`` (default 1 when absent), migrates legacy shapes forward,
# and always validates against the V2 meta-schema. No in-place dual-shape:
# V1 stays available in the registry for legacy consumers, V2 is canonical.

META_SCHEMA_REGISTRY: dict[int, type[BaseModel]] = {
    1: PluginManifest,
    2: PluginManifestV2,
}

# PageV2 accepts exactly these fields (extra="forbid"); V1-only page fields
# (icon, route, ...) are deliberately not carried over.
_PAGE_V2_FIELDS = ("id", "title", "component", "sidebar", "params", "roles")


def _migrate_v1_page(page: Any) -> Any:
    """Map one V1 page dict to the PageV2 field set (unknowns dropped)."""
    if not isinstance(page, dict):
        return page  # let Pydantic reject non-object pages with a clear error
    return {field: page[field] for field in _PAGE_V2_FIELDS if field in page}


def _migrate_v1_to_v2(data: dict) -> dict:
    """Transform a raw V1 manifest dict into V2 shape.

    V1 fields preserved: id, version, hooks, routes, config_schema, pages
    (PageV2 field set). V1-only declarations (name, author, trusted, loader,
    category, icon, description*, min_master_version, database, scheduler,
    copilot_actions) are intentionally NOT carried over: V2 is the stricter
    declarative meta-schema (no executable-ish declarations) and every V2
    model rejects unknown fields (extra="forbid").
    """
    v2: dict[str, Any] = {"schema_version": 2}
    for key in ("id", "version", "hooks", "routes", "config_schema", "permissions", "external_auth_domains"):
        if key in data:
            v2[key] = data[key]
    if "pages" in data:
        pages = data["pages"]
        v2["pages"] = (
            [_migrate_v1_page(p) for p in pages] if isinstance(pages, list) else pages
        )
    return v2


def migrate_manifest(data: dict, from_version: int, to_version: int) -> dict:
    """Migrate a raw manifest dict between meta-schema versions.

    Only forward migrations between registry versions are supported; same
    version returns a copy (no aliasing). Unknown versions or unsupported
    paths raise ValueError with the known versions listed.
    """
    if not isinstance(data, dict):
        raise ValueError("Manifest data must be a JSON object (dict)")
    for version in (from_version, to_version):
        if version not in META_SCHEMA_REGISTRY:
            raise ValueError(
                f"Unknown manifest schema version {version!r}; "
                f"known versions: {sorted(META_SCHEMA_REGISTRY)}"
            )
    if from_version == to_version:
        return dict(data)
    if (from_version, to_version) == (1, 2):
        return _migrate_v1_to_v2(data)
    raise ValueError(
        f"No migration path from manifest schema version "
        f"{from_version} to {to_version}"
    )


def load_and_validate_manifest(raw: dict) -> PluginManifestV2:
    """Auto-detect the manifest schema version, migrate if needed, validate.

    - Missing ``schema_version`` is treated as V1 (the legacy shape).
    - V1 manifests are migrated forward to V2, then validated.
    - V2 manifests validate directly (no modification).
    - Unknown/non-integer versions raise ValueError (fail-closed).
    """
    if not isinstance(raw, dict):
        raise ValueError("Manifest must be a JSON object (dict)")
    if "schema_version" not in raw:
        schema_version = 1
    else:
        schema_version = raw["schema_version"]
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ValueError(
            f"Manifest schema_version must be an integer, "
            f"got {type(schema_version).__name__}"
        )
    if schema_version not in META_SCHEMA_REGISTRY:
        raise ValueError(
            f"Unknown manifest schema version {schema_version!r}; "
            f"known versions: {sorted(META_SCHEMA_REGISTRY)}"
        )
    if schema_version == 2:
        return PluginManifestV2.model_validate(raw)
    return PluginManifestV2.model_validate(migrate_manifest(raw, 1, 2))


def project_legacy_pages(
    v2: PluginManifestV2, v1_pages: list[dict] | None = None
) -> list[dict]:
    """Derive the V1 legacy pages[] format from a V2 manifest.

    The strangler migration keeps ``GET /api/plugins/pages`` (V1 API) and the
    legacy PluginRouter fed from one canonical registry: the V2 manifest.
    PageV2 drops V1-only page extras (icon) by design (extra="forbid"), so
    V1-only values are merged back from the caller-supplied original V1
    ``pages[]`` (the migration source), matched by page ``id``.

    Output reproduces ``PageRegistry.get_all_pages()`` exactly (id, title,
    component, sidebar, params, roles, plugin_id, route) plus ``icon``
    (None when the V1 side has none). ``route`` is always computed as
    ``/plugins/{plugin_id}/{page_id}`` + ``/:{param}`` per param — the
    frontend PluginRouter contract (``replace('/plugins/', '')``) — never
    taken from a raw V1 ``route`` field.
    """
    v1_by_id: dict[str, dict] = {}
    for page in v1_pages or []:
        if isinstance(page, dict) and isinstance(page.get("id"), str):
            v1_by_id[page["id"]] = page

    result: list[dict] = []
    for page in v2.pages:
        v1 = v1_by_id.get(page.id, {})
        route = f"/plugins/{v2.id}/{page.id}"
        for param in page.params:
            route += f"/:{param}"
        result.append(
            {
                "id": page.id,
                "title": page.title,
                "icon": v1.get("icon"),
                "sidebar": page.sidebar,
                "component": page.component,
                "params": list(page.params),
                "roles": list(page.roles),
                "plugin_id": v2.id,
                "route": route,
            }
        )
    return result
