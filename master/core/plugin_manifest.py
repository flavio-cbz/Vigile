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


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


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
    icon: str | None = Field(default=None, description="Optional icon name or URL")
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
