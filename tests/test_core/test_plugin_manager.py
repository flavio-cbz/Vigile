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
