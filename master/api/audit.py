"""
Vigile — Audit API
"""

from __future__ import annotations
import json
import logging
from typing import Annotated, Any
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from master.api.deps import DB, require_role
from master.api.demo_data import is_demo, DEMO_AUDIT_ENTRIES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit", tags=["audit"])


class AuditEntryResponse(BaseModel):
    id: str
    sequence: int
    timestamp: float
    user_id: str
    action: str
    node_id: str | None
    details: dict[str, Any]
    previous_hash: str
    entry_hash: str


class AuditListResponse(BaseModel):
    entries: list[AuditEntryResponse]
    limit: int
    offset: int
    total: int


@router.get("", response_model=AuditListResponse, summary="List audit log entries (Operator+)")
async def list_audit_entries(
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Result offset"),
    node_id: str | None = Query(default=None, description="Filter by node ID"),
    action: str | None = Query(default=None, description="Filter by action name"),
) -> AuditListResponse:
    """Fetch audit log entries, ordered by sequence descending, with pagination."""
    # Demo mode: return mock data, no DB queries
    if is_demo(claims):
        entries = DEMO_AUDIT_ENTRIES
        if node_id:
            entries = [e for e in entries if e.get("node_id") == node_id]
        if action:
            entries = [e for e in entries if e.get("action") == action]
        total = len(entries)
        sliced = entries[offset : offset + limit]
        return AuditListResponse(
            entries=[AuditEntryResponse(**e) for e in sliced],
            limit=limit,
            offset=offset,
            total=total,
        )

    conditions = []
    params: list[Any] = []

    if node_id:
        conditions.append("node_id = ?")
        params.append(node_id)
    if action:
        conditions.append("action = ?")
        params.append(action)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # Get total count
    count_sql = f"SELECT COUNT(*) as cnt FROM audit_log {where}"
    async with db.execute(count_sql, params) as cursor:
        row = await cursor.fetchone()
        total = row["cnt"] if row else 0

    # Get paginated results
    sql = f"""
        SELECT id, sequence, timestamp, user_id, action, node_id,
               details_json, previous_hash, entry_hash
        FROM audit_log
        {where}
        ORDER BY sequence DESC
        LIMIT ? OFFSET ?
    """
    entries = []
    query_params = params + [limit, offset]
    async with db.execute(sql, query_params) as cursor:
        async for r in cursor:
            entries.append(
                AuditEntryResponse(
                    id=r["id"],
                    sequence=r["sequence"],
                    timestamp=r["timestamp"],
                    user_id=r["user_id"],
                    action=r["action"],
                    node_id=r["node_id"],
                    details=json.loads(r["details_json"]),
                    previous_hash=r["previous_hash"],
                    entry_hash=r["entry_hash"],
                )
            )

    return AuditListResponse(
        entries=entries,
        limit=limit,
        offset=offset,
        total=total,
    )
