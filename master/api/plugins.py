from __future__ import annotations

"""
Vigile — Public Plugins API Router

Endpoints:
  - GET  /api/plugins/pages  → List all pages from active plugins (for SPA)
  - POST /api/plugins/batch  → Read-only batch dispatch of plugin commands (J3a-T16)
"""

import inspect
import logging
from contextlib import AsyncExitStack
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.dependencies.utils import get_dependant, solve_dependencies
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from master.api.deps import DB, get_node_manager, require_role
from master.core import permissions as permissions_module
from master.core.command_registry import CommandEntry, scan_all_routes
from master.core.node_manager import NodeManager
from master.core.plugin_engine import PluginEngine
from master.core.rate_limiter import PluginCallType, require_plugin_budget
from master.core.security_manager import ROLES_HIERARCHY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plugins", tags=["plugins"])

# Fail-closed cap on sub-requests per /batch call (anti-amplification guard).
_BATCH_MAX_SUBREQUESTS = 50


def _get_engine() -> PluginEngine | None:
    """Resolve the active PluginEngine instance."""
    from master.core.plugin_manager import plugin_engine
    return plugin_engine


@router.get("/pages", summary="List all plugin pages")
async def list_plugin_pages(
    claims: dict[str, Any] = Depends(require_role("viewer", "operator", "admin")),
) -> JSONResponse:
    """Return a versioned JSON object containing pages from active plugins.

    The frontend calls this at boot to dynamically register plugin routes
    in the React router and populate the sidebar.
    """
    engine = _get_engine()
    if engine is None or engine.page_registry is None:
        return JSONResponse({"version": 1, "pages": []}, status_code=200)

    pages = engine.page_registry.get_all_pages()

    # Filter by user role
    user_role = claims.get("role", "viewer")
    role_index = {"viewer": 0, "operator": 1, "admin": 2}
    user_level = role_index.get(user_role, 0)

    filtered = []
    for page in pages:
        page_roles = page.get("roles", ["viewer"])
        page_level = min(role_index.get(r, 0) for r in page_roles)
        if user_level >= page_level:
            filtered.append(page)

    return JSONResponse({"version": 1, "pages": filtered}, status_code=200)


# ---------------------------------------------------------------------------
# /batch — read-only batch dispatch (J3a-T16)
#
# Contract: docs/contracts/block-contract-v2.md §5.5 + §6.2 + §8 S7.
# Each sub-request is dispatched by command name through the code-derived
# command registry (master/core/command_registry.py) wrapping the existing
# @route handlers (danger map D1 — no endpoint body rewrites). The wrapper
# re-applies, per sub-request: @route roles (faille 3), node-scope (faille 4),
# and the S5 rate budget (extension point, T19). Mutations are rejected with
# 403 and never executed — they stay on the ActionProposal channel.
# ---------------------------------------------------------------------------


class BatchSubRequest(BaseModel):
    """One command invocation inside a /batch payload."""

    command: str = Field(description="Namespaced command name, e.g. 'docker.list_containers_route'")
    params: dict[str, Any] = Field(default_factory=dict, description="Handler kwargs")


class BatchRequest(BaseModel):
    """Payload of POST /api/plugins/batch.

    ``since`` (optionnel, T26) : paire ``<boot_id>:<counter>`` capturée par le
    client — si la revision courante du moteur est identique, la réponse est
    ``{"unchanged": true}`` sans résultats (réconciliation SSE at-most-once,
    plan §S4) ; sinon la forme historique ``{"results": [...]}`` est renvoyée.
    """

    requests: list[BatchSubRequest] = Field(
        max_length=_BATCH_MAX_SUBREQUESTS,
        description="Read-only command invocations, executed sequentially",
    )
    since: str | None = Field(
        default=None,
        description="S4 reconciliation: `<boot_id>:<counter>` — unchanged revision yields `{unchanged: true}`",
    )


def _build_dispatch_map(engine: Any) -> dict[str, tuple[CommandEntry, Any]]:
    """Map command name → (CommandEntry, bound handler) for the loaded engine.

    The registry scan is code-derived (``scan_all_routes`` over
    ``engine._instances``); the handler is the existing bound ``@route``
    method — the adapter wraps it, it never rewrites it.
    """
    instances = getattr(engine, "_instances", None)
    if not isinstance(instances, dict):
        return {}
    dispatch: dict[str, tuple[CommandEntry, Any]] = {}
    for entry in scan_all_routes(instances):
        instance = instances.get(entry.plugin_id)
        if instance is None:
            continue
        handler = getattr(instance, entry.name.split(".", 1)[1], None)
        if handler is None:
            continue
        dispatch[entry.name] = (entry, handler)
        if entry.name.endswith("_route"):
            alias = entry.name[:-6]
            dispatch.setdefault(alias, (entry, handler))
    return dispatch


def _check_subrequest_roles(claims: dict[str, Any], entry: CommandEntry) -> bool:
    """Re-apply the @route roles metadata per sub-request (faille 3)."""
    user_level = ROLES_HIERARCHY.get(claims.get("role", "viewer"), 0)
    required_level = min(ROLES_HIERARCHY.get(r, 99) for r in entry.roles)
    return user_level >= required_level


def _check_s7_intersection(engine: Any, claims: dict[str, Any], entry: CommandEntry) -> tuple[bool, str]:
    """Apply the S7 permission-intersection gate per sub-request.

    Contract: block-contract-v2.md §6. V1 plugins without V2 permissions
    declarations stay on the flat model (allowed). V2 plugins are
    fail-closed: role >= min_role AND p in manifest.permissions AND
    resource_contract (implemented in master/core/permissions.py).
    """
    manifest = engine.get_v2_manifest(entry.plugin_id) if hasattr(engine, "get_v2_manifest") else None
    perms = getattr(manifest, "permissions", None) if manifest is not None else None
    allowed, reason = permissions_module.check_permission_intersection(
        role=str(claims.get("role", "viewer")),
        command_entry=entry,
        manifest_permissions=perms,
    )
    return allowed, reason


async def _check_node_scope(db: Any, nm: NodeManager, params: dict[str, Any]) -> bool:
    """Re-verify node access per sub-request (faille 4).

    Uses the SAME shared helper as /api/nodes — ``NodeManager.get_node`` —
    never a whole-batch check. Sub-requests without ``node_id`` stay on the
    flat model.
    """
    node_id = params.get("node_id")
    if node_id is None:
        return True
    node = await nm.get_node(db, node_id)
    return node is not None


async def _charge_batch_rates(request: Request, entry: CommandEntry) -> None:
    """Facture la sous-requête contre le budget S5 par plugin (T19).

    La charge s'effectue ici, sur le budget READS du plugin (clé composite
    ``plugin:{plugin_id}:{user_id}:reads`` — jamais un compteur global de
    lot). L'épuisement lève une HTTPException 429, interceptée par
    ``_dispatch_one`` : la sous-requête échoue en échec-faible, le reste du
    lot continue.
    """
    dep = require_plugin_budget(entry.plugin_id, PluginCallType.READS)
    await dep(request)


async def _invoke_plugin_handler(request: Request, handler: Any, params: dict[str, Any]) -> Any:
    """Invoke an existing @route handler with its FastAPI dependencies resolved.

    The handler is called directly (not through the router) with the same
    dependency resolution the mounted route would get: ``params`` are injected
    as query params so required path/query parameters resolve with type
    coercion, and ``Depends`` markers (e.g. ``get_db_conn``,
    ``get_worker_query_port``) are solved by FastAPI's own solver.
    """
    scope = dict(request.scope)
    scope["query_string"] = urlencode(params, doseq=True).encode("utf-8")
    sub_request = Request(scope)
    dependant = get_dependant(path="/batch", call=handler)
    stack = AsyncExitStack()
    try:
        solved = await solve_dependencies(
            request=sub_request,
            dependant=dependant,
            body=None,
            background_tasks=None,
            response=None,
            dependency_overrides_provider=request.app,
            async_exit_stack=stack,
            embed_body_fields=False,
        )
        if solved.errors:
            raise HTTPException(status_code=400, detail=f"invalid parameters: {solved.errors}")
        result = handler(**solved.values)
        if inspect.isawaitable(result):
            result = await result
        return result
    finally:
        await stack.aclose()


async def _dispatch_one(
    request: Request,
    db: Any,
    nm: NodeManager,
    claims: dict[str, Any],
    dispatch: dict[str, tuple[CommandEntry, Any]],
    sub: BatchSubRequest,
) -> dict[str, Any]:
    """Dispatch one sub-request through the fail-closed pipeline."""
    found = dispatch.get(sub.command)
    if found is None:
        return {"command": sub.command, "status": 404, "error": f"unknown command: {sub.command}"}
    entry, handler = found
    _engine = _get_engine()
    if _engine is not None and hasattr(_engine, "is_kill_switched") and _engine.is_kill_switched(entry.plugin_id):
        return {
            "command": sub.command,
            "status": 403,
            "error": f"plugin '{entry.plugin_id}' is disabled via kill switch",
        }
    if entry.mutation:
        return {
            "command": sub.command,
            "status": 403,
            "error": "mutation commands are not allowed via /batch",
        }
    if not _check_subrequest_roles(claims, entry):
        return {
            "command": sub.command,
            "status": 403,
            "error": f"insufficient role for command: {sub.command}",
        }
    allowed, reason = _check_s7_intersection(_get_engine(), claims, entry)
    if not allowed:
        return {
            "command": sub.command,
            "status": 403,
            "error": f"permission denied for command: {sub.command} ({reason})",
        }
    if not await _check_node_scope(db, nm, sub.params):
        return {
            "command": sub.command,
            "status": 403,
            "error": f"node access denied for command: {sub.command}",
        }
    try:
        await _charge_batch_rates(request, entry)
    except HTTPException as exc:
        return {
            "command": sub.command,
            "status": exc.status_code,
            "error": str(exc.detail),
        }
    try:
        data = await _invoke_plugin_handler(request, handler, sub.params)
    except HTTPException as exc:
        return {"command": sub.command, "status": exc.status_code, "error": str(exc.detail)}
    except Exception as exc:
        logger.exception("batch sub-request '%s' handler failed", sub.command)
        return {"command": sub.command, "status": 500, "error": f"handler error: {exc}"}
    return {"command": sub.command, "status": 200, "data": data}


def _since_matches(engine: Any, since: str) -> bool:
    """Compare ``<boot_id>:<counter>`` à la revision courante du moteur (S4).

    Un ``since`` malformé ne matche jamais (repli sur la réponse complète) —
    jamais de faux ``unchanged`` : la réconciliation doit rester sûre.
    """
    if engine is None or not hasattr(engine, "revision"):
        return False
    try:
        boot_id, counter = since.rsplit(":", 1)
        revision = engine.revision
        return revision.boot_id == boot_id and revision.counter == int(counter)
    except (ValueError, TypeError):
        return False


@router.post("/batch", summary="Execute read-only plugin commands in batch")
async def batch_execute(
    payload: BatchRequest,
    request: Request,
    db: DB,
    claims: dict[str, Any] = Depends(require_role("viewer", "operator", "admin")),
    nm: NodeManager = Depends(get_node_manager),
) -> JSONResponse:
    """Dispatch a batch of read-only plugin commands.

    Each sub-request is independently checked (mutation → 403, unknown
    command → 404, @route roles, node-scope) and executed against the
    existing plugin route handlers. Mutations are never executed here.

    T26 — réconciliation ``since`` : si la revision courante du moteur est
    identique à la paire envoyée, réponse ``{"unchanged": true}`` SANS les
    résultats (le client garde son cache) ; sinon la forme historique
    ``{"results": [...]}`` inchangée.
    """
    engine = _get_engine()
    if payload.since is not None and _since_matches(engine, payload.since):
        return JSONResponse({"unchanged": True}, status_code=200)

    dispatch = _build_dispatch_map(engine)
    results = [
        await _dispatch_one(request, db, nm, claims, dispatch, sub)
        for sub in payload.requests
    ]
    # La paire `revision` accompagne la réponse complète : le client la
    # capture pour ses prochains appels `since` (réconciliation S4). Absente
    # quand le moteur n'expose pas de revision (forme historique inchangée).
    if engine is not None and hasattr(engine, "revision"):
        rev = engine.revision
        return JSONResponse(
            {"results": results, "revision": {"boot_id": rev.boot_id, "counter": rev.counter}},
            status_code=200,
        )
    return JSONResponse({"results": results}, status_code=200)


class PluginDisableRequest(BaseModel):
    hard: bool = Field(default=False, description="Hard mode: immediate tombstone, no drain")
    reason: str | None = Field(default=None, description="Admin justification (required for hard mode)")


@router.post("/{plugin_id}/disable", summary="Disable a plugin via kill switch (S6)")
async def disable_plugin(
    plugin_id: str,
    payload: PluginDisableRequest,
    db: DB,
    claims: dict[str, Any] = Depends(require_role("admin")),
        engine: PluginEngine | None = Depends(_get_engine),
) -> JSONResponse:
    if engine is None:
        raise HTTPException(status_code=503, detail="Plugin engine not available")

    user_id = str(claims.get("sub", "unknown"))
    hard = payload.hard
    if hard and not payload.reason:
        raise HTTPException(
            status_code=422,
            detail="reason is required when hard=true (kill switch hard mode must be justified)",
        )

    await engine.disable_plugin(
        plugin_id,
        hard=hard,
        reason=payload.reason or "",
        user_id=user_id,
    )
    mode = "hard" if hard else "maintenance"
    return JSONResponse(
        {"status": "disabled", "mode": mode},
        status_code=200,
    )


@router.post("/{plugin_id}/enable", summary="Re-enable a kill-switched plugin (S6)")
async def enable_plugin(
    plugin_id: str,
    db: DB,
    claims: dict[str, Any] = Depends(require_role("admin")),
    engine: PluginEngine | None = Depends(_get_engine),
) -> JSONResponse:
    if engine is None:
        raise HTTPException(status_code=503, detail="Plugin engine not available")

    if not engine.is_kill_switched(plugin_id):
        raise HTTPException(status_code=404, detail=f"plugin '{plugin_id}' is not kill-switched")

    await engine.enable_plugin(plugin_id)
    return JSONResponse({"status": "enabled"}, status_code=200)
