"""
Vigile — Systemd Plugin

Registers systemd-related actions supported by the Worker:
  - LIST_SERVICES
  - STATUS_SERVICE
  - RESTART_SERVICE

The Worker Go binary handles the actual systemd interaction.
This plugin exists to declare supported actions and provide
response model validation for the Master API.
"""

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

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
# Plugin registration
# ---------------------------------------------------------------------------


def register(pm) -> None:
    pm.register("get_supported_actions", _get_supported_actions, plugin_name="systemd")
    logger.info("Systemd plugin registered.")


def _get_supported_actions() -> list[str]:
    return ["LIST_SERVICES", "STATUS_SERVICE", "RESTART_SERVICE"]
