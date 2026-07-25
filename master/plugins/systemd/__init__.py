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

from fastapi import Depends
from master.core.plugin_base import PluginBase, PluginContext, hook, route
from master.api.deps import get_node_manager

logger = logging.getLogger(__name__)


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
    try:
        raw = json.loads(output)
        if not isinstance(raw, list):
            return None
        validated = [ServiceInfo(**item).model_dump() for item in raw]
        return validated
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Invalid service list from worker: %s", exc)
        return None


def parse_service_status(output: str) -> dict[str, str] | None:
    """Parse the JSON object returned by the Worker for STATUS_SERVICE."""
    try:
        raw = json.loads(output)
        validated = ServiceStatus(**raw)
        return validated.model_dump()
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Invalid service status from worker: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


class SystemdPlugin(PluginBase):
    """Systemd Service Manager plugin using the class-based PluginBase API."""

    plugin_id: str = "systemd"

    # Copilot actions supported by this plugin
    copilot_actions: list[dict[str, Any]] = [
        {"action": "LIST_SERVICES", "risk_level": "LOW"},
        {"action": "STATUS_SERVICE", "risk_level": "LOW"},
        {"action": "RESTART_SERVICE", "risk_level": "LOW"},
    ]

    def __init__(self, ctx: PluginContext) -> None:
        super().__init__(ctx)

    @hook("get_supported_actions")
    def _get_supported_actions(self) -> list[str]:
        """Return the list of systemd actions supported by the Worker."""
        return ["LIST_SERVICES", "STATUS_SERVICE", "RESTART_SERVICE"]

    @route("/services", method="GET", roles=["admin", "operator"])
    async def list_services_route(
        self,
        node_id: str | None = None,
        nm: Any = Depends(get_node_manager),
    ) -> dict:
        """Fetch systemd services list across workers."""
        nodes = []
        if node_id:
            nodes = [node_id]
        else:
            nodes = [node.id for node in nm.get_connected_nodes()]

        services = []
        for nid in nodes:
            try:
                result = await nm.send_intent(nid, {"action": "LIST_SERVICES"}, timeout=10.0)
                if result.get("success"):
                    parsed = parse_service_list(result.get("output", ""))
                    if parsed:
                        for srv in parsed:
                            services.append({
                                "node_id": nid,
                                "name": srv["name"],
                                "state": srv["state"],
                                "status": srv["status"]
                            })
            except Exception as e:
                logger.error("Failed to fetch services for node %s: %s", nid, e)

        return {"services": services, "count": len(services)}

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
