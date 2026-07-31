"""
Vigile — Canonical Plugin Identifiers

Single source of truth for mapping on-disk plugin file stems
and public canonical plugin identifiers.
"""

from __future__ import annotations

import json
import os

_BUILTIN_FILE_TO_ID: dict[str, str] = {
    "metrics_plugin": "metrics",
    "systemd_plugin": "systemd",
    "docker_plugin": "docker",
}

_BUILTIN_ID_TO_FILE: dict[str, str] = {
    plugin_id: file_stem for file_stem, plugin_id in _BUILTIN_FILE_TO_ID.items()
}


def canonical_plugin_id(name: str, plugins_dir: str | None = None) -> str:
    """Map an on-disk plugin stem or name to the public canonical plugin id."""
    if plugins_dir:
        manifest_path = os.path.join(plugins_dir, name, "manifest.json")
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "id" in data and data["id"]:
                    return str(data["id"])
            except Exception:
                pass

    if name in _BUILTIN_FILE_TO_ID:
        return _BUILTIN_FILE_TO_ID[name]
    if name.endswith("_plugin"):
        return name[:-7]
    return name


def plugin_file_stem(plugin_id: str) -> str:
    """Resolve the on-disk file stem for a public canonical plugin id."""
    return _BUILTIN_ID_TO_FILE.get(plugin_id, plugin_id)


def is_plugin_active(plugin_id: str) -> bool:
    """Helper global de vérification de l'état actif d'un plugin dans le runtime."""
    try:
        import master.core.plugin_manager as _pm_mod
        engine = _pm_mod.plugin_engine if _pm_mod.plugin_engine is not None else _pm_mod.plugin_manager
        if engine is None:
            return False
        if hasattr(engine, "is_plugin_loaded"):
            return engine.is_plugin_loaded(plugin_id)

        canon = canonical_plugin_id(plugin_id)
        stem = plugin_file_stem(plugin_id)
        disabled = getattr(engine, "_disabled_plugins", set())
        if canon in disabled or stem in disabled or plugin_id in disabled:
            return False
        loaded = getattr(engine, "loaded_plugins", [])
        return canon in loaded or stem in loaded or plugin_id in loaded
    except Exception:
        return False

