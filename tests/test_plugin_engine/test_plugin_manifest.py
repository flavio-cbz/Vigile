from __future__ import annotations

"""
Tests for master.core.plugin_manifest.PluginManifest.

Covers:
- Valid manifest with all fields populated.
- Missing required fields raise ValidationError.
- Invalid plugin id (violates `^[a-z][a-z0-9_]+$`) raises ValidationError.
- manifest_hash is deterministic: identical content => identical hash, but
  different content => different hash.
"""

import hashlib
import json

import pytest
from pydantic import ValidationError

from master.core.plugin_manifest import (
    ColumnSpec,
    PluginManifest,
    RouteSpec,
    ScheduleSpec,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _full_manifest_kwargs() -> dict:
    """Return kwargs that build a fully-populated, valid PluginManifest."""
    return {
        "id": "widget_manager",
        "name": "Widget Manager",
        "version": "1.0.0",
        "author": "Vigile Team",
        "description": "A widget management plugin.",
        "icon": "widgets",
        "routes": [
            RouteSpec(
                path="/api/widgets",
                method="GET",
                handler="master.plugins.widget_manager.views.list_widgets",
                roles=["admin", "operator"],
            ),
            RouteSpec(
                path="/api/widgets/{widget_id}",
                method="POST",
                handler="master.plugins.widget_manager.views.update_widget",
                roles=["admin"],
            ),
        ],
        "hooks": ["on_node_connect", "on_node_disconnect"],
        "database": {
            "widgets": [
                ColumnSpec(name="id", type="TEXT", pk=True, not_null=True),
                ColumnSpec(name="name", type="TEXT", not_null=True),
                ColumnSpec(name="value", type="INTEGER", not_null=False, default=0),
            ],
        },
        "scheduler": [
            ScheduleSpec(
                name="refresh_widgets",
                interval_secs=60,
                handler="master.plugins.widget_manager.scheduler.refresh",
            ),
        ],
        "min_master_version": "0.5.0",
    }


# ---------------------------------------------------------------------------
# Valid manifest
# ---------------------------------------------------------------------------


def test_valid_full_manifest():
    """A manifest with all fields populated validates and exposes them."""
    m = PluginManifest(**_full_manifest_kwargs())

    assert m.id == "widget_manager"
    assert m.name == "Widget Manager"
    assert m.version == "1.0.0"
    assert m.author == "Vigile Team"
    assert m.description == "A widget management plugin."
    assert m.icon == "widgets"
    assert m.min_master_version == "0.5.0"

    assert len(m.routes) == 2
    assert m.routes[0].path == "/api/widgets"
    assert m.routes[0].method == "GET"
    assert m.routes[0].handler == "master.plugins.widget_manager.views.list_widgets"
    assert m.routes[0].roles == ["admin", "operator"]

    assert m.hooks == ["on_node_connect", "on_node_disconnect"]

    assert "widgets" in m.database
    cols = m.database["widgets"]
    assert len(cols) == 3
    assert cols[0].name == "id"
    assert cols[0].pk is True
    assert cols[0].not_null is True
    assert cols[2].default == 0

    assert len(m.scheduler) == 1
    assert m.scheduler[0].name == "refresh_widgets"
    assert m.scheduler[0].interval_secs == 60


def test_valid_minimal_manifest():
    """Only the required fields are enough; optionals default to None / empty."""
    m = PluginManifest(id="metric", name="Metric", version="0.1.0")

    assert m.author is None
    assert m.description is None
    assert m.icon is None
    assert m.routes == []
    assert m.hooks == []
    assert m.database == {}
    assert m.scheduler == []
    assert m.min_master_version is None


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing",
    ["id", "name", "version"],
)
def test_missing_required_field_raises(missing):
    """Removing any required field must raise ValidationError."""
    kwargs = _full_manifest_kwargs()
    kwargs.pop(missing)
    with pytest.raises(ValidationError):
        PluginManifest(**kwargs)


# ---------------------------------------------------------------------------
# Invalid plugin id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_id",
    [
        "WidgetManager",  # uppercase
        "1widget",        # starts with digit
        "widget-manager", # hyphen not allowed
        "widget!",        # punctuation
        "",               # empty
        "widget manager", # space
        "w",              # lone letter: needs 2+ chars ([a-z][a-z0-9_]+)
    ],
)
def test_invalid_plugin_id_raises(bad_id):
    """Plugin id must match ^[a-z][a-z0-9_]+$."""
    kwargs = _full_manifest_kwargs()
    kwargs["id"] = bad_id
    with pytest.raises(ValidationError):
        PluginManifest(**kwargs)


@pytest.mark.parametrize(
    "good_id",
    [
        "wa",
        "widget",
        "widget_manager",
        "widget_2",
        "a1b2c3",
    ],
)
def test_valid_plugin_id_accepts(good_id):
    kwargs = _full_manifest_kwargs()
    kwargs["id"] = good_id
    m = PluginManifest(**kwargs)
    assert m.id == good_id


# ---------------------------------------------------------------------------
# Invalid version
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_version",
    [
        "1.0",         # missing patch
        "1.0.0.0",     # too many parts
        "v1.0.0",      # leading v
        "1.0.0-beta",  # pre-release suffix not allowed
        "1.0.x",       # non-numeric
        "",            # empty
    ],
)
def test_invalid_version_raises(bad_version):
    kwargs = _full_manifest_kwargs()
    kwargs["version"] = bad_version
    with pytest.raises(ValidationError):
        PluginManifest(**kwargs)


# ---------------------------------------------------------------------------
# manifest_hash determinism
# ---------------------------------------------------------------------------


def test_manifest_hash_deterministic():
    """Two manifests with identical content produce the same hash."""
    m1 = PluginManifest(**_full_manifest_kwargs())
    m2 = PluginManifest(**_full_manifest_kwargs())
    assert m1.manifest_hash == m2.manifest_hash
    # Sanity: the hash is a 64-char hex SHA-256 digest.
    assert len(m1.manifest_hash) == 64
    int(m1.manifest_hash, 16)  # parses as hex


def test_manifest_hash_matches_manual_computation():
    """manifest_hash equals a manual SHA-256 of the canonical (sorted) JSON dump.

    Pydantic 2.9's ``model_dump_json`` has no ``sort_keys`` kwarg, so the
    canonical form is json.dumps(model_dump(mode='json'), sort_keys=True).
    We assert the property matches that computation exactly.
    """
    m = PluginManifest(**_full_manifest_kwargs())
    canonical = json.dumps(
        m.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    expected = hashlib.sha256(canonical).hexdigest()
    assert m.manifest_hash == expected


def test_manifest_hash_differs_on_content_change():
    """Changing content changes the hash; reverting restores the original."""
    m = PluginManifest(**_full_manifest_kwargs())
    original = m.manifest_hash

    m.version = "2.0.0"
    assert m.manifest_hash != original

    m.version = "1.0.0"
    assert m.manifest_hash == original


def test_manifest_hash_invariant_to_kwarg_order():
    """Construction order must not affect the hash (sort_keys normalizes)."""
    kwargs = _full_manifest_kwargs()

    # Build with fields passed in reversed/permuted order via dict rebuild.
    keys = list(kwargs.keys())
    permuted = {k: kwargs[k] for k in reversed(keys)}
    m_a = PluginManifest(**kwargs)
    m_b = PluginManifest(**permuted)
    assert m_a.manifest_hash == m_b.manifest_hash


# ---------------------------------------------------------------------------
# Sub-model validation
# ---------------------------------------------------------------------------


def test_schedule_interval_zero_raises_at_construction():
    with pytest.raises(ValidationError):
        ScheduleSpec(name="bad", interval_secs=0, handler="x.y")


def test_extra_field_forbidden():
    """Unknown top-level fields are rejected (model_config extra='forbid')."""
    kwargs = _full_manifest_kwargs()
    kwargs["unexpected"] = "boom"
    with pytest.raises(ValidationError):
        PluginManifest(**kwargs)


def test_route_spec_requires_all_fields():
    with pytest.raises(ValidationError):
        RouteSpec(path="/x", method="GET")  # missing handler


def test_column_spec_defaults():
    c = ColumnSpec(name="n", type="TEXT")
    assert c.pk is False
    assert c.not_null is False
    assert c.default is None
