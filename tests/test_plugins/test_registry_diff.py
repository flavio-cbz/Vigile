from __future__ import annotations

import pytest
from master.core.route_registrar import RouteRegistrar
from master.core.plugin_base import PluginBase, PluginContext, route
from master.core.plugin_manager import plugin_engine
from fastapi import FastAPI

pytestmark = pytest.mark.asyncio


async def test_plugin_registry_routes_validity(db):
    await plugin_engine.load_plugins_from_dir("master/plugins")
    for plugin_id, plugin in plugin_engine._instances.items():
        if not hasattr(plugin, "routes"):
            continue
        for route_spec in plugin.routes:
            method = route_spec.get("method")
            path = route_spec.get("path")
            handler_name = route_spec.get("handler")
            assert method in ("GET", "POST", "PUT", "DELETE", "PATCH"), f"Plugin {plugin_id}: invalid method {method}"
            assert path.startswith("/"), f"Plugin {plugin_id}: path {path} must start with /"
            assert hasattr(plugin, handler_name), f"Plugin {plugin_id}: missing handler {handler_name}"
            assert callable(getattr(plugin, handler_name)), f"Plugin {plugin_id}: handler {handler_name} not callable"


async def test_route_registrar_mount_unmount_cleanly():
    app = FastAPI()
    registrar = RouteRegistrar(app)

    class DummyPlugin(PluginBase):
        plugin_id = "dummy_test"

        @route("/dummy/status", method="GET")
        async def dummy_handler(self):
            return {"ok": True}

    ctx = PluginContext(plugin_id="dummy_test", config={}, db=None)
    plugin = DummyPlugin(ctx)
    registrar.mount("dummy_test", plugin.routes, plugin)

    route_paths = [r.path for r in app.routes]
    assert any("dummy/status" in r.path for r in app.routes)

    registrar.unmount("dummy_test")
    route_paths_after = [r.path for r in app.routes]
    assert not any("dummy/status" in p for p in route_paths_after)
