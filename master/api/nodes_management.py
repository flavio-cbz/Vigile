"""
Vigile — Nodes API: token management, CRUD, stats, logs
"""

from __future__ import annotations

import json
import logging
import os
import time
try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated  # type: ignore[attr-defined]
from typing import Any, List


from fastapi import Depends, HTTPException, Path, Query, Request, status

from master.api.demo_data import DEMO_NODES, get_demo_logs, get_demo_metrics, get_demo_node, is_demo
from master.api.deps import DB, CurrentUser, get_node_manager, get_security, get_worker_query_port, require_role
from master.api.nodes_helpers import _add_bulk_node_metrics, _add_node_metrics, _node_to_response
from master.core.worker_query_port import WorkerQueryPort
from master.api.nodes_models import (
    BulkNodeStatus,
    BulkStatusResponse,
    ConfigureRequest,
    GenerateJoinRequest,
    JoinTokenResponse,
    LogsResponse,
    MetricsSnapshotResponse,
    NodePatchRequest,
    NodeResponse,
    NodeStatsResponse,
)
from master.api.nodes_router import router
from master.core.audit import AuditAction, log_action
from master.core.enums import WorkerAction
from master.core.node_manager import NodeManager, NodeState
from master.core.security_manager import SecurityManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token Management
# ---------------------------------------------------------------------------


@router.post(
    "/generate-join",
    response_model=JoinTokenResponse,
    summary="Generate an enrollment token and kickstart command (Admin only)",
    status_code=status.HTTP_201_CREATED,
)
async def generate_join_token(
    body: GenerateJoinRequest,
    request: Request,
    db: DB,
    claims: Annotated[dict, Depends(require_role("admin"))],
    sec: SecurityManager = Depends(get_security),
    nm: NodeManager = Depends(get_node_manager),
) -> JoinTokenResponse:
    """
    Generate a JOIN_TOKEN for a new Worker Node.

    Steps:
      1. Pre-create the node entry in PENDING state
      2. Generate HMAC-SHA256 signed JOIN_TOKEN
      3. Store token hash in DB (never store raw token)
      4. Return the curl command for the kickstart script

    The token is single-use and expires in 30 minutes.
    """
    # Demo mode: return mock response
    if is_demo(claims):
        master_url = request.app.state.master_url
        fake_token = f"demo-join-token-{uuid.uuid4()}"
        return JoinTokenResponse(
            node_id="demo-node-99",
            token=fake_token,
            expires_in=1800,
            curl_command=(
                f"curl -sSL {master_url}/api/nodes/kickstart.sh | "
                f"sudo bash -s -- --token {fake_token} --master {master_url}"
            ),
        )

    # Generate node_id (UUID) without persisting. The `nodes` row is created
    # by the Worker enrollment handshake — see master/ws/worker_handler.py.
    # This avoids "phantom" nodes: if the Worker never connects, no row leaks.
    # `group` and `ip_prefix` are forwarded through the JOIN_TOKEN payload and
    # applied to the `nodes` row at enrollment time.
    node_id = nm.generate_node_id()
    pending_name = body.name or ""
    pending_group = body.group or ""

    # 2. Generate JOIN_TOKEN (returns token + payload together)
    # `name` and `group` are carried in the payload so the Worker enrollment
    # can persist them on first INSERT (no `nodes` row exists yet).
    token, payload = sec.generate_join_token(
        node_id=node_id,
        ip_prefix=body.ip_prefix,
        name=pending_name,
        group=pending_group,
    )
    token_hash = sec.join_token_hash(token)

    # 3. Store token in DB. The FK on join_tokens.node_id is dropped (migration
    # 006) so this row can exist before the corresponding `nodes` row.
    token_id = str(uuid.uuid4())
    now = time.time()
    await db.execute(
        """
        INSERT INTO join_tokens (id, node_id, token_hash, payload_b64, consumed, expires_at, created_at)
        VALUES (?, ?, ?, ?, 0, ?, ?)
        """,
        (
            token_id,
            node_id,
            token_hash,
            token.split(".", 1)[1],
            payload["expires_at"],
            now,
        ),
    )
    await db.commit()

    # 4. Audit (no node_id FK — audit log keeps the reference for traceability)
    await log_action(
        db,
        user_id=claims["sub"],
        action=AuditAction.GENERATE_JOIN_TOKEN,
        node_id=node_id,
        details={
            "node_name": pending_name,
            "node_group": pending_group,
            "ip_prefix": body.ip_prefix,
        },
    )

    master_url = request.app.state.master_url
    curl_command = (
        f"curl -sSL {master_url}/api/nodes/kickstart.sh | "
        f"sudo bash -s -- --token {token} --master {master_url}"
    )

    expires_in = int(payload["expires_at"] - now)
    logger.info(
        "JOIN_TOKEN generated: node_id=%s name=%s expires_in=%ds",
        node_id,
        body.name,
        expires_in,
    )

    return JoinTokenResponse(
        node_id=node_id,
        token=token,
        expires_in=expires_in,
        curl_command=curl_command,
    )


@router.post(
    "/{node_id}/regenerate-token",
    response_model=JoinTokenResponse,
    summary="Invalidate existing JOIN_TOKENs and issue a fresh one (Admin only)",
    status_code=status.HTTP_201_CREATED,
)
async def regenerate_join_token(
    node_id: Annotated[str, Path(description="Node UUID")],
    request: Request,
    db: DB,
    claims: Annotated[dict, Depends(require_role("admin"))],
    sec: SecurityManager = Depends(get_security),
    nm: NodeManager = Depends(get_node_manager),
) -> JoinTokenResponse:
    """
    Issue a new JOIN_TOKEN for an already-pre-created (PENDING) node, invalidating
    any tokens previously issued for it. The node must still be in PENDING state.
    """
    if is_demo(claims):
        master_url = request.app.state.master_url
        fake_token = f"demo-regen-{uuid.uuid4()}"
        return JoinTokenResponse(
            node_id=node_id,
            token=fake_token,
            expires_in=1800,
            curl_command=(
                f"curl -sSL {master_url}/api/nodes/kickstart.sh | "
                f"sudo bash -s -- --token {fake_token} --master {master_url}"
            ),
        )

    existing = await nm.get_node(db, node_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    if existing["state"] != NodeState.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Node already enrolled. Cannot regenerate token.",
        )

    invalidated = await nm.invalidate_join_tokens(db, node_id)
    logger.info("Invalidated %d join tokens for node %s", invalidated, node_id)

    token, payload = sec.generate_join_token(node_id=node_id, ip_prefix="")
    token_hash = sec.join_token_hash(token)

    token_id = str(uuid.uuid4())
    now = time.time()
    await db.execute(
        """
        INSERT INTO join_tokens (id, node_id, token_hash, payload_b64, consumed, expires_at, created_at)
        VALUES (?, ?, ?, ?, 0, ?, ?)
        """,
        (
            token_id,
            node_id,
            token_hash,
            token.split(".", 1)[1],
            payload["expires_at"],
            now,
        ),
    )
    await db.execute(
        "UPDATE nodes SET updated_at = ? WHERE id = ?",
        (now, node_id),
    )
    await db.commit()

    await log_action(
        db,
        user_id=claims["sub"],
        action=AuditAction.REGENERATE_JOIN_TOKEN,
        node_id=node_id,
        details={"invalidated": invalidated},
    )

    master_url = request.app.state.master_url
    curl_command = (
        f"curl -sSL {master_url}/api/nodes/kickstart.sh | "
        f"sudo bash -s -- --token {token} --master {master_url}"
    )
    expires_in = int(payload["expires_at"] - now)
    logger.info("JOIN_TOKEN regenerated: node_id=%s expires_in=%ds", node_id, expires_in)

    return JoinTokenResponse(
        node_id=node_id,
        token=token,
        expires_in=expires_in,
        curl_command=curl_command,
    )


# ---------------------------------------------------------------------------
# Verify Chain (defined before /{node_id} to prevent route shadowing)
# ---------------------------------------------------------------------------


@router.get(
    "/verify-chain",
    response_model=dict,
    summary="Verify audit chain integrity with optional pagination (Admin only)",
)
async def verify_chain(
    db: DB,
    claims: Annotated[dict, Depends(require_role("admin"))],
    max_entries: int | None = Query(
        default=None, ge=1, le=100000, description="Max entries to verify"
    ),
) -> dict:
    """Verify the audit log hash chain. `max_entries` limits scan for large tables."""
    # Demo mode: return mock data
    if is_demo(claims):
        return {"verified": True, "entries_checked": 5, "corrupted": False, "valid": True}

    from master.core.audit import verify_chain as _verify_chain

    report = await _verify_chain(db, max_entries=max_entries)
    return report


# ---------------------------------------------------------------------------
# Node CRUD
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=List[NodeResponse],

    summary="List all nodes (Operator+)",
)
async def list_nodes(
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    state: str | None = Query(default=None, description="Filter by state"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Result offset for pagination"),
    nm: NodeManager = Depends(get_node_manager),
) -> list[NodeResponse]:
    """Return a list of registered nodes, with optional pagination."""
    # Demo mode: return mock data
    if is_demo(claims):
        mock_dicts = [_node_to_response(n) for n in DEMO_NODES]
        mock_enriched = await _add_bulk_node_metrics(db, mock_dicts, claims)
        return [NodeResponse(**nd) for nd in mock_enriched]

    nodes = await nm.list_nodes(db, state=state, limit=limit, offset=offset)
    node_dicts = [_node_to_response(n) for n in nodes]
    enriched = await _add_bulk_node_metrics(db, node_dicts, claims)
    return [NodeResponse(**nd) for nd in enriched]


@router.get(
    "/{node_id}",
    response_model=NodeResponse,
    summary="Get a node's details (Operator+)",
)
async def get_node(
    node_id: Annotated[str, Path(description="Node UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    nm: NodeManager = Depends(get_node_manager),
) -> NodeResponse:
    """Fetch detailed information for a single node."""
    # Demo mode: return mock data
    if is_demo(claims):
        node = get_demo_node(node_id)
        if node is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
        enriched_demo = await _add_node_metrics(db, _node_to_response(node), claims)
        return NodeResponse(**enriched_demo)

    node = await nm.get_node(db, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    enriched = await _add_node_metrics(db, _node_to_response(node), claims)
    return NodeResponse(**enriched)


@router.delete(
    "/{node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hard-delete a node (Admin only)",
)
async def delete_node(
    node_id: Annotated[str, Path(description="Node UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("admin"))],
    nm: NodeManager = Depends(get_node_manager),
):
    """
    Hard-delete a node from the database.

    This action is permanent — the row is removed and all dependent rows
    (join_tokens, worker_tokens, metrics_snapshots, action_proposals) are
    cascaded away by FK ON DELETE CASCADE. The audit_log keeps a NODE_DELETED
    entry forever (it stores node_id as plain TEXT, no FK). A new enrollment
    is required to re-add the same node.
    """
    # Demo mode: no-op (simulate successful deletion)
    if is_demo(claims):
        return

    deleted = await nm.delete_node(db, node_id, deleted_by=claims["sub"])
    if deleted is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    logger.warning("Node %s hard-deleted by user %s", node_id, claims["sub"])


@router.patch(
    "/{node_id}",
    response_model=NodeResponse,
    summary="Update node metadata or disable flag (Operator+ for metadata, Admin for disable)",
)
async def patch_node(
    node_id: Annotated[str, Path(description="Node UUID")],
    body: NodePatchRequest,
    db: DB,
    claims: CurrentUser,
    nm: NodeManager = Depends(get_node_manager),
) -> NodeResponse:
    """
    Partial update of a node.
      - `name` / `group` : operator+ can change; empty string for `group` clears the value.
      - `disabled`       : admin only; toggles the disable flag and may transition state.
    """
    if is_demo(claims):
        demo_node = get_demo_node(node_id)
        if demo_node is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
        if body.name is not None:
            demo_node["name"] = body.name
        if body.group is not None:
            demo_node["node_group"] = body.group
        if body.disabled is not None:
            demo_node["disabled"] = bool(body.disabled)
            demo_node["state"] = "DISABLED" if body.disabled else demo_node["state"]
        demo_node["updated_at"] = time.time()
        enriched_demo = await _add_node_metrics(db, _node_to_response(demo_node), claims)
        return NodeResponse(**enriched_demo)

    existing = await nm.get_node(db, node_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    user_role = claims.get("role", "viewer")
    has_disabled_field = body.disabled is not None
    has_metadata_field = body.name is not None or body.group is not None

    if has_disabled_field and user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to enable/disable a node",
        )

    if has_disabled_field:
        await nm.set_disabled(db, node_id, body.disabled, by_user=claims["sub"])  # type: ignore[arg-type]

    if has_metadata_field:
        # Empty string for group means clear; Pydantic keeps it as empty string
        # (None means "field not provided", "" means "clear it").
        group_value = body.group if body.group != "" else None
        await nm.patch_metadata(
            db,
            node_id,
            name=body.name,
            group=group_value,
            by_user=claims["sub"],
        )

    updated = await nm.get_node(db, node_id)
    enriched = await _add_node_metrics(db, _node_to_response(updated), claims)  # type: ignore[arg-type]
    return NodeResponse(**enriched)


@router.post(
    "/{node_id}/configure",
    response_model=NodeResponse,
    summary="Confirm node name+group after enrollment handshake (Operator+)",
)
async def configure_node(
    node_id: Annotated[str, Path(description="Node UUID")],
    body: ConfigureRequest,
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    nm: NodeManager = Depends(get_node_manager),
) -> NodeResponse:
    """
    Operator confirms the Worker's name and group after Ed25519 handshake.
    Transitions UNCONFIGURED -> CONNECTED.
    """
    if is_demo(claims):
        demo_node = get_demo_node(node_id)
        if demo_node is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
        demo_node["name"] = body.name
        demo_node["node_group"] = body.group or ""
        if demo_node["state"] == "UNCONFIGURED":
            demo_node["state"] = "CONNECTED"
        demo_node["updated_at"] = time.time()
        enriched_demo = await _add_node_metrics(db, _node_to_response(demo_node), claims)
        return NodeResponse(**enriched_demo)

    existing = await nm.get_node(db, node_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    if existing["state"] != NodeState.UNCONFIGURED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Node is not awaiting configuration (state={existing['state']}).",
        )

    try:
        await nm.configure_node(db, node_id, name=body.name, group=body.group)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    updated = await nm.get_node(db, node_id)
    enriched = await _add_node_metrics(db, _node_to_response(updated), claims)  # type: ignore[arg-type]
    return NodeResponse(**enriched)


# ---------------------------------------------------------------------------
# Bulk Status
# ---------------------------------------------------------------------------


@router.get(
    "/bulk/status",
    response_model=BulkStatusResponse,
    summary="Get bulk status metrics and container counts for all online nodes (Operator+)",
)
async def get_bulk_status(
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    nm: NodeManager = Depends(get_node_manager),
) -> BulkStatusResponse:
    """Get the latest metrics snapshots and container counts for all nodes in bulk."""
    import json

    if is_demo(claims):
        demo_statuses = {}
        for node_id in ["demo-node-01", "demo-node-02", "demo-node-03"]:
            is_online = node_id in ("demo-node-01", "demo-node-02")
            if is_online:
                snaps = get_demo_metrics(node_id, limit=1)
                if snaps:
                    snap = snaps[0]
                    demo_statuses[node_id] = BulkNodeStatus(
                        cpu=snap.get("cpu_percent"),
                        mem=snap.get("mem_percent"),
                        disk=snap.get("disk_percent"),
                        uptime=snap.get("uptime_seconds"),
                        containers_count=4 if node_id == "demo-node-01" else 0,
                    )
            else:
                demo_statuses[node_id] = BulkNodeStatus()
        return BulkStatusResponse(statuses=demo_statuses)

    # Real mode
    # 1. Fetch latest snapshots using window function
    snapshots_map = {}
    async with db.execute("""
        WITH RankedSnapshots AS (
            SELECT
                node_id,
                cpu_percent,
                mem_percent,
                disk_percent,
                uptime_seconds,
                ROW_NUMBER() OVER (PARTITION BY node_id ORDER BY collected_at DESC) as rn
            FROM metrics_snapshots
        )
        SELECT node_id, cpu_percent, mem_percent, disk_percent, uptime_seconds
        FROM RankedSnapshots
        WHERE rn = 1
        """) as cursor:
        for row in await cursor.fetchall():
            snapshots_map[row["node_id"]] = {
                "cpu": row["cpu_percent"],
                "mem": row["mem_percent"],
                "disk": row["disk_percent"],
                "uptime": row["uptime_seconds"],
            }

    # 2. Combine with container count from nodes cached_containers_json
    statuses = {}
    async with db.execute("SELECT id, cached_containers_json FROM nodes") as cursor:
        for row in await cursor.fetchall():
            node_id = row["id"]
            snap = snapshots_map.get(node_id, {})

            containers_count = None
            cached_containers = row["cached_containers_json"]
            if cached_containers:
                try:
                    conts = json.loads(cached_containers)
                    if isinstance(conts, list):
                        containers_count = len(conts)
                except Exception:
                    pass

            statuses[node_id] = BulkNodeStatus(
                cpu=snap.get("cpu"),
                mem=snap.get("mem"),
                disk=snap.get("disk"),
                uptime=snap.get("uptime"),
                containers_count=containers_count,
            )

    return BulkStatusResponse(statuses=statuses)


# ---------------------------------------------------------------------------
# Node Stats
# ---------------------------------------------------------------------------


@router.get(
    "/{node_id}/stats",
    response_model=NodeStatsResponse,
    summary="Get metrics snapshots for a node (Operator+)",
)
async def get_node_stats(
    node_id: Annotated[str, Path(description="Node UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    limit: Annotated[int, Query(ge=1, le=1440, description="Number of snapshots to return")] = 1440,
    nm: NodeManager = Depends(get_node_manager),
) -> NodeStatsResponse:
    """Return the latest metrics snapshots for a node, ordered by time descending."""
    # Demo mode: return mock metrics
    if is_demo(claims):
        demo_node = get_demo_node(node_id)
        if demo_node is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
        snapshots = get_demo_metrics(node_id, limit)
        return NodeStatsResponse(
            node_id=node_id,
            snapshots=[MetricsSnapshotResponse(**s) for s in snapshots],
        )

    # Verify node exists
    node = await nm.get_node(db, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    import json
    rows: list[dict] = []
    async with db.execute(
        """
        SELECT
            collected_at,
            cpu_percent, cpu_load_1m, cpu_load_5m, cpu_load_15m, cpu_cores,
            mem_total_bytes, mem_used_bytes, mem_percent,
            swap_total_bytes, swap_used_bytes,
            disk_total_bytes, disk_used_bytes, disk_percent,
            uptime_seconds, processes, disks_json
        FROM metrics_snapshots
        WHERE node_id = ?
        ORDER BY collected_at DESC
        LIMIT ?
        """,
        (node_id, limit),
    ) as cursor:
        for row in await cursor.fetchall():
            d = dict(row)
            if d.get("disks_json"):
                try:
                    d["disks"] = json.loads(d["disks_json"])
                except Exception:
                    d["disks"] = None
            rows.append(d)

    return NodeStatsResponse(
        node_id=node_id,
        snapshots=[MetricsSnapshotResponse(**r) for r in rows],
    )


# ---------------------------------------------------------------------------
# Node Logs
# ---------------------------------------------------------------------------


@router.get(
    "/{node_id}/logs",
    response_model=LogsResponse,
    summary="Get live logs from a node (Operator+)",
)
async def get_node_logs(
    node_id: Annotated[str, Path(description="Node UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    lines: Annotated[int, Query(ge=1, le=500, description="Number of log lines")] = 50,
    service: Annotated[
        str | None, Query(description="systemd service name (uses journalctl)")
    ] = None,
    path: Annotated[
        str | None, Query(description="Log file path on the worker (/var/log/ only)")
    ] = None,
    nm: NodeManager = Depends(get_node_manager),
    port: WorkerQueryPort = Depends(get_worker_query_port),
) -> LogsResponse:
    """
    Fetch live logs from a Worker via INTENT.

    Supports two modes:
      - **Service logs** (`service` param): uses `journalctl -u <service>` on the Worker
      - **File logs** (`path` param): reads a log file from `/var/log/` on the Worker

    If neither `service` nor `path` is specified, defaults to `/var/log/syslog`.
    """
    # Demo mode: return mock logs
    if is_demo(claims):
        demo_node = get_demo_node(node_id)
        if demo_node is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
        _effective_path = path if path else "/var/log/syslog"
        logs = get_demo_logs(service, _effective_path, lines)
        return LogsResponse(
            node_id=node_id,
            output="\n".join(logs),
            lines=len(logs),
            service=service,
            path=_effective_path if not service else None,
        )

    node = await nm.get_node(db, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    effective_path = path
    if service:
        action = WorkerAction.READ_LOGS_SERVICE
        params = {"service": service, "lines": lines}
    elif effective_path:
        clean_path = os.path.normpath(effective_path)
        if not clean_path.startswith("/var/log/") and clean_path != "/var/log":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Path outside allowed prefix (/var/log/)",
            )
        action = WorkerAction.READ_LOGS
        params = {"path": clean_path, "lines": lines}
    else:
        action = WorkerAction.READ_LOGS
        effective_path = "/var/log/syslog"
        params = {"path": effective_path, "lines": lines}

    try:
        result = await port.query(
            node_id, action, params, timeout=15.0
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Worker did not respond to log request in time",
        )

    return LogsResponse(
        node_id=node_id,
        output=result.get("output", ""),
        lines=lines,
        service=service,
        path=effective_path if not service else None,
        error=result.get("error") if not result.get("success") else None,
    )
