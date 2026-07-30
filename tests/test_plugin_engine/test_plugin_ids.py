"""
Unit tests for master.core.plugin_ids and plugin engine runtime deduplication/unload behavior.
"""

from __future__ import annotations

import pytest
from master.core.plugin_ids import canonical_plugin_id, plugin_file_stem
from master.core.plugin_engine import PluginEngine


def test_builtin_plugin_id_resolution():
    assert canonical_plugin_id("docker_plugin") == "docker"
    assert canonical_plugin_id("metrics_plugin") == "metrics"
    assert canonical_plugin_id("systemd_plugin") == "systemd"

    assert plugin_file_stem("docker") == "docker_plugin"
    assert plugin_file_stem("metrics") == "metrics_plugin"
    assert plugin_file_stem("systemd") == "systemd_plugin"


def test_custom_plugin_id_resolution():
    assert canonical_plugin_id("custom_monitor_plugin") == "custom_monitor"
    assert canonical_plugin_id("foo") == "foo"

    assert plugin_file_stem("custom_monitor") == "custom_monitor"
    assert plugin_file_stem("foo") == "foo"


def test_plugin_engine_loaded_plugins_no_duplicates():
    engine = PluginEngine()
    engine._loaded_plugins = ["docker", "legacy_plugin"]
    engine._wrappers = {"docker": None} # type: ignore

    # "docker" is in wrappers AND _loaded_plugins -> should only appear once
    loaded = engine.loaded_plugins
    assert loaded.count("docker") == 1
    assert "legacy_plugin" in loaded


@pytest.mark.asyncio
async def test_plugin_engine_unload_cleans_loaded_plugins():
    engine = PluginEngine()
    engine._loaded_plugins = ["my_plugin"]

    await engine.unload_plugin("my_plugin")

    assert "my_plugin" not in engine._loaded_plugins
    assert "my_plugin" not in engine.loaded_plugins
