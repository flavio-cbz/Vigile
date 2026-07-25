"""
Vigile — RouteRegistrar

Dynamic FastAPI route mounting and unmounting for plugins.

Mounts an APIRouter under ``/api/plugins/{plugin_id}/`` for each plugin's
declared routes. Unmounting rebuilds the application's route table by
filtering out the routes the registrar installed.

The registrar uses a FastAPI APIRouter per plugin so routes can be
individually mounted and unmounted without affecting other routes.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, FastAPI

logger = logging.getLogger(__name__)


class RouteRegistrar:
    """Manages dynamic FastAPI route mounting for plugins."""

    def __init__(self, app: FastAPI | None = None) -> None:
        self._app = app
        # plugin_id -> list of (path, method) tuples for unmounting
        self._mounted_routes: dict[str, list[tuple[str, str]]] = {}

    def set_app(self, app: FastAPI) -> None:
        """Set or update the FastAPI application reference."""
        self._app = app

    def mount(
        self,
        plugin_id: str,
        routes_spec: list[dict[str, Any]],
        instance: Any,
    ) -> None:
        """Mount routes for a plugin on the FastAPI app.

        Each spec dict must have ``path``, ``method``, ``handler``
        (method name on instance), and optional ``roles``.
        """
        if self._app is None:
            logger.warning(
                "RouteRegistrar: no FastAPI app set — cannot mount routes for '%s'",
                plugin_id,
            )
            return

        if plugin_id in self._mounted_routes:
            logger.warning(
                "RouteRegistrar: '%s' already has mounted routes — unmount first",
                plugin_id,
            )
            return

        router = APIRouter(prefix=f"/api/plugins/{plugin_id}", tags=[f"plugin:{plugin_id}"])

        mounted: list[tuple[str, str]] = []
        for spec in routes_spec:
            path = spec["path"]
            method = spec["method"].upper()
            handler_name = spec["handler"]
            fn = getattr(instance, handler_name, None)
            if fn is None:
                logger.error(
                    "RouteRegistrar: '%s' has no handler '%s'",
                    plugin_id,
                    handler_name,
                )
                continue

            if method == "GET":
                router.get(path)(fn)
            elif method == "POST":
                router.post(path)(fn)
            elif method == "PUT":
                router.put(path)(fn)
            elif method == "DELETE":
                router.delete(path)(fn)
            elif method == "PATCH":
                router.patch(path)(fn)
            else:
                logger.warning(
                    "RouteRegistrar: unsupported method '%s' for %s route '%s'",
                    method,
                    plugin_id,
                    path,
                )
                continue

            mounted.append((f"/api/plugins/{plugin_id}{path}", method))

        self._app.include_router(router)
        self._mounted_routes[plugin_id] = mounted
        logger.info(
            "RouteRegistrar: mounted %d routes for plugin '%s'",
            len(mounted),
            plugin_id,
        )

    def unmount(self, plugin_id: str) -> None:
        """Unmount all routes for a plugin.

        This rebuilds the route table, filtering out the routes that were
        mounted for this plugin.
        """
        if self._app is None:
            return

        mounted = self._mounted_routes.pop(plugin_id, [])
        if not mounted:
            return

        mounted_paths = {path for path, _ in mounted}

        new_routes = []
        removed = 0
        for route in self._app.router.routes:
            if hasattr(route, "path") and route.path in mounted_paths:
                removed += 1
                continue
            new_routes.append(route)

        self._app.router.routes = new_routes
        logger.info(
            "RouteRegistrar: unmounted %d routes for plugin '%s' (removed %d)",
            len(mounted),
            plugin_id,
            removed,
        )

    def get_mounted(self, plugin_id: str) -> list[str]:
        """Return the list of paths mounted for a plugin."""
        return [path for path, _ in self._mounted_routes.get(plugin_id, [])]
