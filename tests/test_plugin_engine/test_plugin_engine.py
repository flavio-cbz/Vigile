import pytest

from master.core.plugin_base import PluginBase, PluginContext
from master.core.plugin_engine import (
    LifecycleManager,
    LifecycleError,
    PluginEngine,
    STATE_ACTIVE,
    STATE_DEACTIVATED,
    STATE_INSTALLED,
    STATE_UNINSTALL,
    STATE_DECOUVERT,
)
from master.core.plugin_manifest import PluginManifest
from master.core.hook_bus import HookBus
from master.core.scheduler import Scheduler


class TestLifecycleManager:
    def test_initial_state_decouvert(self):
        lm = LifecycleManager()
        assert lm.get_state("unknown") == STATE_DECOUVERT

    def test_valid_transition_install(self):
        lm = LifecycleManager()

        async def do():
            await lm.transition("p1", STATE_INSTALLED)

        import asyncio

        asyncio.run(do())
        assert lm.get_state("p1") == STATE_INSTALLED

    def test_invalid_transition_raises(self):
        lm = LifecycleManager()
        lm._states["p1"] = STATE_INSTALLED

        async def do():
            with pytest.raises(LifecycleError):
                await lm.transition("p1", STATE_DECOUVERT)

        import asyncio

        asyncio.run(do())

    def test_get_all_states(self):
        lm = LifecycleManager()
        lm._states["a"] = STATE_INSTALLED
        lm._states["b"] = STATE_ACTIVE
        all_states = lm.get_all_states()
        assert all_states == {"a": STATE_INSTALLED, "b": STATE_ACTIVE}


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

    def test_register_hooks_from_instance(self):
        hook_bus = HookBus()
        engine = PluginEngine(hook_bus=hook_bus)

        class TestPlugin(PluginBase):
            plugin_id = "test_p"

            def __init__(self, ctx):
                super().__init__(ctx)

            @PluginBase._collect_decorated
            def _collected(self):
                return {"routes": [], "hooks": [], "scheduled": []}

        ctx = PluginContext(plugin_id="test_p", config={}, db=None)
        instance = TestPlugin(ctx)

        async def do():
            await engine.register_hooks_from_instance("test_p", instance)

        import asyncio

        asyncio.run(do())

    def test_activate_and_deactivate(self):
        hook_bus = HookBus()
        scheduler = Scheduler()

        def dummy_hook(**kw):
            return "ok"

        hook_bus.register("on_test", dummy_hook, plugin_name="sys")

        engine = PluginEngine(hook_bus=hook_bus, scheduler=scheduler)

        class TestPlugin(PluginBase):
            plugin_id = "test_p"

            def __init__(self, ctx):
                super().__init__(ctx)

        manifest = PluginManifest(
            id="test_p",
            name="Test Plugin",
            version="1.0.0",
        )
        ctx = PluginContext(plugin_id="test_p", config={}, db=None)
        instance = TestPlugin(ctx)

        async def do():
            await engine.install("test_p")
            await engine.activate("test_p", manifest, instance)
            assert engine.lifecycle.get_state("test_p") == STATE_ACTIVE
            await engine.deactivate("test_p")
            assert engine.lifecycle.get_state("test_p") == STATE_DEACTIVATED

        import asyncio

        asyncio.run(do())

    def test_uninstall_deactivates_first(self):
        engine = PluginEngine(hook_bus=HookBus(), scheduler=Scheduler())

        class TestPlugin(PluginBase):
            plugin_id = "test_p"

            def __init__(self, ctx):
                super().__init__(ctx)

        manifest = PluginManifest(
            id="test_p",
            name="Test Plugin",
            version="1.0.0",
        )
        ctx = PluginContext(plugin_id="test_p", config={}, db=None)
        instance = TestPlugin(ctx)

        async def do():
            await engine.install("test_p")
            await engine.activate("test_p", manifest, instance)
            await engine.uninstall("test_p")
            assert engine.lifecycle.get_state("test_p") == STATE_DECOUVERT

        import asyncio

        asyncio.run(do())

    def test_shutdown_deactivates_all(self):
        hook_bus = HookBus()
        scheduler = Scheduler()
        engine = PluginEngine(hook_bus=hook_bus, scheduler=scheduler)

        class TestPlugin(PluginBase):
            plugin_id = "test_p"

            def __init__(self, ctx):
                super().__init__(ctx)

        manifest = PluginManifest(
            id="test_p",
            name="Test Plugin",
            version="1.0.0",
        )
        ctx = PluginContext(plugin_id="test_p", config={}, db=None)
        instance = TestPlugin(ctx)

        async def do():
            await engine.install("test_p")
            await engine.activate("test_p", manifest, instance)
            await engine.shutdown()
            assert engine.lifecycle.get_state("test_p") == STATE_DEACTIVATED

        import asyncio

        asyncio.run(do())
