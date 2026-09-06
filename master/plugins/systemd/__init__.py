"""
Vigile — Systemd Plugin (Folder Format)

Registers systemd-related actions supported by the Worker:
  - LIST_SERVICES
  - STATUS_SERVICE
  - RESTART_SERVICE

The Worker Go binary handles the actual systemd interaction.
This plugin exists to declare supported actions and provide
response model validation for the Master API.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from fastapi import Body, Depends, HTTPException
from master.core.plugin_base import PluginBase, PluginContext, hook, route
from master.api.deps import (
    get_db,
    get_node_manager,
    get_proposal_dispatcher,
    get_worker_query_port,
    require_role,
)
from master.core.audit import AuditAction, log_action
from master.core.plugin_utils import parse_worker_list, parse_worker_object
from master.core.single_flight import SingleFlight

logger = logging.getLogger(__name__)

_systemd_single_flight = SingleFlight()

PROTECTED_SERVICES = frozenset({
    "ssh",
    "sshd",
    "docker",
    "dockerd",
    "containerd",
    "networking",
    "systemd-networkd",
    "networkmanager",
    "systemd-resolved",
    "systemd-journald",
    "systemd-logind",
    "dbus",
    "vigile",
    "vigile-worker",
})


_UNIT_EXTENSIONS = (".service", ".socket", ".target", ".timer", ".slice")


def canonical_service_name(service: str) -> str:
    clean = service.strip().lower()
    for ext in _UNIT_EXTENSIONS:
        if clean.endswith(ext):
            clean = clean[:-len(ext)]
            break
    return clean


def is_protected_service(service: str) -> bool:
    return canonical_service_name(service) in PROTECTED_SERVICES


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ServiceInfo(BaseModel):
    name: str = Field(description="Systemd unit name (e.g. ssh.service)")
    state: str = Field(description="Active state (active, inactive, etc.)")
    status: str = Field(description="Sub-status (running, exited, dead, etc.)")


class ServiceStatus(BaseModel):
    service: str = Field(description="Service name")
    active: str = Field(description="Active state")
    enabled: str = Field(description="Whether service is enabled")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def parse_service_list(output: str) -> list[dict[str, str]] | None:
    """Parse the JSON array returned by the Worker for LIST_SERVICES."""
    return parse_worker_list(output, ServiceInfo)


def parse_service_status(output: str) -> dict[str, str] | None:
    """Parse the JSON object returned by the Worker for STATUS_SERVICE."""
    return parse_worker_object(output, ServiceStatus)


# ---------------------------------------------------------------------------
# Service lifecycle actions (mutation → ActionProposal channel)
# ---------------------------------------------------------------------------

# Actions proposées par l'UI (SystemdServices.tsx) — le clic de l'opérateur
# sur la page EST l'approbation : la proposition est créée directement
# APPROVED, puis dispatchée via ApprovedProposalDispatcher.
_SERVICE_ACTIONS = frozenset({"stop", "start", "restart"})

_ACTION_TO_INTENT: dict[str, str] = {
    "restart": "RESTART_SERVICE",
    "start": "START_SERVICE",
    "stop": "STOP_SERVICE",
}

_ACTION_RISK_LEVEL: dict[str, str] = {
    "start": "LOW",
    "restart": "MEDIUM",
    "stop": "HIGH",
}


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


class SystemdPlugin(PluginBase):
    """Systemd Service Manager plugin using the class-based PluginBase API."""

    plugin_id = "systemd"

    # Copilot actions supported by this plugin
    copilot_actions: list[dict[str, Any]] = [
        {"action": "LIST_SERVICES", "risk_level": "LOW"},
        {"action": "STATUS_SERVICE", "risk_level": "LOW"},
        {"action": "RESTART_SERVICE", "risk_level": "LOW"},
        {"action": "START_SERVICE", "risk_level": "LOW"},
        {"action": "STOP_SERVICE", "risk_level": "HIGH"},
    ]

    def __init__(self, ctx: PluginContext) -> None:
        super().__init__(ctx)

    @hook("get_supported_actions")
    def _get_supported_actions(self) -> list[str]:
        """Return the list of systemd actions supported by the Worker."""
        return [
            "LIST_SERVICES",
            "STATUS_SERVICE",
            "RESTART_SERVICE",
            "START_SERVICE",
            "STOP_SERVICE",
        ]

    @route("/services", method="GET", roles=["admin", "operator"])
    async def list_services_route(
        self,
        node_id: str | None = None,
        force_refresh: bool = False,
        nm: Any = Depends(get_node_manager),
        port: Any = Depends(get_worker_query_port),
        db: Any = Depends(get_db),
    ) -> dict:
        """Fetch systemd services list — cache-first (B4).

        Contract: {services, count, cached_at, stale, errors[]}, TTL 300s.
        - Cache hit (fresh or stale) → serve DB only, no Worker I/O.
        - Cold start (no cache) → live fallback once with timeout 10s.
        - force_refresh=true → live query with timeout 15s (master > worker 10s).
        - set_cached_services only on success:true && parsed!=None.
        """
        import time as _time

        from master.db.service_cache import (
            get_cached_services,
            is_stale,
            set_cached_services,
        )

        # Resolve target nodes
        if node_id:
            nodes = [node_id]
        else:
            nodes = [node.id for node in nm.get_connected_nodes()]
            if not nodes:
                # No connected nodes — still try to serve cached nodes from DB
                # Batch query: single SELECT avoids N+1 get_cached_services
                try:
                    async with db.execute(
                        "SELECT id FROM nodes WHERE cached_services_json IS NOT NULL"
                    ) as cur:
                        rows = await cur.fetchall()
                        if rows:
                            nodes = [r["id"] for r in rows]
                except Exception as exc:
                    logger.warning("systemd: cached-node DB listing failed: %s", exc)

        # Phase 1: load all caches (sequential DB reads — cheap, <1ms each)
        # Collect per-node cache state to decide live refresh
        import asyncio as _asyncio

        per_node: dict[str, dict[str, Any]] = {}
        services: list[dict[str, Any]] = []
        errors: list[str] = []
        cached_ats: list[float] = []
        any_stale = False

        for nid in nodes:
            cached_json, cached_at = await get_cached_services(db, nid)
            stale = is_stale(cached_at)
            if cached_at is not None:
                cached_ats.append(cached_at)

            cached_services: list[dict[str, Any]] = []
            if cached_json is not None:
                try:
                    raw = json.loads(cached_json)
                    for srv in raw if isinstance(raw, list) else []:
                        if isinstance(srv, dict) and "name" in srv:
                            entry = {
                                "node_id": srv.get("node_id", nid),
                                "name": srv["name"],
                                "state": srv.get("state", ""),
                                "status": srv.get("status", ""),
                            }
                            cached_services.append(entry)
                    if stale:
                        any_stale = True
                except Exception as exc:
                    logger.warning(
                        "systemd: cache JSON invalide pour node %s: %s", nid, exc
                    )
                    cached_services = []
                    stale = True
                    any_stale = True
            else:
                stale = True
                any_stale = True

            should_live = False
            live_timeout = 15.0
            if force_refresh:
                should_live = True
                live_timeout = 15.0
            elif cached_json is None:
                should_live = True
                live_timeout = 12.0

            per_node[nid] = {
                "cached_json": cached_json,
                "cached_at": cached_at,
                "cached_services": cached_services,
                "stale": stale,
                "should_live": should_live,
                "live_timeout": live_timeout,
            }

        # Phase 2: parallel live refresh for nodes needing it (Single-Flight + Semaphore 5 thundering herd guard)
        live_nids = [nid for nid, st in per_node.items() if st["should_live"]]
        if live_nids:
            sem = _asyncio.Semaphore(5)

            async def _fetch_one(nid: str) -> tuple[str, list[dict[str, Any]] | None, str | None]:
                st = per_node[nid]

                async def _do_query() -> tuple[list[dict[str, Any]] | None, str | None]:
                    async with sem:
                        try:
                            result = await port.query(nid, "LIST_SERVICES", timeout=st["live_timeout"])
                            if result.get("success"):
                                parsed = parse_service_list(result.get("output", ""))
                                if parsed is not None:
                                    enriched = [
                                        {
                                            "node_id": nid,
                                            "name": p["name"],
                                            "state": p["state"],
                                            "status": p["status"],
                                        }
                                        for p in parsed
                                    ]
                                    try:
                                        await set_cached_services(db, nid, json.dumps(enriched), _time.time())
                                    except Exception as e:
                                        logger.warning("Failed to cache services for node %s: %s", nid, e)
                                    return enriched, None
                                return None, f"{nid}: unparseable service list"
                            err = result.get("error") or "worker returned success=false"
                            return None, f"{nid}: {err}"
                        except Exception as e:
                            logger.warning("Failed to fetch services for node %s: %s", nid, e)
                            return None, f"{nid}: {e}"

                enriched, err = await _systemd_single_flight.run(nid, _do_query)
                return nid, enriched, err

            results = await _asyncio.gather(*[_fetch_one(nid) for nid in live_nids])

            for nid, enriched, err in results:
                st = per_node[nid]
                if enriched is not None:
                    st["cached_services"] = enriched
                    st["cached_at"] = _time.time()
                    st["stale"] = False
                    cached_ats.append(st["cached_at"])  # type: ignore[arg-type]
                elif err is not None:
                    errors.append(err)
                    st["stale"] = True
                    any_stale = True

        # Phase 3: aggregate
        for nid in nodes:
            st = per_node[nid]
            services.extend(st["cached_services"])
            if st["stale"]:
                any_stale = True

        overall_cached_at = max(cached_ats) if cached_ats else None
        overall_stale = any_stale or overall_cached_at is None
        if len(services) > 500:
            services = services[:500]

        return {
            "services": services,
            "count": len(services),
            "cached_at": overall_cached_at,
            "stale": overall_stale,
            "errors": errors,
        }

    @route("/services/{service_name}/{action}", method="POST", roles=["admin", "operator"])
    async def service_action_route(
        self,
        service_name: str,
        action: str,
        body: dict[str, Any] | None = Body(default=None),
        claims: dict[str, Any] = Depends(require_role("admin", "operator")),
        db: Any = Depends(get_db),
        dispatcher: Any = Depends(get_proposal_dispatcher),
    ) -> dict:
        """Déclenche une action de cycle de vie sur un service systemd.

        Mutation obligatoire : la proposition est créée APPROVED (le clic de
        l'opérateur sur la page vaut approbation — zéro changement UX) puis
        dispatchée via ApprovedProposalDispatcher — jamais
        NodeManager.send_intent() (déprécié).
        """
        if action not in _SERVICE_ACTIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Action '{action}' invalide : attendu 'stop', 'start' ou 'restart'.",
            )
        node_id = (body or {}).get("node_id")
        if not node_id:
            raise HTTPException(
                status_code=400,
                detail="Champ 'node_id' manquant dans le corps de la requête.",
            )

        # Contrôle de rôle strict (B4) : stop réservé aux administrateurs
        user_role = claims.get("role")
        if action == "stop" and user_role != "admin":
            if db is not None:
                await log_action(
                    db,
                    user_id=claims.get("sub", "unknown"),
                    action=AuditAction.SECURITY_INCIDENT,
                    node_id=node_id,
                    details={
                        "reason": "unauthorized_role_attempt",
                        "required_role": "admin",
                        "user_role": user_role,
                        "action": action,
                        "service": service_name,
                    },
                )
            raise HTTPException(
                status_code=403,
                detail=f"L'action '{action}' est strictement réservée aux administrateurs.",
            )

        # Protection Master contre l'arrêt de services critiques (B1, B4)
        if action == "stop" and is_protected_service(service_name):
            if db is not None:
                await log_action(
                    db,
                    user_id=claims.get("sub", "unknown"),
                    action=AuditAction.SECURITY_INCIDENT,
                    node_id=node_id,
                    details={
                        "reason": "attempt_to_stop_protected_service",
                        "service": service_name,
                        "action": action,
                    },
                )
            raise HTTPException(
                status_code=403,
                detail=f"Le service '{service_name}' est protégé et ne peut pas être arrêté.",
            )

        intent = _ACTION_TO_INTENT.get(action)
        if intent is None:
            raise HTTPException(
                status_code=400,
                detail=f"L'action '{action}' n'est pas supportée.",
            )

        risk_level = _ACTION_RISK_LEVEL.get(action, "MEDIUM")

        try:
            result = await dispatcher.dispatch_admin_action(
                node_id,
                intent,
                {"service": service_name},
                claims.get("sub", "unknown"),
                db,
                intent_timeout=15.0,
                reasoning=f"Action {action} sur le service {service_name} (page Services)",
                risk_level=risk_level,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Le Worker n'a pas répondu dans le délai imparti.",
            )
        if result.get("success"):
            from master.db.service_cache import invalidate_cached_services

            try:
                if db is not None:
                    await invalidate_cached_services(db, node_id)
            except Exception as exc:
                logger.warning("Failed to invalidate service cache for node %s: %s", node_id, exc)

            if db is not None:
                action_enum_name = f"{action.upper()}_SERVICE"
                audit_action = getattr(AuditAction, action_enum_name, AuditAction.INTENT_DISPATCH)
                await log_action(
                    db,
                    user_id=claims.get("sub", "system"),
                    action=audit_action,
                    node_id=node_id,
                    details={"service_name": service_name, "action": action},
                )
        else:
            if db is not None:
                action_enum_name = f"{action.upper()}_SERVICE"
                audit_action = getattr(AuditAction, action_enum_name, AuditAction.INTENT_DISPATCH)
                await log_action(
                    db,
                    user_id=claims.get("sub", "system"),
                    action=audit_action,
                    node_id=node_id,
                    details={
                        "error": result.get("error"),
                        "status": "FAILED",
                        "service_name": service_name,
                        "action": action,
                    },
                )

        return {
            "success": result.get("success", False),
            "output": result.get("output", ""),
            "error": result.get("error") if not result.get("success") else None,
        }

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        """Return plugin info and configuration schema."""
        return {
            "name": "Systemd Manager",
            "description": (
                "Interrogates and manipulates systemd services. "
                "Provides system state verification and unit action execution."
            ),
            "category": "System",
            "schema": {
                "monitored_services": {
                    "type": "string",
                    "title": "Monitored Services",
                    "default": "ssh,docker,nginx",
                    "description": (
                        "Comma-separated list of systemd services to highlight "
                        "or monitor on the dashboard."
                    ),
                },
                "allow_restart_all": {
                    "type": "boolean",
                    "title": "Allow Restarting All Services",
                    "default": False,
                    "description": (
                        "If enabled, allows operators to trigger restarts on any "
                        "systemd service. If disabled, restarts are restricted to whitelist."
                    ),
                },
            },
        }
