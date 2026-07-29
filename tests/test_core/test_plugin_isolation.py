from __future__ import annotations

"""
Tests for plugin isolation and sandbox execution.
Verifies that plugins run in isolated subprocesses, communicate via JSON-RPC,
perform remote database proxying, and recover gracefully from subprocess crashes.
"""

import asyncio
import os
import shutil
import sys
import tempfile
import time

import aiosqlite
import pytest

from master.core.plugin_manager import PluginManager, PluginProcessWrapper


@pytest.fixture
def temp_plugins_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_plugin_process_wrapper_lifecycle(temp_plugins_dir):
    # 1. Create a dummy plugin file in the temp directory
    plugin_content = """
def register(pm):
    pm.register("multiply", _multiply, plugin_name="dummy")

def _multiply(x: int) -> int:
    return x * 3
"""
    plugin_path = os.path.join(temp_plugins_dir, "dummy_plugin.py")
    with open(plugin_path, "w") as f:
        f.write(plugin_content)

    # 2. Instantiate and start wrapper
    wrapper = PluginProcessWrapper("dummy", plugin_path)
    await wrapper.start()

    assert wrapper.process is not None
    assert "multiply" in wrapper.hooks

    # 3. Call hook
    res = await wrapper.call_hook("multiply", x=7)
    assert res == 21

    # 4. Stop wrapper
    await wrapper.stop()
    assert wrapper.process is None


@pytest.mark.asyncio
async def test_plugin_database_proxy(temp_plugins_dir, db: aiosqlite.Connection):
    # Create a plugin that queries the DB and commits
    plugin_content = """
def register(pm):
    pm.register("get_user_count", _get_user_count, plugin_name="dummy_db")

async def _get_user_count(db) -> int:
    cursor = await db.execute("SELECT COUNT(*) as count FROM users")
    row = await cursor.fetchone()
    return row["count"]
"""
    plugin_path = os.path.join(temp_plugins_dir, "dummy_db_plugin.py")
    with open(plugin_path, "w") as f:
        f.write(plugin_content)

    wrapper = PluginProcessWrapper("dummy_db", plugin_path)
    await wrapper.start()

    # Pass the active test DB to the hook
    res = await wrapper.call_hook("get_user_count", db=db)
    # The default conftest db has 2 users (default admin + test-user)
    assert res == 2

    await wrapper.stop()


@pytest.mark.asyncio
async def test_plugin_process_crash_and_restart(temp_plugins_dir):
    plugin_content = """
def register(pm):
    pm.register("ping", _ping, plugin_name="dummy_crash")

def _ping() -> str:
    return "pong"
"""
    plugin_path = os.path.join(temp_plugins_dir, "dummy_crash_plugin.py")
    with open(plugin_path, "w") as f:
        f.write(plugin_content)

    wrapper = PluginProcessWrapper("dummy_crash", plugin_path)
    await wrapper.start()

    # Call it once
    res1 = await wrapper.call_hook("ping")
    assert res1 == "pong"

    # Manually terminate process to simulate a crash
    wrapper.process.kill()
    await wrapper.process.wait()

    # Verify that calling again auto-restarts and succeeds
    res2 = await wrapper.call_hook("ping")
    assert res2 == "pong"

    await wrapper.stop()


@pytest.mark.asyncio
async def test_plugin_manager_sandbox_toggle(temp_plugins_dir, db):
    # Verify PluginManager loaded with sandbox=False runs in-process
    plugin_content = """
def register(pm):
    pm.register("test_hook", lambda: "in_process", plugin_name="dummy_mgr")
"""
    plugin_path = os.path.join(temp_plugins_dir, "dummy_mgr_plugin.py")
    with open(plugin_path, "w") as f:
        f.write(plugin_content)

    # sandbox=False
    pm_sync = PluginManager()
    await pm_sync.initialize(db, sandbox=False)
    success = await pm_sync.load_plugin("dummy_mgr_plugin", temp_plugins_dir)
    assert success is True
    assert "dummy_mgr_plugin" in pm_sync.loaded_plugins
    # Since it runs in-process, it should be in the local sys.modules
    assert "vigile.plugins.dummy_mgr_plugin" in sys.modules

    # Clean up sys.modules
    await pm_sync.unload_plugin("dummy_mgr_plugin")

    # sandbox=True
    pm_sandbox = PluginManager()
    await pm_sandbox.initialize(db, sandbox=True)
    success_sb = await pm_sandbox.load_plugin("dummy_mgr_plugin", temp_plugins_dir)
    assert success_sb is True
    assert "dummy_mgr_plugin" in pm_sandbox.loaded_plugins
    # In sandbox mode, the plugin file itself is NOT loaded in the parent process interpreter
    assert "vigile.plugins.dummy_mgr_plugin" not in sys.modules

    await pm_sandbox.unload_plugin("dummy_mgr_plugin")
