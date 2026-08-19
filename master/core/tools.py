"""
Vigile — Tool Calling System

Defines the OpenAI-compatible tool schemas for fleet operations, node metrics,
systemd services, Docker containers, and logs. Includes ToolExecutor for running
actions via NodeManager or raising ActionProposals for validation.
"""

import json
import logging
import time
from typing import Any, TypedDict, Optional
import aiosqlite

from master.core.node_manager import NodeManager
from master.core.enums import WorkerAction, RiskLevel
from master.core.action_proposal import ActionProposal
from master.plugins.systemd_plugin import parse_service_list, parse_service_status
from master.plugins.docker_plugin import parse_container_list

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool Schemas for LLM
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_fleet_overview",
            "description": "Obtenir la liste globale de tous les nœuds de la flotte avec leur état et métriques de base.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_node_metrics",
            "description": "Obtenir les métriques d'utilisation détaillées d'un nœud (CPU, RAM, disque, uptime).",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id_or_name": {
                        "type": "string",
                        "description": "ID unique du nœud (UUID) ou son nom textuel.",
                    }
                },
                "required": ["node_id_or_name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_services",
            "description": "Lister tous les services systemd actifs ou inactifs sur un nœud spécifique.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id_or_name": {
                        "type": "string",
                        "description": "ID unique du nœud (UUID) ou son nom.",
                    }
                },
                "required": ["node_id_or_name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_service_status",
            "description": "Vérifier le statut détaillé d'un service systemd spécifique sur un nœud.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id_or_name": {
                        "type": "string",
                        "description": "ID unique du nœud (UUID) ou son nom.",
                    },
                    "service_name": {
                        "type": "string",
                        "description": "Nom du service systemd (ex: ssh, nginx.service, docker).",
                    },
                },
                "required": ["node_id_or_name", "service_name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_containers",
            "description": "Lister les conteneurs Docker (actifs et inactifs) s'exécutant sur un nœud spécifique.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id_or_name": {
                        "type": "string",
                        "description": "ID unique du nœud (UUID) ou son nom.",
                    }
                },
                "required": ["node_id_or_name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_logs",
            "description": "Lire les dernières lignes des fichiers de log système ou applicatifs sur un nœud.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id_or_name": {
                        "type": "string",
                        "description": "ID unique du nœud (UUID) ou son nom.",
                    },
                    "log_path": {
                        "type": "string",
                        "description": "Chemin facultatif du fichier ou nom de service/conteneur (ex: /var/log/syslog, nginx, docker). Par défaut, syslog.",
                    },
                    "lines": {
                        "type": "integer",
                        "description": "Nombre de lignes à extraire (par défaut 50, maximum 200).",
                        "default": 50,
                    },
                },
                "required": ["node_id_or_name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_restart_service",
            "description": "Créer une proposition d'action pour redémarrer un service systemd. Nécessite l'approbation de l'opérateur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id_or_name": {
                        "type": "string",
                        "description": "ID unique du nœud (UUID) ou son nom.",
                    },
                    "service_name": {
                        "type": "string",
                        "description": "Nom du service systemd à redémarrer (ex: nginx.service).",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Explication claire en français de la raison de ce redémarrage, basée sur vos observations.",
                    },
                },
                "required": ["node_id_or_name", "service_name", "reasoning"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_restart_container",
            "description": "Créer une proposition d'action pour redémarrer un conteneur Docker. Nécessite l'approbation de l'opérateur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id_or_name": {
                        "type": "string",
                        "description": "ID unique du nœud (UUID) ou son nom.",
                    },
                    "container_id_or_name": {
                        "type": "string",
                        "description": "ID unique ou nom du conteneur Docker à redémarrer.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Explication claire en français de la raison de ce redémarrage, basée sur vos observations.",
                    },
                },
                "required": ["node_id_or_name", "container_id_or_name", "reasoning"],
                "additionalProperties": False,
            },
        },
    },
]


class ToolResult(TypedDict):
    success: bool
    data: Any
    error: Optional[str]
    proposal_id: Optional[str]


# ---------------------------------------------------------------------------
# Tool Executor Core
# ---------------------------------------------------------------------------

class ToolExecutor:
    """Resolves node names, runs read-only actions, or creates proposals for mutations."""

    @staticmethod
    async def resolve_node(db: aiosqlite.Connection, node_id_or_name: str) -> dict[str, Any]:
        """
        Lookup a node by UUID, exact name, or partial name match.
        Raises ValueError if not found or ambiguous.
        """
        # 1. Direct UUID match
        async with db.execute("SELECT * FROM nodes WHERE id = ?", (node_id_or_name,)) as cursor:
            row = await cursor.fetchone()
        if row:
            return dict(row)

        # 2. Case-insensitive exact name or hostname match
        async with db.execute(
            "SELECT * FROM nodes WHERE LOWER(name) = ? OR LOWER(hostname) = ?",
            (node_id_or_name.lower(), node_id_or_name.lower())
        ) as cursor:
            rows = [dict(r) for r in await cursor.fetchall()]
        
        if len(rows) == 1:
            return rows[0]

        # 3. Partial case-insensitive name/hostname match
        if not rows:
            async with db.execute(
                "SELECT * FROM nodes WHERE name LIKE ? OR hostname LIKE ?",
                (f"%{node_id_or_name}%", f"%{node_id_or_name}%")
            ) as cursor:
                rows = [dict(r) for r in await cursor.fetchall()]
        
        if len(rows) == 1:
            return rows[0]
        elif len(rows) > 1:
            names = ", ".join(f"'{r['name']}' ({r['id'][:8]})" for r in rows)
            raise ValueError(
                f"Le nom de nœud '{node_id_or_name}' est ambigu. Correspondances trouvées : {names}. "
                "Veuillez spécifier l'ID ou le nom exact."
            )
        
        raise ValueError(f"Aucun nœud trouvé avec le nom ou l'ID '{node_id_or_name}'.")

    @classmethod
    async def execute(
        cls,
        tool_name: str,
        arguments: dict[str, Any],
        nm: NodeManager,
        db: aiosqlite.Connection,
        user_id: str,
    ) -> ToolResult:
        """Execute a tool request and return a structured ToolResult."""
        try:
            # 1. Tools that do not require target node resolution
            if tool_name == "get_fleet_overview":
                nodes = await nm.list_nodes(db)
                simplified = []
                for n in nodes:
                    simplified.append({
                        "id": n["id"],
                        "name": n["name"],
                        "hostname": n["hostname"],
                        "state": n["state"],
                        "online": n["online"],
                        "os": n["os"],
                        "arch": n["arch"],
                    })
                return {"success": True, "data": simplified, "error": None, "proposal_id": None}

            # 2. All other tools require resolving the node target
            node_id_or_name = arguments.get("node_id_or_name")
            if not node_id_or_name:
                raise ValueError("Le paramètre 'node_id_or_name' est requis.")
            
            node = await cls.resolve_node(db, node_id_or_name)
            node_id = node["id"]
            node_name = node["name"]
            online = node_id in nm._connections

            # 3. Operations execution
            if tool_name == "get_node_metrics":
                # Get latest snapshot from DB
                async with db.execute(
                    "SELECT cpu_percent, mem_percent, disk_percent, uptime_seconds, collected_at "
                    "FROM metrics_snapshots WHERE node_id = ? "
                    "ORDER BY collected_at DESC LIMIT 1",
                    (node_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                
                metrics = dict(row) if row else None
                return {
                    "success": True,
                    "data": {
                        "node_id": node_id,
                        "node_name": node_name,
                        "online": online,
                        "state": node["state"],
                        "metrics": metrics,
                    },
                    "error": None,
                    "proposal_id": None
                }

            # For actions querying worker, make sure the node is online
            if not online:
                raise RuntimeError(
                    f"Le nœud '{node_name}' ({node_id[:8]}) est déconnecté. "
                    "Impossible d'interroger ou de modifier son état."
                )

            if tool_name == "list_services":
                result = await nm.send_intent(node_id, {"action": "LIST_SERVICES", "params": {}}, timeout=15.0)
                if not result.get("success"):
                    raise RuntimeError(result.get("error", "Erreur lors de la récupération des services."))
                parsed = parse_service_list(result.get("output", ""))
                return {"success": True, "data": parsed, "error": None, "proposal_id": None}

            elif tool_name == "get_service_status":
                service_name = arguments.get("service_name")
                if not service_name:
                    raise ValueError("Le paramètre 'service_name' est requis.")
                result = await nm.send_intent(
                    node_id,
                    {"action": "STATUS_SERVICE", "params": {"name": service_name}},
                    timeout=15.0
                )
                if not result.get("success"):
                    raise RuntimeError(result.get("error", f"Impossible d'obtenir le statut de {service_name}."))
                parsed = parse_service_status(result.get("output", ""))
                return {"success": True, "data": parsed, "error": None, "proposal_id": None}

            elif tool_name == "list_containers":
                result = await nm.send_intent(node_id, {"action": "LIST_CONTAINERS", "params": {}}, timeout=15.0)
                if not result.get("success"):
                    raise RuntimeError(result.get("error", "Erreur lors de la récupération des conteneurs."))
                parsed = parse_container_list(result.get("output", ""))
                return {"success": True, "data": parsed, "error": None, "proposal_id": None}

            elif tool_name == "read_logs":
                log_path = arguments.get("log_path") or "syslog"
                lines = arguments.get("lines") or 50
                lines = min(max(int(lines), 1), 200) # Bounds clamp
                
                result = await nm.send_intent(
                    node_id,
                    {"action": "READ_LOGS", "params": {"path": log_path, "lines": lines}},
                    timeout=15.0
                )
                if not result.get("success"):
                    raise RuntimeError(result.get("error", f"Impossible de lire le log '{log_path}'."))
                
                return {
                    "success": True,
                    "data": {
                        "log_path": log_path,
                        "lines_returned": len(result.get("output", "").splitlines()),
                        "output": result.get("output", ""),
                    },
                    "error": None,
                    "proposal_id": None
                }

            # 4. Action proposals (mutations) requiring human approval
            elif tool_name == "propose_restart_service":
                service_name = arguments.get("service_name")
                reasoning = arguments.get("reasoning", "")
                if not service_name:
                    raise ValueError("Le paramètre 'service_name' est requis.")
                
                proposal = ActionProposal(
                    node_id=node_id,
                    action=WorkerAction.RESTART_SERVICE.value,
                    params={"service": service_name},
                    reasoning=reasoning,
                    risk_level=RiskLevel.MEDIUM.value,
                    created_by=user_id,
                )
                
                # Persist proposal
                db_data = proposal.to_db_dict()
                await db.execute(
                    """
                    INSERT INTO action_proposals
                        (id, node_id, action, params_json, reasoning, risk_level,
                         status, created_by, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        db_data["id"],
                        db_data["node_id"],
                        db_data["action"],
                        db_data["params_json"],
                        db_data["reasoning"],
                        db_data["risk_level"],
                        db_data["status"],
                        db_data["created_by"],
                        db_data["created_at"],
                        db_data["updated_at"],
                    ),
                )
                await db.commit()
                
                return {
                    "success": True,
                    "data": {
                        "proposal_id": proposal.id,
                        "status": proposal.status,
                        "action": proposal.action,
                        "params": proposal.params,
                        "reasoning": proposal.reasoning,
                        "risk_level": proposal.risk_level,
                    },
                    "error": None,
                    "proposal_id": proposal.id
                }

            elif tool_name == "propose_restart_container":
                container_id_or_name = arguments.get("container_id_or_name")
                reasoning = arguments.get("reasoning", "")
                if not container_id_or_name:
                    raise ValueError("Le paramètre 'container_id_or_name' est requis.")
                
                proposal = ActionProposal(
                    node_id=node_id,
                    action=WorkerAction.RESTART_CONTAINER.value,
                    params={"container": container_id_or_name},
                    reasoning=reasoning,
                    risk_level=RiskLevel.MEDIUM.value,
                    created_by=user_id,
                )
                
                # Persist proposal
                db_data = proposal.to_db_dict()
                await db.execute(
                    """
                    INSERT INTO action_proposals
                        (id, node_id, action, params_json, reasoning, risk_level,
                         status, created_by, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        db_data["id"],
                        db_data["node_id"],
                        db_data["action"],
                        db_data["params_json"],
                        db_data["reasoning"],
                        db_data["risk_level"],
                        db_data["status"],
                        db_data["created_by"],
                        db_data["created_at"],
                        db_data["updated_at"],
                    ),
                )
                await db.commit()
                
                return {
                    "success": True,
                    "data": {
                        "proposal_id": proposal.id,
                        "status": proposal.status,
                        "action": proposal.action,
                        "params": proposal.params,
                        "reasoning": proposal.reasoning,
                        "risk_level": proposal.risk_level,
                    },
                    "error": None,
                    "proposal_id": proposal.id
                }

            else:
                raise ValueError(f"Outil inconnu '{tool_name}'.")

        except Exception as exc:
            logger.warning("Error executing tool %s: %s", tool_name, exc)
            return {"success": False, "data": None, "error": str(exc), "proposal_id": None}
