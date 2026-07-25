from __future__ import annotations

"""
Vigile — Investigations API Router

Endpoints:
  - GET /api/investigations → List investigation records
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from master.api.deps import require_role
from master.core.investigation_manager import investigation_manager
from master.db.database import get_db_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/investigations", tags=["investigations"])


@router.get("")
async def list_investigations(
    request: Request,
    node_id: str | None = Query(None, description="Filter by node ID"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status (queued, in_progress, completed, failed)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: dict = Depends(require_role("admin")),
):
    """List investigation records with optional filters."""
    db = get_db_conn()
    results = await investigation_manager.get_investigations(
        db=db,
        node_id=node_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return {"total": len(results), "investigations": results}
