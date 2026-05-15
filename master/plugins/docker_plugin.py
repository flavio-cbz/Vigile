"""
Vigile — Docker Plugin

Registers Docker-related actions supported by the Worker:
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

logger = logging.getLogger(__name__)


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
# Plugin registration
# ---------------------------------------------------------------------------


def register(pm) -> None:
    pm.register("get_supported_actions", _get_supported_actions, plugin_name="docker")
    logger.info("Docker plugin registered.")


def _get_supported_actions() -> list[str]:
    return ["LIST_CONTAINERS", "RESTART_CONTAINER"]
