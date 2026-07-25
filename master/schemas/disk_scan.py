"""Pydantic v2 schemas for Worker disk-scan JSON validation."""

from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class DiskNode(BaseModel):
    """Recursive tree node representing a file or directory on disk."""

    model_config = ConfigDict(extra="forbid")

    name: str
    path: str
    size: int  # allocated bytes on disk
    is_dir: bool
    children: Optional[list[DiskNode]] = Field(default=None, max_length=100)


# Self-referencing forward-ref resolution — MUST stay after DiskNode.
DiskNode.model_rebuild()


class DiskScanResult(BaseModel):
    """Top-level envelope returned by the Worker disk-scan plugin."""

    model_config = ConfigDict(extra="forbid")

    root: DiskNode
    truncated: bool = False
    scanned_at: int
    walked_count: int = 0
    skipped_perm: int = 0


def validate_disk_scan_json(json_str: str) -> DiskScanResult:
    """Parse *json_str* into a DiskScanResult; raise ValueError on any error."""
    try:
        raw = json.loads(json_str)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    try:
        return DiskScanResult.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Schema validation failed: {exc}") from exc
