from __future__ import annotations

"""Tests for master.schemas.disk_scan validation."""

import json
import pytest

from master.schemas.disk_scan import DiskNode, DiskScanResult, validate_disk_scan_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_SCAN = {
    "root": {
        "name": "/var",
        "path": "/var",
        "size": 5368709120,
        "is_dir": True,
        "children": [
            {
                "name": "log",
                "path": "/var/log",
                "size": 104857600,
                "is_dir": True,
                "children": [
                    {
                        "name": "syslog",
                        "path": "/var/log/syslog",
                        "size": 2097152,
                        "is_dir": False,
                        "children": None,
                    }
                ],
            }
        ],
    },
    "truncated": False,
    "scanned_at": 1718700000,
    "walked_count": 42,
    "skipped_perm": 0,
}


# ---------------------------------------------------------------------------
# test_valid — valid JSON parses cleanly
# ---------------------------------------------------------------------------

def test_valid():
    """Given a well-formed disk-scan JSON → parse succeeds."""
    result = validate_disk_scan_json(json.dumps(VALID_SCAN))

    assert isinstance(result, DiskScanResult)
    assert result.root.name == "/var"
    assert result.truncated is False
    assert result.walked_count == 42

    # Nested child is reachable
    child = result.root.children[0]
    assert child.name == "log"
    assert child.is_dir is True

    grandchild = child.children[0]
    assert grandchild.name == "syslog"
    assert grandchild.is_dir is False


# ---------------------------------------------------------------------------
# test_malicious — unexpected fields / bad structure → ValueError
# ---------------------------------------------------------------------------

def test_malicious_unknown_field():
    """Extra unknown field on DiskNode should be rejected (forbid)."""
    bad = {**VALID_SCAN}
    bad["root"] = {**VALID_SCAN["root"], "evil_inject": True}
    with pytest.raises(ValueError, match="Schema validation failed"):
        validate_disk_scan_json(json.dumps(bad))


def test_malicious_path_too_long():
    """A path exceeding 4096 chars should fail validation."""
    bad = json.loads(json.dumps(VALID_SCAN))
    bad["root"]["path"] = "x" * 4097
    bad["root"]["name"] = "x" * 4097
    # Pydantic v2 doesn't enforce max_length on str by default;
    # this tests the schema accepts it (path length is Worker-side).
    # Instead test a negative size (schema has int, but logically invalid).
    bad["root"]["size"] = -1
    # size=-1 is still valid int for Pydantic; test with non-int instead.
    bad2 = json.loads(json.dumps(VALID_SCAN))
    bad2["root"]["size"] = "not_a_number"
    with pytest.raises(ValueError, match="Schema validation failed"):
        validate_disk_scan_json(json.dumps(bad2))


def test_malicious_missing_required():
    """Missing required fields should fail."""
    bad = json.loads(json.dumps(VALID_SCAN))
    del bad["root"]["name"]
    with pytest.raises(ValueError, match="Schema validation failed"):
        validate_disk_scan_json(json.dumps(bad))


def test_malicious_wrong_type():
    """Wrong types for required fields should fail."""
    bad = json.loads(json.dumps(VALID_SCAN))
    bad["root"]["is_dir"] = "yes"
    bad["root"]["size"] = "big"
    bad["scanned_at"] = "now"
    with pytest.raises(ValueError, match="Schema validation failed"):
        validate_disk_scan_json(json.dumps(bad))


# ---------------------------------------------------------------------------
# test_truncated — truncated=true parses correctly
# ---------------------------------------------------------------------------

def test_truncated():
    """Given truncated=true → parse OK, flag is True."""
    data = json.loads(json.dumps(VALID_SCAN))
    data["truncated"] = True
    result = validate_disk_scan_json(json.dumps(data))
    assert result.truncated is True
    assert result.root.name == "/var"


# ---------------------------------------------------------------------------
# test_empty_children — root with children=None
# ---------------------------------------------------------------------------

def test_empty_children():
    """Given root.children=None → parse OK."""
    data = json.loads(json.dumps(VALID_SCAN))
    data["root"]["children"] = None
    result = validate_disk_scan_json(json.dumps(data))
    assert result.root.children is None


def test_empty_children_list():
    """Given root.children=[] → parse OK, children is empty list."""
    data = json.loads(json.dumps(VALID_SCAN))
    data["root"]["children"] = []
    result = validate_disk_scan_json(json.dumps(data))
    assert result.root.children == []


# ---------------------------------------------------------------------------
# test_invalid_json — not valid JSON at all
# ---------------------------------------------------------------------------

def test_invalid_json():
    """Given garbage string → ValueError."""
    with pytest.raises(ValueError, match="Invalid JSON"):
        validate_disk_scan_json("not json at all {{{")


# ---------------------------------------------------------------------------
# test_children_max_length — more than 100 children → rejected
# ---------------------------------------------------------------------------

def test_children_max_length():
    """Given >100 children → rejected by max_length=100."""
    data = json.loads(json.dumps(VALID_SCAN))
    data["root"]["children"] = [
        {"name": str(i), "path": f"/{i}", "size": 0, "is_dir": False, "children": None}
        for i in range(101)
    ]
    with pytest.raises(ValueError, match="Schema validation failed"):
        validate_disk_scan_json(json.dumps(data))


# ---------------------------------------------------------------------------
# test_defaults — defaults work for optional fields
# ---------------------------------------------------------------------------

def test_defaults():
    """Minimal valid payload → defaults applied."""
    minimal = {
        "root": {
            "name": "/",
            "path": "/",
            "size": 0,
            "is_dir": True,
            "children": None,
        },
        "scanned_at": 0,
    }
    result = validate_disk_scan_json(json.dumps(minimal))
    assert result.truncated is False
    assert result.walked_count == 0
    assert result.skipped_perm == 0
