"""
Vigile — Nodes API: Pydantic request/response models
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateJoinRequest(BaseModel):
    name: str | None = Field(
        default=None, max_length=128, description="Optional pre-filled human label"
    )
    group: str | None = Field(default=None, max_length=128, description="Optional group/tag")
    ip_prefix: str = Field(
        default="",
        max_length=64,
        pattern=r"^$|^[\d.]+$",
        description="DEPRECATED, ignored. Kept for back-compat with older clients.",
    )


class NodePatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    group: str | None = Field(default=None, max_length=128)
    disabled: bool | None = None


class ConfigureRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    group: str | None = Field(default=None, max_length=128)


class JoinTokenResponse(BaseModel):
    node_id: str
    token: str
    expires_in: int  # seconds
    curl_command: str


class NodeResponse(BaseModel):
    id: str
    name: str
    hostname: str | None
    machine_id: str | None
    arch: str | None
    os: str | None
    state: str
    online: bool
    last_heartbeat: float | None
    enrolled_at: float | None
    created_at: float
    updated_at: float
    group: str | None
    disabled: bool
    enrolled_recently: bool
    version: str | None = None
    cpu_percent: float | None = None
    memory_percent: float | None = None
    disk_percent: float | None = None
    uptime_seconds: float | None = None


class BulkNodeStatus(BaseModel):
    cpu: float | None = None
    mem: float | None = None
    disk: float | None = None
    uptime: float | None = None
    containers_count: int | None = None


class BulkStatusResponse(BaseModel):
    statuses: dict[str, BulkNodeStatus]


class LogsResponse(BaseModel):
    """Response model for live logs fetched from a Worker."""

    node_id: str
    output: str
    lines: int
    service: str | None = None
    path: str | None = None
    error: str | None = None


class DiskMountResponse(BaseModel):
    mount_point: str
    fs_type: str
    device: str
    total_bytes: int
    used_bytes: int
    percent: float


class MetricsSnapshotResponse(BaseModel):
    """Single metrics snapshot exposed via the stats endpoint."""

    collected_at: float
    cpu_percent: float
    cpu_load_1m: float | None = None
    cpu_load_5m: float | None = None
    cpu_load_15m: float | None = None
    cpu_cores: int | None = None
    mem_total_bytes: int
    mem_used_bytes: int
    mem_percent: float
    swap_total_bytes: int
    swap_used_bytes: int
    disk_total_bytes: int
    disk_used_bytes: int
    disk_percent: float
    disks: list[DiskMountResponse] | None = None
    uptime_seconds: float
    processes: int | None = None


class NodeStatsResponse(BaseModel):
    """Node stats endpoint response."""

    node_id: str
    snapshots: list[MetricsSnapshotResponse]
