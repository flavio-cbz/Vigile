from __future__ import annotations

"""
Vigile — Plugin Utilities

Shared utility functions for parsing worker output across all plugins.
This module contains the common parsing logic that was duplicated across
plugin files.
"""

import json
import logging
from typing import Any, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

__all__ = [
    "parse_worker_output",
    "parse_worker_list",
    "parse_worker_object",
]


def parse_worker_output(output: str, model_class: type[T]) -> list[dict[str, Any]] | dict[str, Any] | None:
    """Parse JSON output from a Worker and validate with a Pydantic model.
    
    This is a shared utility for the common pattern used across plugins:
    1. Parse JSON from worker output
    2. Validate with Pydantic model
    3. Return model_dump() for further processing
    
    Args:
        output: JSON string from worker
        model_class: Pydantic model class to validate against
        
    Returns:
        - For list models: list of dicts from model_dump()
        - For single models: dict from model_dump()
        - None if parsing/validation fails
    """
    try:
        raw = json.loads(output)
        if isinstance(raw, list):
            # Handle list of items
            validated = [model_class(**item).model_dump() for item in raw]
            return validated
        elif isinstance(raw, dict):
            # Handle single item
            validated = model_class(**raw)
            return validated.model_dump()
        else:
            return None
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Invalid worker output: %s", exc)
        return None


def parse_worker_list(output: str, model_class: type[T]) -> list[dict[str, Any]] | None:
    """Parse JSON array output from a Worker and validate with a Pydantic model.
    
    Specialized version for list outputs (e.g., LIST_CONTAINERS, LIST_SERVICES).
    
    Args:
        output: JSON string from worker
        model_class: Pydantic model class to validate against
        
    Returns:
        List of dicts from model_dump(), or None if parsing/validation fails
    """
    try:
        raw = json.loads(output)
        if not isinstance(raw, list):
            return None
        validated = [model_class(**item).model_dump() for item in raw]
        return validated
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Invalid worker list output: %s", exc)
        return None


def parse_worker_object(output: str, model_class: type[T]) -> dict[str, Any] | None:
    """Parse JSON object output from a Worker and validate with a Pydantic model.
    
    Specialized version for single object outputs (e.g., STATUS_SERVICE).
    
    Args:
        output: JSON string from worker
        model_class: Pydantic model class to validate against
        
    Returns:
        Dict from model_dump(), or None if parsing/validation fails
    """
    try:
        raw = json.loads(output)
        validated = model_class(**raw)
        return validated.model_dump()
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Invalid worker object output: %s", exc)
        return None
