"""
Vigile — Canonical Plugin Identifiers

Single source of truth for mapping on-disk plugin file stems
and public canonical plugin identifiers.
"""

from __future__ import annotations

_BUILTIN_FILE_TO_ID: dict[str, str] = {
    "metrics_plugin": "metrics",
    "systemd_plugin": "systemd",
    "docker_plugin": "docker",
}

_BUILTIN_ID_TO_FILE: dict[str, str] = {
    plugin_id: file_stem for file_stem, plugin_id in _BUILTIN_FILE_TO_ID.items()
}


def canonical_plugin_id(name: str) -> str:
    """Map an on-disk plugin stem or name to the public canonical plugin id."""
    if name in _BUILTIN_FILE_TO_ID:
        return _BUILTIN_FILE_TO_ID[name]
    if name.endswith("_plugin"):
        return name[:-7]
    return name


def plugin_file_stem(plugin_id: str) -> str:
    """Resolve the on-disk file stem for a public canonical plugin id."""
    return _BUILTIN_ID_TO_FILE.get(plugin_id, plugin_id)
