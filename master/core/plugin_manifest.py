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
