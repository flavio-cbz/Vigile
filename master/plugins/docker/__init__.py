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
from typing import Any

from pydantic import BaseModel, Field

from fastapi import Depends
from master.core.plugin_base import PluginBase, hook, route
from master.api.deps import get_node_manager

logger = logging.getLogger(__name__)

plugin_id = "docker"


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
    try:
        raw = json.loads(output)
        if not isinstance(raw, list):
            return None
        validated = [ContainerSummary(**item).model_dump() for item in raw]
        return validated
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Invalid container list from worker: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


class DockerPlugin(PluginBase):
    """Docker Container Orchestrator plugin.

    Registers hooks for container lifecycle management actions
    dispatched to Worker nodes over authenticated WebSocket intents.
    """

    plugin_id = "docker"

    @hook("get_supported_actions")
    def get_supported_actions(self) -> list[str]:
        """Return the list of Docker actions this plugin supports."""
        return ["LIST_CONTAINERS", "RESTART_CONTAINER"]

    @route("/containers", method="GET", roles=["admin", "operator"])
    async def list_containers_route(
        self,
        node_id: str | None = None,
        nm: Any = Depends(get_node_manager),
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
                result = await nm.send_intent(nid, {"action": "LIST_CONTAINERS"}, timeout=10.0)
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

        return {"containers": containers, "count": len(containers)}


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
