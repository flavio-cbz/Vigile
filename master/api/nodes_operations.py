"""
Vigile — Nodes API: worker operations (update, disk scan)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Path, Query, status

from master.api.demo_data import is_demo
from master.api.deps import DB, get_node_manager, require_role
from master.api.nodes_router import router
from master.core.audit import AuditAction, log_action
from master.core.enums import WorkerAction
from master.core.node_manager import NodeManager
from master.db.disk_scan_cache import get_cached_disk_scan, set_cached_disk_scan
from master.schemas.disk_scan import DiskScanResult

logger = logging.getLogger(__name__)

_operator_plus = Depends(require_role("operator", "admin"))


# ---------------------------------------------------------------------------
# Worker Update
# ---------------------------------------------------------------------------


@router.post(
    "/{node_id}/update",
    summary="Trigger worker self-update (Admin only)",
)
async def update_worker(
    node_id: Annotated[str, Path(description="Node UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("admin"))],
    nm: NodeManager = Depends(get_node_manager),
) -> dict:
    """Send an UPDATE_WORKER intent to the worker, causing it to download the latest binary from the Master and restart."""
    if is_demo(claims):
        return {"success": True, "output": "demo worker update simulation complete"}

    node = await nm.get_node(db, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    try:
        result = await nm.send_intent(
            node_id,
            {"action": WorkerAction.UPDATE_WORKER, "params": {}},
            timeout=30.0,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Worker did not respond to update request in time",
        )

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("error", "Update failed on worker"),
        )

    # Log action to audit trails
    await log_action(
        db,
        user_id=claims["sub"],
        action="UPDATE_WORKER",
        node_id=node_id,
        details={"result": result},
    )

    return {"success": True, "output": result.get("output", "")}


# ---------------------------------------------------------------------------
# DISK_SCAN endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/{node_id}/disk-scan",
    summary="Scan disk usage on a node (Operator+, force: Admin)",
)
async def get_disk_scan(
    node_id: Annotated[str, Path(description="Node UUID")],
    path: str = Query("/"),
    force: bool = False,
    max_depth: int = Query(4, ge=0, le=20),
    min_size_bytes: int = Query(10 * 1024 * 1024, ge=0),
    claims: Annotated[dict, _operator_plus] = None,
    nm: NodeManager = Depends(get_node_manager),
    db: DB = None,
) -> dict[str, Any]:
    """
    Scan disk usage tree for a node's filesystem.

    Results are cached for 5 minutes per node. Pass ``force=true``
    (admin only) to bypass the cache and trigger a fresh scan.
    """
    if claims is None:
        claims = {}
    if force:
        if claims.get("role") not in ("admin",):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="force=true requires admin role",
            )

    if not force:
        try:
            cached_json, cached_at = await get_cached_disk_scan(db, node_id)
        except Exception:
            cached_json, cached_at = None, None
        if (
            cached_json
            and cached_at is not None
            and (time.time() - cached_at) < 300
        ):
            try:
                return json.loads(cached_json)
            except Exception:
                pass

    node = await nm.get_node(db, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    mounts = ["/"]
    try:
        stats_result = await nm.send_intent(
            node_id, {"action": "GET_STATS"}, timeout=10.0
        )
        if stats_result.get("success"):
            disks = stats_result.get("disks", [])
            extracted = [d["mount_point"] for d in disks if d.get("mount_point")]
            if extracted:
                mounts = extracted
    except Exception as exc:
        logger.warning("Node %s: GET_STATS failed for disk-scan mounts: %s", node_id, exc)

    try:
        result = await nm.send_intent(
            node_id,
            {
                "action": WorkerAction.DISK_SCAN,
                "params": {
                    "path": path,
                    "max_depth": max_depth,
                    "min_size_bytes": min_size_bytes,
                    "mounts": mounts,
                },
            },
            timeout=45.0,
        )
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Worker did not respond to disk-scan request in time",
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("error", "scan failed"),
        )

    try:
        parsed = DiskScanResult.model_validate_json(result["output"])
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="invalid scan result from worker",
        )

    try:
        await set_cached_disk_scan(db, node_id, result["output"], time.time())
    except Exception as exc:
        logger.warning("Node %s: failed to write disk-scan cache: %s", node_id, exc)

    await log_action(
        db,
        user_id=claims.get("sub", "system"),
        action=AuditAction.DISK_SCAN,
        node_id=node_id,
        details={"path": path, "max_depth": max_depth, "min_size_bytes": min_size_bytes},
    )

    response = parsed.model_dump(mode="json")
    response["available_mounts"] = mounts
    return response
