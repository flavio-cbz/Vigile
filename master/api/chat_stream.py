"""
Vigile — Chat API: streaming chat + suggestions endpoints
"""

from __future__ import annotations

import json
import logging
import time
try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated  # type: ignore[attr-defined]
from typing import Any

from fastapi import Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from master.api.chat_helpers import (
    _build_chat_context,
    _cap_history,
    _list_available_actions,
    _normalize_action_proposal,
    _persist_proposal,
    _sanitize_message,
    _validate_log_path,
)
from master.api.chat_router import router
from master.api.demo_data import (
    get_demo_chat_tokens,
    get_demo_proposal_from_text,
    is_demo,
    save_demo_chat_session,
)
from master.api.deps import (
    DB,
    get_llm_client,
    get_node_manager,
    get_settings,
    get_structured_llm,
    get_worker_query_port,
    require_role,
)
from master.core.action_proposal import ActionProposal
from master.core.llm_client import LLMClient, LLMError
from master.core.node_manager import NodeManager
from master.core.plugin_base import redact_sensitive
from master.core.structured_llm import StructuredLLM
from master.core.worker_query_port import WorkerQueryPort

logger = logging.getLogger(__name__)


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
    port: WorkerQueryPort = Depends(get_worker_query_port),
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
    message = _sanitize_message(body.get("message", ""))
    node_id = body.get("node_id")
    history = _cap_history(body.get("history", []))
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
        from master.core.alert_engine import alert_engine

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
        seen_tool_fingerprints: set[str] = set()

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

                    # ReAct dedup: skip tool calls that were already executed in a previous step
                    tool_fingerprint = f"{fn_name}:{fn_args_str}"
                    if tool_fingerprint in seen_tool_fingerprints:
                        logger.warning("Skipping duplicate tool call: %s", tool_fingerprint)
                        yield f"data: {json.dumps({'type': 'tool_skipped', 'tool': fn_name, 'reason': 'duplicate'}, separators=(',', ':'))}\n\n"
                        current_messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": fn_name,
                            "content": json.dumps({"success": False, "error": "This action was already performed in a previous step."})
                        })
                        continue
                    seen_tool_fingerprints.add(tool_fingerprint)

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
                            # Path validation: reject paths outside the allowed whitelist
                            requested_path = fn_args["file"]
                            if not _validate_log_path(requested_path):
                                logger.warning("Blocked read_logs path not in allowlist: %s", requested_path)
                                tool_output = json.dumps({
                                    "success": False,
                                    "error": f"Access denied: log file '{requested_path}' is not in the allowed list."
                                })
                                tool_success = False
                                tool_duration_ms = int((time.monotonic() - tool_start_ts) * 1000)
                                yield f"data: {json.dumps({'type': 'tool_result', 'tool': fn_name, 'node_id': node_id, 'duration_ms': tool_duration_ms, 'success': tool_success}, separators=(',', ':'))}\n\n"
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
                                continue
                            params["file"] = requested_path
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
                            result = await port.query(node_id, action, params, timeout=15.0)
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

        except LLMError as exc:
            logger.exception("Chat LLM error")
            safe_detail = redact_sensitive(str(exc))
            yield f"data: {json.dumps({'type': 'error', 'detail': safe_detail}, separators=(',', ':'))}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, separators=(',', ':'))}\n\n"
        except Exception:
            logger.exception("Chat streaming error")
            yield f"data: {json.dumps({'type': 'error', 'detail': 'An unexpected error occurred. Please try again.'}, separators=(',', ':'))}\n\n"
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
# GET /api/chat/suggestions — Context-aware prompt suggestions
# ---------------------------------------------------------------------------


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
# Proposal extraction helpers (legacy / ReAct-retrofit)
# ---------------------------------------------------------------------------


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
            temperature=0.3,
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



