"""
Vigile — Chat API

Endpoints for the Human-in-the-Loop AI chat interface.

Endpoints:
  POST   /api/chat                             Operator+: send message → SSE stream
  GET    /api/chat/proposals                   Operator+: list pending proposals
  GET    /api/chat/proposals/{proposal_id}     Operator+: proposal detail
  POST   /api/chat/proposals/{proposal_id}/approve  Operator+: approve → execute
  POST   /api/chat/proposals/{proposal_id}/reject   Operator+: reject
"""

import json
import logging
import time
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from master.api.deps import (
    DB,
    CurrentUser,
    get_llm_client,
    get_node_manager,
    get_structured_llm,
    require_role,
)
from master.core.action_proposal import ActionProposal
from master.core.audit import log_action
from master.core.llm_client import LLMClient
from master.core.node_manager import NodeManager
from master.core.structured_llm import StructuredLLM

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# POST /api/chat — Streaming chat
# ---------------------------------------------------------------------------


@router.post(
    "",
    summary="Send a message and stream the AI response (Operator+)",
    response_class=StreamingResponse,
)
async def chat(
    body: dict[str, Any],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    nm: NodeManager = Depends(get_node_manager),
    llm: LLMClient = Depends(get_llm_client),
    sllm: StructuredLLM = Depends(get_structured_llm),
) -> StreamingResponse:
    """
    Send a message to the AI. Returns a SSE stream with tokens and tool calls.

    Request body:
      {
        "message": "What's the status of my server?",
        "node_id": "optional-node-uuid",
        "history": []  # optional conversation history
      }

    SSE events:
      data: {"type": "token", "content": "..."}
      data: {"type": "proposal", "proposal_id": "...", "action": "...", "risk_level": "..."}
      data: {"type": "error", "detail": "..."}
      data: {"type": "done"}
    """
    message = body.get("message", "")
    node_id = body.get("node_id")
    history = body.get("history", [])

    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    # Build system prompt with node context if specified
    system_prompt = await _build_chat_context(nm, db, node_id)

    # Build messages array
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    async def _event_stream() -> Any:
        token_buffer = ""
        full_reasoning = ""
        tool_calls_detected: list[dict] = []

        try:
            async for event in llm.stream(messages, temperature=0.3):
                if event["type"] == "token":
                    token_buffer += event["content"]
                    yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"

                elif event["type"] == "tool_call":
                    tool_calls_detected.append(event["tool_calls"])

                elif event["type"] == "done":
                    # LLM stream done — continue to proposal extraction below
                    pass

                elif event["type"] == "error":
                    yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
                    yield f"data: {json.dumps({'type': 'done'}, separators=(',', ':'))}\n\n"
                    return

            # After streaming, try to extract a structured proposal
            if node_id:
                proposal = await _try_extract_proposal(
                    sllm, node_id, message, token_buffer, claims["sub"]
                )
                if proposal:
                    await _persist_proposal(db, proposal)
                    yield (
                        f"data: {json.dumps({
                            'type': 'proposal',
                            'proposal_id': proposal.id,
                            'action': proposal.action,
                            'risk_level': proposal.risk_level,
                            'reasoning': proposal.reasoning,
                        }, separators=(',', ':'))}\n\n"
                    )

            # Final done event
            yield f"data: {json.dumps({'type': 'done'}, separators=(',', ':'))}\n\n"

        except Exception as exc:
            logger.exception("Chat streaming error")
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)}, separators=(',', ':'))}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, separators=(',', ':'))}\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Proposals CRUD
# ---------------------------------------------------------------------------


@router.get(
    "/proposals",
    summary="List action proposals (Operator+)",
)
async def list_proposals(
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    status_filter: str | None = Query(
        default=None, description="Filter by status (PENDING, APPROVED, etc.)"
    ),
) -> list[dict[str, Any]]:
    """List all action proposals, optionally filtered by status."""
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
    return rows


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
    async with db.execute(
        "SELECT * FROM action_proposals WHERE id = ?", (proposal_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    return dict(row)


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
    # Fetch proposal
    async with db.execute(
        "SELECT * FROM action_proposals WHERE id = ?", (proposal_id,)
    ) as cursor:
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
            executed_at = ?, result_json = ?
        WHERE id = ?
        """,
        (
            db_data["status"],
            db_data["approved_by"],
            db_data["updated_at"],
            db_data["executed_at"],
            db_data["result_json"],
            proposal.id,
        ),
    )
    await db.commit()

    # Audit
    await log_action(
        db,
        user_id=claims["sub"],
        action="PROPOSAL_APPROVED",
        node_id=proposal.node_id,
        details={
            "proposal_id": proposal.id,
            "action": proposal.action,
            "status": proposal.status,
            "result": db_data["result_json"],
        },
    )

    return db_data


@router.post(
    "/proposals/{proposal_id}/reject",
    summary="Reject a pending action proposal (Operator+)",
)
async def reject_proposal(
    proposal_id: Annotated[str, Path(description="Proposal UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    body: dict[str, str] = {},
) -> dict[str, Any]:
    """
    Reject a pending action proposal. The LLM will be informed
    and can propose an alternative.
    """
    reason = body.get("reason", "")

    async with db.execute(
        "SELECT * FROM action_proposals WHERE id = ?", (proposal_id,)
    ) as cursor:
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
        action="PROPOSAL_REJECTED",
        node_id=proposal.node_id,
        details={
            "proposal_id": proposal.id,
            "action": proposal.action,
            "reason": reason,
        },
    )

    return db_data


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _build_chat_context(
    nm: NodeManager, db: DB, node_id: str | None
) -> str:
    """
    Build a system prompt with node context.
    If no node_id is specified, returns a generic sysadmin prompt.
    """
    if not node_id:
        return (
            "You are a server fleet management AI assistant. "
            "You help operators monitor and manage their servers. "
            "When an action is needed, you can propose it and the operator will approve it. "
            "Be concise, technical, and precise."
        )

    node = await nm.get_node(db, node_id)
    if node is None:
        return (
            "You are a server fleet management AI assistant. "
            "The specified node was not found."
        )

    # Gather node context
    context_parts = [
        f"Node: {node.get('name', 'unknown')} (ID: {node_id[:8]}...)",
        f"State: {node.get('state', 'unknown')}",
        f"OS: {node.get('os', 'unknown')} / {node.get('arch', 'unknown')}",
        f"Hostname: {node.get('hostname', 'unknown')}",
    ]

    if node.get("state") in ("CONNECTED",):
        context_parts.append("Status: online")

        # Fetch latest stats
        try:
            async with db.execute(
                "SELECT cpu_percent, mem_percent, disk_percent, uptime_seconds "
                "FROM metrics_snapshots WHERE node_id = ? "
                "ORDER BY collected_at DESC LIMIT 1",
                (node_id,),
            ) as cursor:
                row = await cursor.fetchone()
            if row:
                context_parts.append(
                    f"CPU: {row['cpu_percent']:.1f}% | "
                    f"RAM: {row['mem_percent']:.1f}% | "
                    f"Disk: {row['disk_percent']:.1f}% | "
                    f"Uptime: {row['uptime_seconds'] / 3600:.0f}h"
                )
        except Exception:
            pass

    base = (
        "You are a server fleet management AI assistant. "
        "You help operators monitor and manage their servers.\n\n"
        "Available actions you can propose (use the proper action name):\n"
        "- GET_STATS: Collect CPU/RAM/disk metrics\n"
        "- READ_LOGS: Read log files from /var/log/\n"
        "- LIST_SERVICES: List systemd services\n"
        "- STATUS_SERVICE: Get status of a specific service\n"
        "- RESTART_SERVICE: Restart a systemd service\n"
        "- LIST_CONTAINERS: List Docker containers\n"
        "- RESTART_CONTAINER: Restart a Docker container\n\n"
        "Current node context:\n"
    )

    return base + "\n".join(f"- {line}" for line in context_parts)


class _ProposalRequest(BaseModel):
    """Simplified model for LLM to fill — only needs action/reasoning/risk."""
    action: str = ""
    params: dict[str, Any] = {}
    reasoning: str = ""
    risk_level: str = "MEDIUM"


async def _try_extract_proposal(
    sllm: StructuredLLM,
    node_id: str,
    user_message: str,
    ai_response: str,
    user_id: str,
) -> ActionProposal | None:
    """
    After the AI responds, try to extract an action proposal
    from the conversation context.
    """
    try:
        req = await sllm.create(
            _ProposalRequest,
            [
                {"role": "system", "content": (
                    "Based on the conversation, determine if a server action is needed. "
                    "If yes, output action, params, reasoning, and risk_level as JSON. "
                    "Set action to 'NONE' if no action is needed."
                )},
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": ai_response},
                {"role": "user", "content": (
                    f"Is a {_list_available_actions()} action needed? "
                    "Reply with JSON only."
                )},
            ],
            temperature=0.1,
            max_retries=2,
        )
        if not req.action or req.action == "NONE":
            return None
        proposal = ActionProposal(
            node_id=node_id,
            action=req.action,
            params=req.params,
            reasoning=req.reasoning,
            risk_level=req.risk_level or "MEDIUM",
            created_by="ai",
        )
        return proposal
    except Exception as exc:
        logger.warning("Could not extract proposal: %s", exc)
        return None


async def _persist_proposal(db: DB, proposal: ActionProposal) -> None:
    """Insert a new action proposal into the database."""
    data = proposal.to_db_dict()
    await db.execute(
        """
        INSERT INTO action_proposals
            (id, node_id, action, params_json, reasoning, risk_level,
             status, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["id"],
            data["node_id"],
            data["action"],
            data["params_json"],
            data["reasoning"],
            data["risk_level"],
            data["status"],
            data["created_by"],
            data["created_at"],
            data["updated_at"],
        ),
    )
    await db.commit()
    logger.info(
        "Proposal created: id=%s action=%s node=%s",
        proposal.id, proposal.action, proposal.node_id,
    )


def _list_available_actions() -> str:
    return (
        "GET_STATS, READ_LOGS, LIST_SERVICES, STATUS_SERVICE, "
        "RESTART_SERVICE, LIST_CONTAINERS, RESTART_CONTAINER"
    )
