import asyncio
import logging
import os
import tempfile

import pytest

from master.core.plugin_manager import PluginManager


def test_hook_dispatch_sync(plugin_manager: PluginManager):
    plugin_manager.register("test_hook", lambda x: x * 2, plugin_name="double")
    plugin_manager.register("test_hook", lambda x: x + 10, plugin_name="adder")

    out = plugin_manager.call("test_hook", x=5)
    assert sorted(out) == [10, 15]
    assert plugin_manager.call_first("test_hook", x=3) in [6, 13]
    assert plugin_manager.call("nonexistent_hook") == []
    assert plugin_manager.has_hook("test_hook")
    assert not plugin_manager.has_hook("nonexistent_hook")


@pytest.mark.asyncio
async def test_hook_dispatch_async(plugin_manager: PluginManager):
    async def async_double(x):
        return x * 3

    plugin_manager.register("async_hook", async_double, plugin_name="async_triple")
    out = await plugin_manager.async_call("async_hook", x=4)
    assert out == [12]


def test_plugin_load_from_dir():
    with tempfile.TemporaryDirectory() as plugin_dir:
        plugin_code = """
def register(pm):
    pm.register("file_hook", lambda: "from_file", plugin_name="file_plugin")
"""
        with open(os.path.join(plugin_dir, "test_plugin.py"), "w") as f:
            f.write(plugin_code)
        pm = PluginManager()
        loaded = pm.load_plugins_from_dir(plugin_dir)
        assert "test_plugin" in loaded
        assert pm.call("file_hook") == ["from_file"]

        # Test dedup (already loaded)
        loaded_again = pm.load_plugins_from_dir(plugin_dir)
        assert "test_plugin" not in loaded_again


def test_unregister(plugin_manager: PluginManager):
    # Non-existent hook unregister
    assert plugin_manager.unregister("nonexistent_unregister", "any") == 0

    # Add hooks
    plugin_manager.register("unreg_hook", lambda: 1, plugin_name="p1")
    plugin_manager.register("unreg_hook", lambda: 2, plugin_name="p2")
    plugin_manager.register("unreg_hook", lambda: 3, plugin_name="p1")

    # Unregister p1
    removed = plugin_manager.unregister("unreg_hook", "p1")
    assert removed == 2
    assert plugin_manager.call("unreg_hook") == [2]


def test_sync_call_skips_async_hook(caplog):
    pm = PluginManager()

    async def dummy_async():
        pass

    pm.register("mixed_hook", dummy_async, plugin_name="async_plugin")

    with caplog.at_level(logging.WARNING):
        res = pm.call("mixed_hook")
        assert res == []
        assert "skipped in sync call()" in caplog.text

    # call_first should also skip it
    res_first = pm.call_first("mixed_hook")
    assert res_first is None


def test_call_exceptions_handled(caplog):
    pm = PluginManager()

    def raise_err():
        raise ValueError("Oops")

    pm.register("err_hook", raise_err, plugin_name="broken")

    with caplog.at_level(logging.ERROR):
        res = pm.call("err_hook")
        assert res == []
        assert "raised an exception" in caplog.text

    # call_first handles exceptions
    res_first = pm.call_first("err_hook")
    assert res_first is None


@pytest.mark.asyncio
async def test_async_call_first(plugin_manager: PluginManager):
    pm = PluginManager()

    async def async_one():
        return 42

    pm.register("async_first_hook", async_one, plugin_name="one")

    res = await pm.async_call_first("async_first_hook")
    assert res == 42

    res_empty = await pm.async_call_first("nonexistent_async_first")
    assert res_empty is None


@pytest.mark.asyncio
async def test_async_call_exceptions_and_sync_runs_in_executor(caplog):
    pm = PluginManager()
    # 1. Sync hook in async_call (runs in executor)
    pm.register("async_mix", lambda: "sync_val", plugin_name="sync_p")

    # 2. Async hook raising error
    async def async_raise():
        raise RuntimeError("Async error")

    pm.register("async_mix", async_raise, plugin_name="async_fail")

    with caplog.at_level(logging.ERROR):
        res = await pm.async_call("async_mix")
        assert "sync_val" in res
        assert "raised: Async error" in caplog.text


def test_load_plugins_from_invalid_dir():
    pm = PluginManager()
    res = pm.load_plugins_from_dir("/invalid/directory/path/that/doesnt/exist")
    assert res == []


def test_load_plugin_errors():
    with tempfile.TemporaryDirectory() as plugin_dir:
        # Plugin with no register function
        plugin_no_reg = "def not_register(pm): pass"
        with open(os.path.join(plugin_dir, "noreg_plugin.py"), "w") as f:
            f.write(plugin_no_reg)

        # Plugin with registration syntax error
        plugin_broken = "def register(pm):\n    raise ValueError('registration error')"
        with open(os.path.join(plugin_dir, "broken_plugin.py"), "w") as f:
            f.write(plugin_broken)

        # Non-py file (should be ignored)
        with open(os.path.join(plugin_dir, "ignored.txt"), "w") as f:
            f.write("text")

        pm = PluginManager()
        loaded = pm.load_plugins_from_dir(plugin_dir)
        # noreg_plugin is loaded but skipped (not in loaded return list)
        # broken_plugin raised ValueError (not in loaded return list)
        # ignored.txt is skipped (not in loaded return list)
        assert loaded == []
        assert pm.loaded_plugins == []


def test_plugin_manager_introspection():
    pm = PluginManager()
    pm.register("hook_a", lambda: 1, plugin_name="plugin_x")
    pm.register("hook_b", lambda: 2, plugin_name="plugin_y")

    hooks = pm.get_hooks()
    assert hooks == {"hook_a": ["plugin_x"], "hook_b": ["plugin_y"]}
    assert pm.loaded_plugins == []
