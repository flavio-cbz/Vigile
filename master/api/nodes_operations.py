"""
Vigile — Nodes API: worker operations (update, disk scan)
"""

from __future__ import annotations

from master.api.nodes import get_disk_scan, update_worker
from master.api.nodes_router import router

router.add_api_route(
    "/{node_id}/update",
    update_worker,
    methods=["POST"],
    summary="Trigger worker self-update (Admin only)",
)

router.add_api_route(
    "/{node_id}/disk-scan",
    get_disk_scan,
    methods=["GET"],
    summary="Scan disk usage on a node (Operator+, force: Admin)",
)

__all__ = ["update_worker", "get_disk_scan"]

