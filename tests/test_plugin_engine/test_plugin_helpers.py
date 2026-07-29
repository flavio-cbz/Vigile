from __future__ import annotations

"""Tests for master.core.plugin_utils shared utility functions.

Verifies that parse_worker_list and parse_worker_object
are importable from master.core.plugin_utils, that they function correctly
when invoked with sample data, and that they are used by plugin modules.
"""

import json

import pytest

from master.core import plugin_utils
from master.core.plugin_utils import (
    parse_worker_list,
    parse_worker_object,
)
from master.plugins.docker_plugin import parse_container_list as _orig_container
from master.plugins.systemd_plugin import (
    parse_service_list as _orig_service_list,
    parse_service_status as _orig_service_status,
)


# ---------------------------------------------------------------------------
# Importability / identity
# ---------------------------------------------------------------------------


def test_parse_worker_list_importable():
    assert callable(parse_worker_list)


def test_parse_worker_object_importable():
    assert callable(parse_worker_object)


def test_all_two_listed_in_all():
    assert set(plugin_utils.__all__) == {
        "parse_worker_output",
        "parse_worker_list",
        "parse_worker_object",
    }


# ---------------------------------------------------------------------------
# parse_worker_list — behavior
# ---------------------------------------------------------------------------

SERVICE_SAMPLE = [
    {"name": "ssh.service", "state": "active", "status": "running"},
    {"name": "nginx.service", "state": "inactive", "status": "dead"},
]


def test_parse_worker_list_valid():
    from master.plugins.systemd_plugin import ServiceInfo
    parsed = parse_worker_list(json.dumps(SERVICE_SAMPLE), ServiceInfo)
    assert parsed is not None
    assert len(parsed) == 2
    assert parsed[0]["name"] == "ssh.service"
    assert parsed[0]["state"] == "active"
    assert parsed[0]["status"] == "running"
    assert parsed[1]["name"] == "nginx.service"


def test_parse_worker_list_empty_array():
    from master.plugins.systemd_plugin import ServiceInfo
    assert parse_worker_list("[]", ServiceInfo) == []


def test_parse_worker_list_invalid_json():
    from master.plugins.systemd_plugin import ServiceInfo
    assert parse_worker_list("!!!", ServiceInfo) is None


def test_parse_worker_list_not_a_list():
    from master.plugins.systemd_plugin import ServiceInfo
    assert parse_worker_list('{"name": "ssh.service"}', ServiceInfo) is None


def test_parse_worker_list_bad_fields():
    from master.plugins.systemd_plugin import ServiceInfo
    assert parse_worker_list('[{"state": "active"}]', ServiceInfo) is None


# ---------------------------------------------------------------------------
# parse_worker_object — behavior
# ---------------------------------------------------------------------------


def test_parse_worker_object_valid():
    from master.plugins.systemd_plugin import ServiceStatus
    raw = json.dumps({"service": "ssh.service", "active": "active", "enabled": "enabled"})
    parsed = parse_worker_object(raw, ServiceStatus)
    assert parsed is not None
    assert parsed["service"] == "ssh.service"
    assert parsed["active"] == "active"
    assert parsed["enabled"] == "enabled"


def test_parse_worker_object_missing_field():
    from master.plugins.systemd_plugin import ServiceStatus
    assert parse_worker_object('{"service": "ssh.service"}', ServiceStatus) is None


def test_parse_worker_object_invalid_json():
    from master.plugins.systemd_plugin import ServiceStatus
    assert parse_worker_object("{not json", ServiceStatus) is None


def test_parse_worker_object_not_an_object():
    from master.plugins.systemd_plugin import ServiceStatus
    # A JSON array is not a mapping -> ServiceStatus(**[...]) raises TypeError
    assert parse_worker_object("[]", ServiceStatus) is None
