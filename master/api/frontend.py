"""
Vigile — Frontend Routes (SSR + HTMX)

Serves the Vigile dashboard UI using Jinja2 templates.
All routes validate JWT from httpOnly cookie.
Fragment endpoints return HTML for HTMX polling.
"""

import json
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from master.config import settings
from master.core.audit import log_action
from master.core.node_manager import NodeManager, node_manager
from master.core.plugin_manager import plugin_manager
from master.core.security_manager import SecurityManager, get_security_instance
from master.plugins.systemd_plugin import parse_service_list
from master.plugins.docker_plugin import parse_container_list

logger = logging.getLogger(__name__)

router = APIRouter(tags=["frontend"])


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _sec() -> SecurityManager:
    return get_security_instance()


def _nm() -> NodeManager:
    return node_manager


async def _get_user(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        return _sec().verify_access_token(token)
    except Exception:
        return None


async def _get_db():
    from master.db.database import get_db_conn
    return get_db_conn()


# ---------------------------------------------------------------------------
# Intent helper (reused by fragment routes)
# ---------------------------------------------------------------------------

async def _send_intent(node_id: str, action: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        return await _nm().send_intent(
            node_id, {"action": action, "params": params}, timeout=15.0
        )
    except (RuntimeError, TimeoutError) as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# 429 exception handler (returns HTML for HTMX fragment requests)
# ---------------------------------------------------------------------------


async def _frontend_429_handler(request: Request, exc: HTTPException) -> HTMLResponse:
    if exc.status_code != 429:
        raise
    retry_after = 60
    if exc.headers and "Retry-After" in exc.headers:
        retry_after = int(exc.headers["Retry-After"])
    else:
        import re
        match = re.search(r"(\d+)s?", exc.detail)
        if match:
            retry_after = int(match.group(1))
    html = (
        '<div class="toast amber" style="margin:0.75rem 1.4rem;display:flex;align-items:center;gap:0.65rem;'
        'padding:0.65rem 1rem;border:1.5px solid var(--amber-border);background:var(--amber-soft);'
        'font-size:0.85rem;font-weight:500;color:var(--ink);">'
        '<span style="width:7px;height:7px;border-radius:50%;background:var(--amber);flex-shrink:0;"></span>'
        f'Trop de requêtes. Réessayez dans {retry_after}s'
        '</div>'
    )
    return HTMLResponse(
        status_code=429,
        content=html,
        headers={"Retry-After": str(retry_after)},
    )


# ---------------------------------------------------------------------------
# Auth pages
# ---------------------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = await _get_user(request)
    if user:
        return RedirectResponse(url="/", status_code=302)
    return request.app.state.templates.TemplateResponse(
        "login.html", {"request": request, "error": None}
    )


@router.post("/login")
async def login_action(request: Request):
    templates = request.app.state.templates
    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))

    if not username or not password:
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Missing username or password"},
            status_code=400,
        )

    db = await _get_db()
    sec = _sec()

    async with db.execute(
        "SELECT id, username, password_hash, role, is_active FROM users WHERE username = ?",
        (username,),
    ) as cursor:
        user = await cursor.fetchone()

    if user is None or not sec.verify_password(password, user["password_hash"]):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Invalid credentials"},
            status_code=401,
        )

    if not user["is_active"]:
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Account deactivated"},
            status_code=403,
        )

    access_token = sec.create_access_token(
        user_id=user["id"], username=user["username"], role=user["role"],
    )
    await db.execute(
        "UPDATE users SET last_login = ? WHERE id = ?", (time.time(), user["id"]),
    )
    await db.commit()

    logger.info("Frontend login: user='%s' role=%s", user["username"], user["role"])

    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=settings.jwt_access_token_ttl,
        path="/",
    )
    # Also set a non-httpOnly cookie so client-side JS can read the JWT
    # for Bearer auth on REST API calls (approve/reject proposals).
    response.set_cookie(
        key="auth_token",
        value=access_token,
        httponly=False,
        secure=False,
        samesite="lax",
        max_age=settings.jwt_access_token_ttl,
        path="/",
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="auth_token", path="/")
    return response


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = await _get_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    db = await _get_db()
    nm = _nm()

    async with db.execute(
        "SELECT id, name, hostname, machine_id, arch, os, state, "
        "last_heartbeat, enrolled_at, created_at, updated_at "
        "FROM nodes ORDER BY created_at DESC"
    ) as cursor:
        nodes = [dict(r) for r in await cursor.fetchall()]

    metrics_by_node: dict[str, dict] = {}
    for node in nodes:
        async with db.execute(
            "SELECT cpu_percent, mem_percent, disk_percent, uptime_seconds, "
            "cpu_load_1m, cpu_load_5m, cpu_load_15m, "
            "mem_total_bytes, mem_used_bytes, "
            "disk_total_bytes, disk_used_bytes, "
            "processes, collected_at "
            "FROM metrics_snapshots WHERE node_id = ? "
            "ORDER BY collected_at DESC LIMIT 1",
            (node["id"],),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                metrics_by_node[node["id"]] = dict(row)

    connected_ids = set(nm.connected_node_ids())
    for node in nodes:
        node["online"] = node["id"] in connected_ids
        node["metrics"] = metrics_by_node.get(node["id"])

    # Separate online/offline
    online_nodes = [n for n in nodes if n["online"]]
    offline_nodes = [n for n in nodes if not n["online"]]

    return request.app.state.templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "nodes": nodes,
        "online_nodes": online_nodes,
        "offline_nodes": offline_nodes,
        "connected_count": len(connected_ids),
        "total_count": len(nodes),
    })


# ---------------------------------------------------------------------------
# Node detail
# ---------------------------------------------------------------------------


@router.get("/nodes/{node_id}", response_class=HTMLResponse)
async def node_detail(request: Request, node_id: str):
    user = await _get_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    db = await _get_db()
    nm = _nm()

    async with db.execute(
        "SELECT id, name, hostname, machine_id, arch, os, state, public_key, "
        "last_heartbeat, enrolled_at, created_at, updated_at "
        "FROM nodes WHERE id = ?", (node_id,),
    ) as cursor:
        node = await cursor.fetchone()

    if node is None:
        return HTMLResponse(
            "<div class='glass p-12 text-center'><p style='color: var(--ink-muted);'>Node not found.</p></div>",
            status_code=404,
        )

    node = dict(node)
    node["online"] = nm.is_connected(node_id)

    # Latest metrics
    async with db.execute(
        "SELECT * FROM metrics_snapshots WHERE node_id = ? "
        "ORDER BY collected_at DESC LIMIT 1", (node_id,),
    ) as cursor:
        metrics_row = await cursor.fetchone()
    metrics = dict(metrics_row) if metrics_row else None

    # Metrics history (last 20 for sparklines)
    async with db.execute(
        "SELECT collected_at, cpu_percent, mem_percent, disk_percent "
        "FROM metrics_snapshots WHERE node_id = ? "
        "ORDER BY collected_at DESC LIMIT 20", (node_id,),
    ) as cursor:
        history = [dict(r) for r in await cursor.fetchall()]
    history.reverse()

    # Stats snapshots count
    async with db.execute(
        "SELECT COUNT(*) as cnt FROM metrics_snapshots WHERE node_id = ?", (node_id,),
    ) as cursor:
        row = await cursor.fetchone()
        snapshots_count = row["cnt"] if row else 0

    return request.app.state.templates.TemplateResponse("node.html", {
        "request": request,
        "user": user,
        "node": node,
        "metrics": metrics,
        "history": history,
        "snapshots_count": snapshots_count,
        "page": request.query_params.get("tab", "metrics"),
    })


# ---------------------------------------------------------------------------
# HTMX fragments
# ---------------------------------------------------------------------------


@router.get("/nodes/{node_id}/fragments/metrics", response_class=HTMLResponse)
async def node_metrics_fragment(request: Request, node_id: str):
    user = await _get_user(request)
    if not user:
        return HTMLResponse(
            '<div class="p-8 text-center"><p style="color:var(--ink-dim);">Session expired. <a href="/login">Login again</a></p></div>',
            headers={"HX-Redirect": "/login?reason=expired"},
        )

    db = await _get_db()

    async with db.execute(
        "SELECT * FROM metrics_snapshots WHERE node_id = ? "
        "ORDER BY collected_at DESC LIMIT 1", (node_id,),
    ) as cursor:
        row = await cursor.fetchone()
    metrics = dict(row) if row else None

    return request.app.state.templates.TemplateResponse(
        "_metrics.html", {"request": request, "metrics": metrics, "node_id": node_id},
    )


@router.get("/nodes/{node_id}/fragments/services", response_class=HTMLResponse)
async def node_services_fragment(request: Request, node_id: str):
    user = await _get_user(request)
    if not user:
        return HTMLResponse(
            '<div class="p-8 text-center"><p style="color:var(--ink-dim);">Session expired. <a href="/login">Login again</a></p></div>',
            headers={"HX-Redirect": "/login?reason=expired"},
        )

    result = await _send_intent(node_id, "LIST_SERVICES", {})
    services: list[dict[str, str]] = []
    error = None
    if result.get("success"):
        parsed = parse_service_list(result.get("output", ""))
        if parsed is not None:
            services = parsed
        else:
            error = "Unparseable service list"
    else:
        error = result.get("error", "Worker not available")

    return request.app.state.templates.TemplateResponse(
        "_services.html", {
            "request": request, "node_id": node_id,
            "services": services, "error": error,
        },
    )


@router.get("/nodes/{node_id}/fragments/containers", response_class=HTMLResponse)
async def node_containers_fragment(request: Request, node_id: str):
    user = await _get_user(request)
    if not user:
        return HTMLResponse(
            '<div class="p-8 text-center"><p style="color:var(--ink-dim);">Session expired. <a href="/login">Login again</a></p></div>',
            headers={"HX-Redirect": "/login?reason=expired"},
        )

    result = await _send_intent(node_id, "LIST_CONTAINERS", {})
    containers: list[dict[str, Any]] = []
    error = None
    if result.get("success"):
        parsed = parse_container_list(result.get("output", ""))
        if parsed is not None:
            containers = parsed
        else:
            error = "Unparseable container list"
    else:
        error = result.get("error", "Worker not available")

    return request.app.state.templates.TemplateResponse(
        "_containers.html", {
            "request": request, "node_id": node_id,
            "containers": containers, "error": error,
        },
    )


@router.get("/nodes/{node_id}/fragments/logs", response_class=HTMLResponse)
async def node_logs_fragment(request: Request, node_id: str):
    user = await _get_user(request)
    if not user:
        return HTMLResponse(
            '<div class="p-8 text-center"><p style="color:var(--ink-dim);">Session expired. <a href="/login">Login again</a></p></div>',
            headers={"HX-Redirect": "/login?reason=expired"},
        )

    # Try to read logs from worker
    result = await _send_intent(node_id, "READ_LOGS", {"path": "/var/log/syslog"})
    log_lines: list[str] = []
    error = None
    if result.get("success"):
        output = result.get("output", "")
        log_lines = output.split("\n") if output else []
    else:
        error = result.get("error", "Worker not available")

    return request.app.state.templates.TemplateResponse(
        "_logs.html", {
            "request": request, "node_id": node_id,
            "log_lines": log_lines, "error": error,
        },
    )


# ---------------------------------------------------------------------------
# Proposals page
# ---------------------------------------------------------------------------


@router.get("/proposals", response_class=HTMLResponse)
async def proposals_page(request: Request):
    user = await _get_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    db = await _get_db()

    status_filter = request.query_params.get("status")
    if status_filter:
        async with db.execute(
            "SELECT * FROM action_proposals WHERE status = ? ORDER BY created_at DESC",
            (status_filter,),
        ) as cursor:
            proposals = [dict(r) for r in await cursor.fetchall()]
    else:
        async with db.execute(
            "SELECT * FROM action_proposals ORDER BY created_at DESC",
        ) as cursor:
            proposals = [dict(r) for r in await cursor.fetchall()]

    return request.app.state.templates.TemplateResponse("proposals.html", {
        "request": request, "user": user,
        "proposals": proposals, "status_filter": status_filter or "all",
    })


# ---------------------------------------------------------------------------
# Audit page
# ---------------------------------------------------------------------------


@router.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request):
    user = await _get_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    db = await _get_db()
    limit = min(int(request.query_params.get("limit", 100)), 500)

    async with db.execute(
        "SELECT * FROM audit_log ORDER BY sequence DESC LIMIT ?", (limit,),
    ) as cursor:
        entries = [dict(r) for r in await cursor.fetchall()]

    return request.app.state.templates.TemplateResponse("audit.html", {
        "request": request, "user": user,
        "entries": entries, "limit": limit,
    })


# ---------------------------------------------------------------------------
# Plugins page
# ---------------------------------------------------------------------------


@router.get("/plugins", response_class=HTMLResponse)
async def plugins_page(request: Request):
    user = await _get_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    loaded = plugin_manager.loaded_plugins
    hooks = plugin_manager.get_hooks()

    return request.app.state.templates.TemplateResponse("plugins.html", {
        "request": request, "user": user,
        "loaded_plugins": loaded,
        "hooks": hooks,
    })


# ---------------------------------------------------------------------------
# Chat stream (cookie-based auth version)
# ---------------------------------------------------------------------------


@router.post("/chat/stream")
async def chat_stream(request: Request):
    user = await _get_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    body_bytes = await request.body()
    body = json.loads(body_bytes) if body_bytes else {}
    message = body.get("message", "")
    node_id = body.get("node_id")
    history = body.get("history", [])

    if not message:
        return HTMLResponse("message is required", status_code=400)

    db = await _get_db()
    nm = _nm()

    from master.api.chat import _build_chat_context, _try_extract_proposal, _persist_proposal
    from master.core.llm_client import LLMClient
    from master.core.structured_llm import StructuredLLM
    from master.api.deps import get_llm_client, get_structured_llm

    llm = get_llm_client()
    sllm = get_structured_llm()

    system_prompt = await _build_chat_context(nm, db, node_id)

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    async def _event_stream():
        token_buffer = ""
        try:
            async for event in llm.stream(messages, temperature=0.3):
                if event["type"] == "token":
                    token_buffer += event["content"]
                    yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
                elif event["type"] == "error":
                    yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
                    yield f"data: {json.dumps({'type': 'done'}, separators=(',', ':'))}\n\n"
                    return
                elif event["type"] == "done":
                    pass

            # Proposal extraction
            if node_id:
                proposal = await _try_extract_proposal(
                    sllm, node_id, message, token_buffer, user["sub"]
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
