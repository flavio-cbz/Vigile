from __future__ import annotations

"""
Vigile — Public Plugins API Router

Endpoints:
  - GET /api/plugins/pages  → List all pages from active plugins (for SPA)
  - GET /api/plugins/pages/sidebar  → Only sidebar pages (for navigation)
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from master.api.deps import require_role
from master.core.plugin_engine import PluginEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


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
