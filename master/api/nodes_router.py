"""
Vigile — Nodes Router (shared definition)

Defines the single ``router`` instance used by all ``nodes_*`` sub-modules
to register their route handlers.  Importing this file before any sub-module
avoids circular-import errors.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/nodes", tags=["nodes"])
