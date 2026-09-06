from __future__ import annotations

"""
Vigile — Docker Plugin (folder-format)

Class-based plugin using PluginBase and @hook decorators.
Declares Docker-related actions supported by the Worker:
  - LIST_CONTAINERS
  - RESTART_CONTAINER

The Worker Go binary handles the actual Docker API interaction via Unix socket.
This plugin exists to declare supported actions and provide
response model validation for the Master API.
"""

import json
import logging
import re
import time
from typing import Any

from pydantic import BaseModel, Field

from fastapi import Body, Depends, HTTPException
from master.core.plugin_base import PluginBase, hook, route
from master.api.deps import (
    get_db,
    get_node_manager,
    get_proposal_dispatcher,
    get_worker_query_port,
    require_role,
)
from master.core.audit import AuditAction, log_action
from master.core.plugin_utils import parse_worker_list

logger = logging.getLogger(__name__)

plugin_id = "docker"

_CONTAINER_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{3,64}$")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ContainerSummary(BaseModel):
    id: str = Field(description="Container ID (12-char prefix)")
    name: str = Field(description="Container name")
    image: str = Field(description="Container image")
    state: str = Field(description="Container state (running, exited, etc.)")
    ports: list[str] = Field(default_factory=list, description="Port mappings")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def parse_container_list(output: str) -> list[dict[str, Any]] | None:
    """Parse the JSON array returned by the Worker for LIST_CONTAINERS."""
    return parse_worker_list(output, ContainerSummary)


# ---------------------------------------------------------------------------
# Container lifecycle actions (mutation → ActionProposal channel)
# ---------------------------------------------------------------------------

# Actions proposées par l'UI (DockerContainers.tsx) — le clic de l'opérateur
# sur la page EST l'approbation : la proposition est créée directement
# APPROVED, puis dispatchée via ApprovedProposalDispatcher.
_CONTAINER_ACTIONS = frozenset({"stop", "start", "restart", "delete"})

_ACTION_TO_INTENT: dict[str, str] = {
    "restart": "RESTART_CONTAINER",
    "start": "START_CONTAINER",
    "stop": "STOP_CONTAINER",
    "delete": "DELETE_CONTAINER",
}

_ACTION_RISK_LEVEL: dict[str, str] = {
    "start": "LOW",
    "restart": "MEDIUM",
    "stop": "HIGH",
    "delete": "CRITICAL",
}


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


class DockerPlugin(PluginBase):
    """Docker Container Orchestrator plugin.

    Registers hooks for container lifecycle management actions
    dispatched to Worker nodes over authenticated WebSocket intents.
    """

    plugin_id = "docker"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        """Return plugin info and configuration schema."""
        return {
            "name": "Docker Orchestrator",
            "description": "Manages container life cycle, network sockets, container logs, and lifecycle controls directly over local unix socket paths.",
            "category": "Virtualization",
            "schema": {
                "docker_host": {
                    "type": "string",
                    "title": "Docker Host Socket",
                    "default": "unix:///var/run/docker.sock",
                    "description": "Unix socket path or TCP endpoint to connect to the Docker daemon.",
                },
                "auto_restart_failed": {
                    "type": "boolean",
                    "title": "Auto Restart Failed Containers",
                    "default": False,
                    "description": "Whether the orchestrator should automatically restart containers that exit with a non-zero code.",
                },
            },
        }

    @hook("get_supported_actions")
    def get_supported_actions(self) -> list[str]:
        """Return the list of Docker actions this plugin supports."""
        return [
            "LIST_CONTAINERS",
            "RESTART_CONTAINER",
            "START_CONTAINER",
            "STOP_CONTAINER",
            "DELETE_CONTAINER",
        ]

    @route("/containers", method="GET", roles=["admin", "operator"])
    async def list_containers_route(
        self,
        node_id: str | None = None,
        nm: Any = Depends(get_node_manager),
        port: Any = Depends(get_worker_query_port),
    ) -> dict:
        """Fetch Docker containers list across workers."""
        nodes = []
        if node_id:
            nodes = [node_id]
        else:
            nodes = [node.id for node in nm.get_connected_nodes()]

        containers = []
        for nid in nodes:
            try:
                result = await port.query(nid, "LIST_CONTAINERS", timeout=10.0)
                if result.get("success"):
                    parsed = parse_container_list(result.get("output", ""))
                    if parsed:
                        for container in parsed:
                            containers.append({
                                "node_id": nid,
                                "id": container["id"],
                                "name": container["name"],
                                "image": container["image"],
                                "state": container["state"],
                                "ports": container["ports"]
                            })
            except Exception as e:
                logger.error("Failed to fetch containers for node %s: %s", nid, e)

        return {"containers": containers, "count": len(containers), "cached_at": time.time()}

    @route("/containers/{container_id}/{action}", method="POST", roles=["admin", "operator"])
    async def container_action_route(
        self,
        container_id: str,
        action: str,
        body: dict[str, Any] | None = Body(default=None),
        claims: dict[str, Any] = Depends(require_role("admin", "operator")),
        db: Any = Depends(get_db),
        dispatcher: Any = Depends(get_proposal_dispatcher),
    ) -> dict:
        """Déclenche une action de cycle de vie sur un conteneur Docker.

        Mutation obligatoire : la proposition est créée APPROVED puis
        dispatchée via ApprovedProposalDispatcher — jamais
        NodeManager.send_intent() (déprécié).
        """
        if action not in _CONTAINER_ACTIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Action '{action}' invalide : attendu 'stop', 'start', 'restart' ou 'delete'.",
            )
        if not _CONTAINER_ID_REGEX.match(container_id):
            raise HTTPException(
                status_code=400,
                detail=f"Format de container_id invalide : '{container_id}'.",
            )
        node_id = (body or {}).get("node_id")
        if not node_id:
            raise HTTPException(
                status_code=400,
                detail="Champ 'node_id' manquant dans le corps de la requête.",
            )

        # Contrôle de rôle strict (B3) : stop et delete réservés aux administrateurs
        user_role = claims.get("role")
        if action in ("stop", "delete") and user_role != "admin":
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
                        "container_id": container_id,
                    },
                )
            raise HTTPException(
                status_code=403,
                detail=f"L'action '{action}' est strictement réservée aux administrateurs.",
            )

        container_name = (body or {}).get("container_name")
        if action == "delete" and not container_name:
            raise HTTPException(
                status_code=400,
                detail="container_name is required for delete",
            )

        intent = _ACTION_TO_INTENT.get(action)
        if intent is None:
            raise HTTPException(
                status_code=400,
                detail=f"L'action '{action}' n'est pas supportée.",
            )

        params: dict[str, Any] = {"container_id": container_id}
        if container_name:
            params["container_name"] = container_name

        risk_level = _ACTION_RISK_LEVEL.get(action, "MEDIUM")

        try:
            result = await dispatcher.dispatch_admin_action(
                node_id,
                intent,
                params,
                claims.get("sub", "unknown"),
                db,
                intent_timeout=15.0,
                reasoning=f"Action {action} sur le conteneur {container_id} (page Conteneurs)",
                risk_level=risk_level,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Le Worker n'a pas répondu dans le délai imparti.",
            )

        if db is not None:
            action_enum_name = f"{action.upper()}_CONTAINER"
            audit_action = getattr(AuditAction, action_enum_name, AuditAction.INTENT_DISPATCH)
            if result.get("success"):
                await log_action(
                    db,
                    user_id=claims.get("sub", "system"),
                    action=audit_action,
                    node_id=node_id,
                    details={
                        "container_id": container_id,
                        "container_name": container_name,
                        "action": action,
                    },
                )
            else:
                await log_action(
                    db,
                    user_id=claims.get("sub", "system"),
                    action=audit_action,
                    node_id=node_id,
                    details={
                        "error": result.get("error"),
                        "status": "FAILED",
                        "container_id": container_id,
                        "container_name": container_name,
                        "action": action,
                    },
                )

        return {
            "success": result.get("success", False),
            "output": result.get("output", ""),
            "error": result.get("error") if not result.get("success") else None,
        }


# ---------------------------------------------------------------------------
# Config schema (kept for backward compatibility with flat .py loading)
# ---------------------------------------------------------------------------


def get_config_schema() -> dict[str, Any]:
    """Return plugin info and configuration schema."""
    return {
        "name": "Docker Orchestrator",
        "description": "Manages container life cycle, network sockets, container logs, and lifecycle controls directly over local unix socket paths.",
        "category": "Virtualization",
        "schema": {
            "docker_host": {
                "type": "string",
                "title": "Docker Host Socket",
                "default": "unix:///var/run/docker.sock",
                "description": "Unix socket path or TCP endpoint to connect to the Docker daemon.",
            },
            "auto_restart_failed": {
                "type": "boolean",
                "title": "Auto Restart Failed Containers",
                "default": False,
                "description": "Whether the orchestrator should automatically restart containers that exit with a non-zero code.",
            },
        },
    }
