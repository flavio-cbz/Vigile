"""Tests for master.core.plugin_helpers re-export facade.

Verifies that parse_container_list, parse_service_list and parse_service_status
are importable from master.core.plugin_helpers, that they are the same objects
as the originals in master.plugins.* (genuine re-export, not a copy), and that
they function correctly when invoked with sample data.
"""

import json

import pytest

from master.core import plugin_helpers
from master.core.plugin_helpers import (
    parse_container_list,
    parse_service_list,
    parse_service_status,
)
from master.plugins.docker_plugin import parse_container_list as _orig_container
from master.plugins.systemd_plugin import (
    parse_service_list as _orig_service_list,
    parse_service_status as _orig_service_status,
)


# ---------------------------------------------------------------------------
# Importability / identity
# ---------------------------------------------------------------------------


def test_parse_container_list_importable():
    assert callable(parse_container_list)


def test_parse_service_list_importable():
    assert callable(parse_service_list)


def test_parse_service_status_importable():
    assert callable(parse_service_status)


def test_all_three_listed_in_all():
    assert set(plugin_helpers.__all__) == {
        "parse_container_list",
        "parse_service_list",
        "parse_service_status",
    }


@pytest.mark.parametrize(
    "name,original",
    [
        ("parse_container_list", _orig_container),
        ("parse_service_list", _orig_service_list),
        ("parse_service_status", _orig_service_status),
    ],
)
def test_reexport_is_same_object(name, original):
    assert getattr(plugin_helpers, name) is original


# ---------------------------------------------------------------------------
# parse_container_list — behavior
# ---------------------------------------------------------------------------

CONTAINER_SAMPLE = [
    {
        "id": "abc123def456",
        "name": "vigile-master",
        "image": "vigile/master:latest",
        "state": "running",
        "ports": ["0.0.0.0:8000->8000/tcp"],
    },
    {
        "id": "deadbeef0000",
        "name": "plex",
        "image": "plexinc/pms:latest",
        "state": "exited",
        "ports": [],
    },
]


def test_parse_container_list_valid():
    parsed = parse_container_list(json.dumps(CONTAINER_SAMPLE))
    assert parsed is not None
    assert len(parsed) == 2
    assert parsed[0]["id"] == "abc123def456"
    assert parsed[0]["name"] == "vigile-master"
    assert parsed[0]["state"] == "running"
    assert parsed[0]["ports"] == ["0.0.0.0:8000->8000/tcp"]
    assert parsed[1]["ports"] == []


def test_parse_container_list_empty_array():
    assert parse_container_list("[]") == []


def test_parse_container_list_invalid_json():
    assert parse_container_list("not json") is None


def test_parse_container_list_not_a_list():
    assert parse_container_list('{"id": "abc"}') is None


def test_parse_container_list_bad_fields():
    # Missing required 'name' field -> pydantic raises -> swallowed to None
    assert parse_container_list('[{"id": "x"}]') is None


# ---------------------------------------------------------------------------
# parse_service_list — behavior
# ---------------------------------------------------------------------------

SERVICE_SAMPLE = [
    {"name": "ssh.service", "state": "active", "status": "running"},
    {"name": "nginx.service", "state": "inactive", "status": "dead"},
]


def test_parse_service_list_valid():
    parsed = parse_service_list(json.dumps(SERVICE_SAMPLE))
    assert parsed is not None
    assert len(parsed) == 2
    assert parsed[0]["name"] == "ssh.service"
    assert parsed[0]["state"] == "active"
    assert parsed[0]["status"] == "running"
    assert parsed[1]["name"] == "nginx.service"


def test_parse_service_list_empty_array():
    assert parse_service_list("[]") == []


def test_parse_service_list_invalid_json():
    assert parse_service_list("!!!") is None


def test_parse_service_list_not_a_list():
    assert parse_service_list('{"name": "ssh.service"}') is None


def test_parse_service_list_bad_fields():
    assert parse_service_list('[{"state": "active"}]') is None


# ---------------------------------------------------------------------------
# parse_service_status — behavior
# ---------------------------------------------------------------------------


def test_parse_service_status_valid():
    raw = json.dumps({"service": "ssh.service", "active": "active", "enabled": "enabled"})
    parsed = parse_service_status(raw)
    assert parsed is not None
    assert parsed["service"] == "ssh.service"
    assert parsed["active"] == "active"
    assert parsed["enabled"] == "enabled"


def test_parse_service_status_missing_field():
    assert parse_service_status('{"service": "ssh.service"}') is None


def test_parse_service_status_invalid_json():
    assert parse_service_status("{not json") is None


def test_parse_service_status_not_an_object():
    # A JSON array is not a mapping -> ServiceStatus(**[...]) raises TypeError
    assert parse_service_status("[]") is None
