from __future__ import annotations

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
from difflib import SequenceMatcher
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from master.api.demo_data import (
    DEMO_PROPOSALS,
    delete_demo_chat_session,
    get_demo_chat_session,
    get_demo_chat_sessions,
    get_demo_chat_tokens,
    get_demo_proposal,
    get_demo_proposal_from_text,
    is_demo,
    save_demo_chat_session,
    update_demo_proposal,
)
from master.api.deps import (
    DB,
    get_llm_client,
    get_node_manager,
    get_settings,
    get_structured_llm,
    require_role,
)
from master.core.action_proposal import ActionProposal
from master.core.audit import AuditAction, log_action
from master.core.llm_client import LLMClient
from master.core.node_manager import NodeManager
from master.core.structured_llm import StructuredLLM
from master.core.plugin_helpers import parse_container_list

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
    settings: Any = Depends(get_settings),
    accept_language: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """
    Send a message to the AI. Returns a SSE stream with tokens and tool calls.

    Request body:
      {
        "message": "What's the status of my server?",
        "node_id": "optional-node-uuid",
        "history": [],  # optional conversation history
        "session_id": "optional-session-uuid"
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
    session_id = body.get("session_id")

    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    # Demo mode: intercept with simulated streaming (no LLM, no DB)
    if is_demo(claims):

        async def _demo_event_stream():
            demo_tokens = get_demo_chat_tokens(message)
            for token in demo_tokens:
                yield f"data: {json.dumps({'type': 'token', 'content': token + ' '}, separators=(',', ':'))}\n\n"

            # Look for a pending demo proposal
            demo_proposal = get_demo_proposal_from_text(message)
            if demo_proposal:
                yield f"data: {json.dumps({'type': 'proposal', 'proposal_id': demo_proposal['id'], 'action': demo_proposal['action'], 'risk_level': demo_proposal['risk_level'], 'reasoning': demo_proposal['reasoning']}, separators=(',', ':'))}\n\n"

            # Save session to in-memory dict if session_id provided
            if session_id:
                new_history = list(history) + [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": " ".join(demo_tokens)},
                ]
                title = message[:40] + ("..." if len(message) > 40 else "")
                save_demo_chat_session(
                    session_id=session_id,
                    user_id=claims["sub"],
                    node_id=node_id,
                    title=title,
                    history=new_history,
                )

            yield f"data: {json.dumps({'type': 'done'}, separators=(',', ':'))}\n\n"

        return StreamingResponse(
            _demo_event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # If session_id is provided and history is empty, try loading it from DB
    if session_id and not history:
        async with db.execute(
            "SELECT history_json FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, claims["sub"]),
        ) as cursor:
            sess_row = await cursor.fetchone()
        if sess_row:
            try:
                history = json.loads(sess_row["history_json"])
            except Exception:
                logger.debug("Failed to parse chat history JSON, using empty list")
                history = []

    # Build system prompt with node context if specified
    locale = "fr"
    if accept_language and accept_language.lower().startswith("en"):
        locale = "en"

    # Get active alerts for suggestions and prompt enrichment
    active_alerts = []
    alert_suggestions = []
    if node_id and node_id != "all":
        active_alerts = alert_engine.get_active_alerts(node_id)
        for a in active_alerts:
            alert_name = a.get("alert_name")
            if locale == "en":
                alert_suggestions.append(f"Why is {alert_name} active?")
            else:
                alert_suggestions.append(f"Pourquoi l'alerte {alert_name} est-elle active ?")

    system_prompt = await _build_chat_context(nm, db, node_id, locale)

    # Build messages array
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    # Define tools available to OpenAI-compatible function calling
    available_tools = [
        {
            "type": "function",
            "function": {
                "name": "list_containers",
                "description": "List Docker containers on the node",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_services",
                "description": "List systemd services on the node",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_logs",
                "description": "Read system logs or a specific log file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file": {
                            "type": "string",
                            "description": "Optional log file path (e.g. /var/log/syslog)",
                        }
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "status_service",
                "description": "Get detailed status of a specific systemd service",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service": {"type": "string", "description": "Service name"}
                    },
                    "required": ["service"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "restart_service",
                "description": "Restart a specific systemd service (Requires approval)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service": {"type": "string", "description": "Service name"}
                    },
                    "required": ["service"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "restart_container",
                "description": "Restart a specific Docker container (Requires approval)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "container_id": {"type": "string", "description": "Container ID or name"}
                    },
                    "required": ["container_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "disk_scan",
                "description": "Scan disk usage tree on the node (returns treemap data)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Root path to scan (default: /)",
                        },
                        "max_depth": {
                            "type": "integer",
                            "description": "Maximum directory depth (0-20, default: 4)",
                        },
                        "min_size_bytes": {
                            "type": "integer",
                            "description": "Minimum file size in bytes to include",
                        },
                    },
                },
            },
        },
    ]

    async def _event_stream() -> Any:
        token_buffer = ""
        current_messages = list(messages)

        # Yield suggestions first if any alerts exist
        if alert_suggestions:
            yield f"data: {json.dumps({'type': 'suggestions', 'suggestions': alert_suggestions}, separators=(',', ':'))}\n\n"

        # Emit a meta event so the UI can surface model + node context.
        yield f"data: {json.dumps({'type': 'meta', 'model': settings.llm_model, 'node_id': node_id}, separators=(',', ':'))}\n\n"

        try:
            # We run a loop for the ReAct/function calling steps
            for step in range(5):
                # Call LLM stream with tools configuration
                tool_calls_buf = []
                active_tool_call = None

                async for event in llm.stream(
                    current_messages,
                    tools=available_tools,
                    temperature=settings.llm_chat_temperature,
                ):
                    if event["type"] == "token":
                        token_buffer += event["content"]
                        yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"

                    elif event["type"] == "tool_call":
                        # Aggregate streaming tool call chunks
                        for tc in event["tool_calls"]:
                            idx = tc.get("index", 0)
                            while len(tool_calls_buf) <= idx:
                                tool_calls_buf.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                            
                            target_tc = tool_calls_buf[idx]
                            if tc.get("id"):
                                target_tc["id"] = tc["id"]
                            if tc.get("type"):
                                target_tc["type"] = tc["type"]
                            if "function" in tc:
                                fn = tc["function"]
                                if fn.get("name"):
                                    target_tc["function"]["name"] += fn["name"]
                                if fn.get("arguments"):
                                    target_tc["function"]["arguments"] += fn["arguments"]

                    elif event["type"] == "error":
                        yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
                        yield f"data: {json.dumps({'type': 'done'}, separators=(',', ':'))}\n\n"
                        return

                # If no tool calls were requested, we are done
                if not tool_calls_buf:
                    break

                # Process the tool calls
                assistant_tool_calls = []
                for tc in tool_calls_buf:
                    tc_id = tc.get("id")
                    fn_name = tc.get("function", {}).get("name")
                    fn_args_str = tc.get("function", {}).get("arguments", "{}")
                    try:
                        fn_args = json.loads(fn_args_str)
                    except Exception:
                        logger.warning("Failed to parse LLM tool call arguments JSON: %s", fn_args_str)
                        fn_args = {}

                    assistant_tool_calls.append({
                        "id": tc_id,
                        "type": "function",
                        "function": {"name": fn_name, "arguments": fn_args_str}
                    })

                    # Notify frontend that tool execution is starting
                    yield f"data: {json.dumps({'type': 'tool_executing', 'tool': fn_name, 'node_id': node_id}, separators=(',', ':'))}\n\n"

                    tool_start_ts = time.monotonic()
                    tool_success = False

                    # 1. READ tools execute in direct loop
                    if fn_name in ("list_containers", "list_services", "read_logs", "status_service", "disk_scan") and node_id and node_id != "all":
                        action_map = {
                            "list_containers": "LIST_CONTAINERS",
                            "list_services": "LIST_SERVICES",
                            "read_logs": "READ_LOGS",
                            "status_service": "STATUS_SERVICE",
                            "disk_scan": "DISK_SCAN",
                        }
                        action = action_map[fn_name]
                        params = {}
                        if fn_name == "read_logs" and "file" in fn_args:
                            params["file"] = fn_args["file"]
                        elif fn_name == "status_service" and "service" in fn_args:
                            params["service"] = fn_args["service"]
                        elif fn_name == "disk_scan":
                            if "path" in fn_args:
                                params["path"] = fn_args["path"]
                            if "max_depth" in fn_args:
                                params["max_depth"] = fn_args["max_depth"]
                            if "min_size_bytes" in fn_args:
                                params["min_size_bytes"] = fn_args["min_size_bytes"]

                        try:
                            result = await nm.send_intent(node_id, {"action": action, "params": params}, timeout=15.0)
                            tool_output = json.dumps(result)
                            tool_success = bool(result.get("success", False))
                        except Exception as e:
                            tool_output = json.dumps({"success": False, "error": str(e)})

                        tool_duration_ms = int((time.monotonic() - tool_start_ts) * 1000)
                        yield f"data: {json.dumps({'type': 'tool_result', 'tool': fn_name, 'node_id': node_id, 'duration_ms': tool_duration_ms, 'success': tool_success}, separators=(',', ':'))}\n\n"

                        # Append assistant message with tool call call and tool response to history for next model step
                        current_messages.append({
                            "role": "assistant",
                            "content": token_buffer or None,
                            "tool_calls": assistant_tool_calls
                        })
                        current_messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": fn_name,
                            "content": tool_output
                        })
                    
                    # 2. WRITE tools require operator approval
                    elif fn_name in ("restart_service", "restart_container") and node_id and node_id != "all":
                        action = "RESTART_SERVICE" if fn_name == "restart_service" else "RESTART_CONTAINER"
                        params = {}
                        if fn_name == "restart_service" and "service" in fn_args:
                            params["service"] = fn_args["service"]
                        elif fn_name == "restart_container" and "container_id" in fn_args:
                            params["container_id"] = fn_args["container_id"]

                        # Construct ActionProposal dynamically
                        proposal = ActionProposal(
                            node_id=node_id,
                            action=action,
                            params=params,
                            reasoning=token_buffer or f"Proposé via assistant ReAct pour {fn_name}.",
                            risk_level="HIGH" if action == "RESTART_SERVICE" else "MEDIUM",
                            created_by="ai"
                        )
                        await _normalize_action_proposal(db, nm, proposal)
                        await _persist_proposal(db, proposal)

                        tool_duration_ms = int((time.monotonic() - tool_start_ts) * 1000)
                        # Emit tool_result with success=True since the proposal was persisted (deferred execution via approval).
                        yield f"data: {json.dumps({'type': 'tool_result', 'tool': fn_name, 'node_id': node_id, 'duration_ms': tool_duration_ms, 'success': True, 'proposal_id': proposal.id}, separators=(',', ':'))}\n\n"

                        # Emit proposal needed event
                        proposal_json = json.dumps(
                            {
                                "type": "proposal_needed",
                                "proposal_id": proposal.id,
                                "action": proposal.action,
                                "risk_level": proposal.risk_level,
                                "reasoning": proposal.reasoning,
                                "params": proposal.params,
                            },
                            separators=(",", ":"),
                        )
                        yield f"data: {proposal_json}\n\n"

                        # ReAct loop pauses/terminates when write tool is reached
                        yield f"data: {json.dumps({'type': 'done'}, separators=(',', ':'))}\n\n"
                        return

            # Save chat history to DB if session_id is provided
            if session_id:
                new_history = history + [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": token_buffer},
                ]
                now = time.time()
                history_str = json.dumps(new_history)

                async with db.execute(
                    "SELECT title FROM chat_sessions WHERE id = ? AND user_id = ?",
                    (session_id, claims["sub"]),
                ) as cursor:
                    sess_row = await cursor.fetchone()

                if sess_row:
                    await db.execute(
                        """
                        UPDATE chat_sessions SET
                            history_json = ?, updated_at = ?
                        WHERE id = ? AND user_id = ?
                        """,
                        (history_str, now, session_id, claims["sub"]),
                    )
                else:
                    title = message[:40] + ("..." if len(message) > 40 else "")
                    db_node_id = node_id
                    if db_node_id == "all":
                        db_node_id = None
                    await db.execute(
                        """
                        INSERT INTO chat_sessions (id, user_id, node_id, title, history_json, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (session_id, claims["sub"], db_node_id, title, history_str, now, now),
                    )
                await db.commit()

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


@router.get(
    "/suggestions",
    summary="Get context-aware chat prompt suggestions (Operator+)",
)
async def get_suggestions(
    node_id: str | None = Query(default=None),
    accept_language: Annotated[str | None, Header()] = None,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))] = None,
) -> list[str]:
    """
    Returns a list of recommended prompt suggestions based on active node alerts.
    """
    from master.core.alert_engine import alert_engine

    locale = "fr"
    if accept_language and accept_language.lower().startswith("en"):
        locale = "en"

    if not node_id or node_id == "all":
        if locale == "en":
            return [
                "List all offline servers",
                "Are there any critical alerts?",
                "Verify fleet status",
            ]
        else:
            return [
                "Lister tous les serveurs hors ligne",
                "Y a-t-il des alertes critiques en cours ?",
                "Vérifier la santé de la flotte",
            ]

    active_alerts = alert_engine.get_active_alerts(node_id)
    suggestions = []

    for alert in active_alerts:
        name = alert["alert_name"]
        if "disk" in name:
            if locale == "en":
                suggestions.append("Why is disk space full?")
                suggestions.append("Which files use the most space?")
            else:
                suggestions.append("Pourquoi l'espace disque est-il saturé ?")
                suggestions.append("Quels fichiers occupent le plus d'espace ?")
        elif "cpu" in name or "load" in name:
            if locale == "en":
                suggestions.append("Why is CPU usage so high?")
                suggestions.append("Which processes consume the most CPU?")
            else:
                suggestions.append("Pourquoi le CPU est-il si élevé ?")
                suggestions.append("Quels processus consomment le plus de CPU ?")
        elif "mem" in name or "ram" in name:
            if locale == "en":
                suggestions.append("Why is RAM usage high?")
                suggestions.append("Which processes consume the most memory?")
            else:
                suggestions.append("Pourquoi la RAM est-elle saturée ?")
                suggestions.append("Quels processus consomment le plus de mémoire ?")
        elif "reboot" in name:
            if locale == "en":
                suggestions.append("When did the server reboot?")
            else:
                suggestions.append("Quand le serveur a-t-il redémarré ?")
        elif "lost" in name or "stale" in name:
            if locale == "en":
                suggestions.append("Why did the server disconnect?")
            else:
                suggestions.append("Pourquoi le serveur s'est-il déconnecté ?")

    # Add generic fallback suggestions if needed
    if len(suggestions) < 3:
        if locale == "en":
            suggestions.append("What are the active Docker containers?")
        else:
            suggestions.append("Quels sont les conteneurs Docker actifs ?")
    if len(suggestions) < 3:
        if locale == "en":
            suggestions.append("Verify the server general status")
        else:
            suggestions.append("Vérifie l'état général du serveur")
    if len(suggestions) < 3:
        if locale == "en":
            suggestions.append("Show the latest system logs")
        else:
            suggestions.append("Affiche les derniers logs système")

    # Return unique items up to 4
    seen = set()
    result = []
    for s in suggestions:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result[:4]


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
    body: dict[str, str] = {},
) -> dict[str, Any]:
    """
    Reject a pending action proposal. The LLM will be informed
    and can propose an alternative.
    """
    reason = body.get("reason", "")

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


# ---------------------------------------------------------------------------
# Chat Sessions CRUD (Operator+)
# ---------------------------------------------------------------------------


class _SessionSaveRequest(BaseModel):
    id: str | None = None
    node_id: str | None = None
    title: str
    history: list[dict[str, Any]] = []


@router.get(
    "/sessions",
    summary="List chat sessions (Operator+)",
)
async def list_sessions(
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    node_id: str | None = Query(default=None, description="Filter by node ID"),
) -> list[dict[str, Any]]:
    """List all chat sessions for the logged in user, optionally filtered by node_id."""
    if is_demo(claims):
        return get_demo_chat_sessions(claims["sub"])

    user_id = claims["sub"]
    params: tuple[str, ...]
    if node_id and node_id != "all":
        query = (
            "SELECT * FROM chat_sessions WHERE user_id = ? AND node_id = ? ORDER BY updated_at DESC"
        )
        params = (user_id, node_id)
    else:
        query = "SELECT * FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC"
        params = (user_id,)

    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()

    results = []
    for r in rows:
        d = dict(r)
        try:
            d["history"] = json.loads(d.pop("history_json"))
        except Exception:
            logger.debug("Failed to parse chat session history JSON in list_sessions, using empty list")
            d["history"] = []
        results.append(d)
    return results


@router.get(
    "/sessions/{session_id}",
    summary="Get chat session details (Operator+)",
)
async def get_session(
    session_id: Annotated[str, Path(description="Session UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
) -> dict[str, Any]:
    """Get the details and history of a specific chat session."""
    if is_demo(claims):
        sess = get_demo_chat_session(session_id)
        if sess is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return sess

    user_id = claims["sub"]
    async with db.execute(
        "SELECT * FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, user_id),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    d = dict(row)
    try:
        d["history"] = json.loads(d.pop("history_json"))
    except Exception:
        logger.debug("Failed to parse chat session history JSON in get_session, using empty list")
        d["history"] = []
    return d


@router.post(
    "/sessions",
    summary="Create or update a chat session (Operator+)",
)
async def save_session(
    body: _SessionSaveRequest,
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
) -> dict[str, Any]:
    """Create a new chat session or update an existing one's metadata and/or history."""
    if is_demo(claims):
        sess_id = body.id or str(uuid.uuid4())
        db_node_id = body.node_id
        if db_node_id == "all":
            db_node_id = None
        return save_demo_chat_session(
            session_id=sess_id,
            user_id=claims["sub"],
            node_id=db_node_id,
            title=body.title,
            history=body.history,
        )

    user_id = claims["sub"]
    sess_id = body.id or str(uuid.uuid4())
    node_id = body.node_id
    if node_id == "all":
        node_id = None

    now = time.time()
    history_str = json.dumps(body.history)

    async with db.execute(
        "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
        (sess_id, user_id),
    ) as cursor:
        exists = await cursor.fetchone() is not None

    if exists:
        await db.execute(
            """
            UPDATE chat_sessions SET
                node_id = ?, title = ?, history_json = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (node_id, body.title, history_str, now, sess_id, user_id),
        )
    else:
        await db.execute(
            """
            INSERT INTO chat_sessions (id, user_id, node_id, title, history_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (sess_id, user_id, node_id, body.title, history_str, now, now),
        )
    await db.commit()

    return {
        "id": sess_id,
        "user_id": user_id,
        "node_id": node_id,
        "title": body.title,
        "history": body.history,
        "created_at": now,
        "updated_at": now,
    }


@router.delete(
    "/sessions/{session_id}",
    summary="Delete a chat session (Operator+)",
)
async def delete_session(
    session_id: Annotated[str, Path(description="Session UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
) -> dict[str, Any]:
    """Delete a chat session."""
    if is_demo(claims):
        deleted = delete_demo_chat_session(session_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return {"success": True}

    user_id = claims["sub"]
    async with db.execute(
        "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, user_id),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    await db.execute(
        "DELETE FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, user_id),
    )
    await db.commit()
    return {"success": True}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _build_chat_context(
    nm: NodeManager, db: DB, node_id: str | None, locale: str = "fr"
) -> str:
    """
    Build a system prompt with node context.
    If no node_id is specified, returns a generic sysadmin prompt.
    """
    from master.core.prompts import load_prompt

    lang_instruction = (
        "You must always reply in English."
        if locale == "en"
        else "Tu dois toujours répondre en français."
    )
    if not node_id or node_id == "all":
        return load_prompt("chat_generic", lang_instruction=lang_instruction)

    node = await nm.get_node(db, node_id)
    if node is None:
        return load_prompt("chat_node_not_found", lang_instruction=lang_instruction)

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
            logger.exception("Failed to build status context for node")

    context_lines = "\n".join(f"- {line}" for line in context_parts)
    return load_prompt(
        "chat_with_context",
        lang_instruction=lang_instruction,
        context_lines=context_lines,
    )


_CONTAINER_TARGET_KEYS = ("container_id", "container", "name", "target", "id")
_FUZZY_CONTAINER_THRESHOLD = 0.75
_FUZZY_CONTAINER_AMBIGUITY_MARGIN = 0.08


async def _normalize_action_proposal(
    db: DB,
    nm: NodeManager,
    proposal: ActionProposal,
) -> str | None:
    """
    Normalize safety-sensitive proposal params before storage/execution.

    Returns an operator-facing error string when the target cannot be resolved
    safely. A non-None value means the caller must not execute the intent.
    """
    if proposal.action != "RESTART_CONTAINER":
        return None

    target = _extract_container_target(proposal.params)
    if not target:
        return "RESTART_CONTAINER requires a container target"

    resolved = await _resolve_container_target(db, nm, proposal.node_id, target)
    if resolved.get("status") == "matched":
        value = resolved["container_id"]
        proposal.params = {"container_id": value, "target": value}
        return None
    if resolved.get("status") == "ambiguous":
        candidates = ", ".join(resolved.get("candidates", []))
        return f"Ambiguous container target '{target}'. Candidates: {candidates}"
    return f"Unknown container target '{target}'"


def _extract_container_target(params: dict[str, Any]) -> str:
    """Return the first non-empty container target from common LLM param names."""
    for key in _CONTAINER_TARGET_KEYS:
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


async def _resolve_container_target(
    db: DB,
    nm: NodeManager,
    node_id: str,
    target: str,
) -> dict[str, Any]:
    """Resolve a requested container target against cached containers, then live data."""
    cached_containers = await _get_cached_containers(db, node_id)
    if cached_containers:
        cached_match = _match_container(target, cached_containers)
        if cached_match.get("status") != "not_found":
            return cached_match

    live_containers = await _get_live_containers(nm, node_id)
    if live_containers:
        return _match_container(target, live_containers)

    return {"status": "not_found"}


async def _get_cached_containers(db: DB, node_id: str) -> list[dict[str, Any]]:
    """Read the node container cache. Invalid cache data is treated as empty."""
    async with db.execute(
        "SELECT cached_containers_json FROM nodes WHERE id = ?",
        (node_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None or not row["cached_containers_json"]:
        return []
    try:
        raw = json.loads(row["cached_containers_json"])
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


async def _get_live_containers(nm: NodeManager, node_id: str) -> list[dict[str, Any]]:
    """Fetch live containers from the Worker when cache data cannot resolve a target."""
    try:
        result = await nm.send_intent(node_id, {"action": "LIST_CONTAINERS"}, timeout=10.0)
    except (RuntimeError, TimeoutError):
        return []
    if not result.get("success"):
        return []
    parsed = parse_container_list(result.get("output", ""))
    return parsed or []


def _match_container(target: str, containers: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a single exact/fuzzy container match, or an ambiguity/not-found marker."""
    normalized_target = _normalize_match_text(target)
    if not normalized_target:
        return {"status": "not_found"}

    exact_matches: list[dict[str, Any]] = []
    for container in containers:
        for variant, value in _container_match_variants(container):
            if normalized_target == variant:
                exact_matches.append({"container_id": value, "display": value})
                break
    if len(exact_matches) == 1:
        return {"status": "matched", **exact_matches[0]}
    if len(exact_matches) > 1:
        return {
            "status": "ambiguous",
            "candidates": [match["display"] for match in exact_matches],
        }

    scored: list[tuple[float, str]] = []
    for container in containers:
        best_score = 0.0
        best_value = ""
        for variant, value in _container_match_variants(container):
            score = SequenceMatcher(None, normalized_target, variant).ratio()
            if score > best_score:
                best_score = score
                best_value = value
        if best_value:
            scored.append((best_score, best_value))

    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] < _FUZZY_CONTAINER_THRESHOLD:
        return {"status": "not_found"}

    top_score, top_value = scored[0]
    ambiguous = [
        value
        for score, value in scored[1:]
        if score >= _FUZZY_CONTAINER_THRESHOLD
        and top_score - score <= _FUZZY_CONTAINER_AMBIGUITY_MARGIN
    ]
    if ambiguous:
        return {"status": "ambiguous", "candidates": [top_value, *ambiguous]}

    return {"status": "matched", "container_id": top_value, "display": top_value}


def _container_match_variants(container: dict[str, Any]) -> list[tuple[str, str]]:
    """Build normalized match strings paired with the value to send to Docker."""
    variants: list[tuple[str, str]] = []

    container_id = str(container.get("id") or "").strip()
    name = str(container.get("name") or "").strip().lstrip("/")
    preferred_name = name or container_id

    if name:
        variants.append((_normalize_match_text(name), preferred_name))
        for part in name.replace("_", "-").replace(".", "-").split("-"):
            normalized_part = _normalize_match_text(part)
            if normalized_part:
                variants.append((normalized_part, preferred_name))
    if container_id:
        variants.append((_normalize_match_text(container_id), container_id))

    seen: set[tuple[str, str]] = set()
    unique: list[tuple[str, str]] = []
    for variant in variants:
        if variant[0] and variant not in seen:
            seen.add(variant)
            unique.append(variant)
    return unique


def _normalize_match_text(value: str) -> str:
    """Normalize operator/LLM text for conservative container matching."""
    return value.strip().lower().lstrip("/")


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
    locale: str = "fr",
) -> ActionProposal | None:
    """
    After the AI responds, try to extract an action proposal
    from the conversation context.
    """
    try:
        if locale == "en":
            reasoning_instruction = (
                "The 'reasoning' field MUST be written in English "
                "(all explanations, risks, and details must be in English)."
            )
        else:
            reasoning_instruction = (
                "Le champ 'reasoning' DOIT être rédigé en français "
                "(toutes les explications, risques et détails doivent être en français)."
            )

        req = await sllm.create(
            _ProposalRequest,
            [
                {
                    "role": "system",
                    "content": (
                        "Based on the conversation, determine if a server action is needed. "
                        "If yes, output action, params, reasoning, and risk_level as JSON. "
                        "Set action to 'NONE' if no action is needed. "
                        f"{reasoning_instruction}"
                    ),
                },
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": ai_response},
                {
                    "role": "user",
                    "content": (
                        f"Is a {_list_available_actions()} action needed? " "Reply with JSON only."
                    ),
                },
            ],
            temperature=settings.llm_structured_temperature,
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
        proposal.id,
        proposal.action,
        proposal.node_id,
    )


def _list_available_actions() -> str:
    return (
        "GET_STATS, READ_LOGS, LIST_SERVICES, STATUS_SERVICE, "
        "RESTART_SERVICE, LIST_CONTAINERS, RESTART_CONTAINER"
    )
