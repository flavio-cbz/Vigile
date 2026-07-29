"""
Vigile — Chat API: action proposals endpoints
"""

from __future__ import annotations

import logging
import time
from typing import Annotated, Any

from fastapi import Body, Depends, HTTPException, Path, status

from master.api.chat_helpers import _normalize_action_proposal, _persist_proposal
from master.api.chat_router import router
from master.api.demo_data import (
    DEMO_PROPOSALS,
    get_demo_proposal,
    is_demo,
    update_demo_proposal,
)
from master.api.deps import DB, get_node_manager, require_role
from master.core.action_proposal import ActionProposal
from master.core.audit import AuditAction, log_action
from master.core.node_manager import NodeManager

logger = logging.getLogger(__name__)


@router.get(
    "/proposals",
    summary="List action proposals (Operator+)",
)
async def list_proposals(
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    """List all action proposals, optionally filtered by status."""
    if is_demo(claims):
        props = DEMO_PROPOSALS
        if status_filter:
            props = [p for p in props if p["status"] == status_filter]
        return [ActionProposal.from_db_row(p).model_dump() for p in props]

    if status_filter:
        async with db.execute(
            "SELECT * FROM action_proposals WHERE status = ? ORDER BY created_at DESC",
            (status_filter,),
        ) as cursor:
            rows = [dict(r) for r in await cursor.fetchall()]
    else:
        async with db.execute(
            "SELECT * FROM action_proposals ORDER BY created_at DESC",
        ) as cursor:
            rows = [dict(r) for r in await cursor.fetchall()]
    return [ActionProposal.from_db_row(row).model_dump() for row in rows]


@router.get(
    "/proposals/{proposal_id}",
    summary="Get proposal detail (Operator+)",
)
async def get_proposal(
    proposal_id: Annotated[str, Path(description="Proposal UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
) -> dict[str, Any]:
    """Fetch a single action proposal by ID."""
    if is_demo(claims):
        prop = get_demo_proposal(proposal_id)
        if prop is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
        return ActionProposal.from_db_row(prop).model_dump()

    async with db.execute("SELECT * FROM action_proposals WHERE id = ?", (proposal_id,)) as cursor:
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    return ActionProposal.from_db_row(dict(row)).model_dump()


@router.post(
    "/proposals/{proposal_id}/approve",
    summary="Approve and execute an action proposal (Operator+)",
)
async def approve_proposal(
    proposal_id: Annotated[str, Path(description="Proposal UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    nm: NodeManager = Depends(get_node_manager),
) -> dict[str, Any]:
    """
    Approve a pending action proposal and execute it immediately.

    The intent is sent to the Worker via the existing WebSocket.
    The proposal status becomes EXECUTED or FAILED based on the result.
    """
    if is_demo(claims):
        prop = get_demo_proposal(proposal_id)
        if prop is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
        if prop["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Proposal is {prop['status']}, not PENDING",
            )
        updates = {
            "status": "EXECUTED",
            "approved_by": claims["sub"],
            "executed_at": time.time(),
            "result_json": '{"success": true, "simulated": true}',
        }
        updated = update_demo_proposal(proposal_id, updates)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Proposal not found",
            )
        return ActionProposal.from_db_row(updated).model_dump()

    # Fetch proposal
    async with db.execute("SELECT * FROM action_proposals WHERE id = ?", (proposal_id,)) as cursor:
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")

    proposal = ActionProposal.from_db_row(dict(row))

    if proposal.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Proposal is {proposal.status}, not PENDING",
        )

    # Approve
    proposal.approve(claims["sub"])

    # Execute intent
    try:
        validation_error = await _normalize_action_proposal(db, nm, proposal)
        if validation_error:
            proposal.complete(success=False, result_data={"error": validation_error})
        else:
            result = await nm.send_intent(
                proposal.node_id,
                {"action": proposal.action, "params": proposal.params},
                timeout=15.0,
            )
            success = result.get("success", False)
            proposal.complete(success=success, result_data=result)
    except RuntimeError as exc:
        proposal.complete(success=False, result_data={"error": str(exc)})
    except TimeoutError:
        proposal.complete(success=False, result_data={"error": "Worker did not respond in time"})

    # Persist
    db_data = proposal.to_db_dict()
    await db.execute(
        """
        UPDATE action_proposals SET
            status = ?, approved_by = ?, updated_at = ?,
            executed_at = ?, result_json = ?, params_json = ?
        WHERE id = ?
        """,
        (
            db_data["status"],
            db_data["approved_by"],
            db_data["updated_at"],
            db_data["executed_at"],
            db_data["result_json"],
            db_data["params_json"],
            proposal.id,
        ),
    )
    await db.commit()

    # Audit
    await log_action(
        db,
        user_id=claims["sub"],
        action=AuditAction.PROPOSAL_APPROVED,
        node_id=proposal.node_id,
        details={
            "proposal_id": proposal.id,
            "action": proposal.action,
            "target": proposal.params.get("target")
            or proposal.params.get("container_id")
            or proposal.params.get("container")
            or proposal.params.get("service")
            or "",
            "status": proposal.status,
            "result": db_data["result_json"],
        },
    )

    return proposal.model_dump()


@router.post(
    "/proposals/{proposal_id}/reject",
    summary="Reject a pending action proposal (Operator+)",
)
async def reject_proposal(
    proposal_id: Annotated[str, Path(description="Proposal UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    body: Annotated[dict[str, str] | None, Body()] = None,
) -> dict[str, Any]:
    """
    Reject a pending action proposal. The LLM will be informed
    and can propose an alternative.
    """
    reason = (body or {}).get("reason", "")

    if is_demo(claims):
        prop = get_demo_proposal(proposal_id)
        if prop is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
        if prop["status"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Proposal is {prop['status']}, not PENDING",
            )
        updates = {
            "status": "REJECTED",
            "rejected_by": claims["sub"],
            "rejection_reason": reason,
        }
        updated = update_demo_proposal(proposal_id, updates)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Proposal not found",
            )
        return ActionProposal.from_db_row(updated).model_dump()

    async with db.execute("SELECT * FROM action_proposals WHERE id = ?", (proposal_id,)) as cursor:
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")

    proposal = ActionProposal.from_db_row(dict(row))

    if proposal.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Proposal is {proposal.status}, not PENDING",
        )

    proposal.reject(claims["sub"], reason)
    db_data = proposal.to_db_dict()

    await db.execute(
        """
        UPDATE action_proposals SET
            status = ?, rejected_by = ?, rejection_reason = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            db_data["status"],
            db_data["rejected_by"],
            db_data["rejection_reason"],
            db_data["updated_at"],
            proposal.id,
        ),
    )
    await db.commit()

    await log_action(
        db,
        user_id=claims["sub"],
        action=AuditAction.PROPOSAL_REJECTED,
        node_id=proposal.node_id,
        details={
            "proposal_id": proposal.id,
            "action": proposal.action,
            "target": proposal.params.get("target")
            or proposal.params.get("container")
            or proposal.params.get("service")
            or "",
            "reason": reason,
        },
    )

    return proposal.model_dump()
