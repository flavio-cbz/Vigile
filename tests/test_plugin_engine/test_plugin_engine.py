from __future__ import annotations

import asyncio

from master.core.plugin_engine import PluginEngine
from master.core.hook_bus import HookBus
from master.core.scheduler import Scheduler


class TestHookBus:
    def test_initial_state_empty(self):
        bus = HookBus()
        assert bus.get_hooks() == {}
        assert not bus.has_hook("anything")

    def test_register_and_call_sync(self):
        bus = HookBus()
        bus.register("on_test", lambda: "ok", plugin_name="sys")
        assert bus.has_hook("on_test")
        assert bus.call("on_test") == ["ok"]

    def test_unregister_removes_hook(self):
        bus = HookBus()
        bus.register("on_test", lambda: "ok", plugin_name="sys")
        removed = bus.unregister("on_test", "sys")
        assert removed == 1
        assert not bus.has_hook("on_test")

    def test_exception_caught_in_call(self):
        bus = HookBus()
        bus.register("on_test", lambda: 1 / 0, plugin_name="sys")
        result = bus.call("on_test")
        assert result == []

    def test_call_first_returns_first(self):
        bus = HookBus()
        bus.register("on_test", lambda: "first", plugin_name="a")
        bus.register("on_test", lambda: "second", plugin_name="b")
        assert bus.call_first("on_test") == "first"

    def test_async_call_dispatches(self):
        bus = HookBus()

        async def async_hook(**kw):
            return "async_ok"

        bus.register("on_test", async_hook, plugin_name="sys")

        async def do():
            return await bus.async_call("on_test")

        results = asyncio.run(do())
        assert results == ["async_ok"]


class TestPluginEngine:
    def test_initial_state(self):
        engine = PluginEngine(
            hook_bus=HookBus(),
            scheduler=Scheduler(),
        )
        assert engine.loaded_plugins == []

    def test_get_hooks_empty(self):
        engine = PluginEngine(hook_bus=HookBus())
        assert engine.get_hooks() == {}

    def test_has_hook_false(self):
        engine = PluginEngine(hook_bus=HookBus())
        assert not engine.has_hook("anything")

    def test_register_direct_hook(self):
        engine = PluginEngine(hook_bus=HookBus())
        engine.register("on_test", lambda **kw: "ok", plugin_name="sys")
        assert engine.has_hook("on_test")

    def test_call_dispatches_to_hook(self):
        engine = PluginEngine(hook_bus=HookBus())
        engine.register("on_test", lambda **kw: "ok", plugin_name="sys")
        result = engine.call("on_test")
        assert result == ["ok"]

    def test_async_call_returns_results(self):
        engine = PluginEngine(hook_bus=HookBus())

        async def async_hook(**kw):
            return "async_ok"

        engine.register("on_test", async_hook, plugin_name="sys")

        async def do():
            return await engine.async_call("on_test")

        results = asyncio.run(do())
        assert results == ["async_ok"]

    def test_shutdown_unloads_everything(self):
        engine = PluginEngine(hook_bus=HookBus(), scheduler=Scheduler())
        engine.register("on_test", lambda **kw: "ok", plugin_name="sys")

        async def do():
            await engine.shutdown()

        asyncio.run(do())
        assert engine.loaded_plugins == []
