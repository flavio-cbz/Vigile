"""
Vigile — Code-Derived Command Registry Scan

Discovers every ``@route``-decorated handler across all loaded plugins and
produces a flat, deterministic command inventory. This is the J1 "code-derived
command inventory" — the migration reference is this scan, NEVER the manifest
(manifest ``routes[]`` is the legacy projection and is known to drift: plex
declares 11 ``@route`` in code vs 8 in manifest).

Two registration shapes are handled, mirroring ``plugin_engine``:

1. **Class-based** (``PluginBase`` subclass — all 4 built-in plugins): the
   scan iterates the plugin class attributes and reads ``fn.__plugin_route__``
   metadata stamped by the ``@route`` decorator (``plugin_base.py``).
2. **Module-level** (legacy ``register(pm)`` shape — e.g. metrics
   ``register()``): the scan accepts a module object and picks up any
   module-level function carrying ``__plugin_route__``.

The scan is intentionally dependency-free: it takes a mapping of
``plugin_id -> instance-or-module`` (e.g. ``PluginEngine._instances``) and
never touches the engine, the DB, or the filesystem.
"""

from __future__ import annotations

import types
from dataclasses import dataclass
from typing import Any, Mapping

from master.core.plugin_base import PluginBase

# Methods that mutate state — these must be dispatched through ActionProposal
# (PENDING → APPROVED → EXECUTED), never executed directly.
_MUTATING_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})

_DEFAULT_ROLES = ("viewer",)


@dataclass(frozen=True)
class CommandEntry:
    """One code-derived command backed by a plugin ``@route`` handler.

    Attributes
    ----------
    plugin_id:
        Plugin owning the route (canonical manifest id).
    name:
        Namespaced command name ``<plugin_id>.<handler>`` — the S1 namespace
        format (``id + "."``), ready for the LLM tool registry / permission
        catalog.
    method:
        HTTP method, uppercased (GET/POST/PUT/DELETE/PATCH).
    path_template:
        Route path as declared in ``@route`` (e.g. ``/{node_id}/photo``).
    mutation:
        ``True`` for POST/PUT/DELETE/PATCH — must go through ActionProposal.
    roles:
        Minimum roles required by the ``@route`` decorator (defaults to
        ``("viewer",)`` when the decorator omits ``roles``).
    resource_contract:
        Resource domain the command operates on — the plugin id (code-derived;
        a plugin owns exactly one domain). Future permission scoping (S7)
        intersects on this field.
    """

    plugin_id: str
    name: str
    method: str
    path_template: str
    mutation: bool
    roles: tuple[str, ...]
    resource_contract: str


def _entry_from_meta(
    plugin_id: str,
    handler_name: str,
    meta: dict[str, Any],
) -> CommandEntry:
    path = str(meta.get("path", "/"))
    method = str(meta.get("method", "GET")).upper()
    roles_list = meta.get("roles")
    roles = tuple(str(r) for r in (roles_list if roles_list is not None else _DEFAULT_ROLES))
    return CommandEntry(
        plugin_id=plugin_id,
        name=f"{plugin_id}.{handler_name}",
        method=method,
        path_template=path,
        mutation=method in _MUTATING_METHODS,
        roles=roles,
        resource_contract=plugin_id,
    )


def _scan_plugin_instance(plugin_id: str, instance: PluginBase) -> list[CommandEntry]:
    """Class-based shape: read ``__plugin_route__`` on class attributes."""
    entries: list[CommandEntry] = []
    cls = instance.__class__
    for name in dir(cls):
        if name.startswith("__") and name.endswith("__"):
            continue
        fn = getattr(cls, name, None)
        if not callable(fn):
            continue
        meta = getattr(fn, "__plugin_route__", None)
        if meta is not None:
            entries.append(_entry_from_meta(plugin_id, name, meta))
    return entries


def _scan_plugin_module(plugin_id: str, module: types.ModuleType) -> list[CommandEntry]:
    """Module-level shape (legacy ``register(pm)``): scan module functions."""
    entries: list[CommandEntry] = []
    for name, value in vars(module).items():
        if name.startswith("__"):
            continue
        if not callable(value):
            continue
        meta = getattr(value, "__plugin_route__", None)
        if meta is not None:
            entries.append(_entry_from_meta(plugin_id, name, meta))
    return entries


def scan_all_routes(
    plugins: Mapping[str, Any],
) -> list[CommandEntry]:
    """Scan every loaded plugin for ``@route``-decorated handlers.

    Parameters
    ----------
    plugins:
        Mapping of ``plugin_id -> plugin object``. Each value is either a
        ``PluginBase`` instance (class-based shape) or a module object
        (module-level ``register(pm)`` shape). ``PluginEngine._instances``
        is the natural source for class-based plugins.

    Returns
    -------
    list[CommandEntry]
        Deterministically ordered (by plugin_id, then path, then method),
        deduplicated on ``(plugin_id, path, method)``.
    """
    entries: list[CommandEntry] = []
    seen: set[tuple[str, str, str]] = set()

    for plugin_id, plugin in plugins.items():
        if isinstance(plugin, PluginBase):
            found = _scan_plugin_instance(plugin_id, plugin)
        elif isinstance(plugin, types.ModuleType):
            found = _scan_plugin_module(plugin_id, plugin)
        else:
            continue
        for entry in found:
            key = (entry.plugin_id, entry.path_template, entry.method)
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)

    entries.sort(key=lambda e: (e.plugin_id, e.path_template, e.method))
    return entries


def scan_loaded_engine(engine: Any) -> list[CommandEntry]:
    """Convenience wrapper over an object exposing ``_instances``.

    ``PluginEngine._instances`` maps plugin_id → class-based PluginBase
    instance. Sandbox (subprocess) plugins expose no route metadata in the
    parent process — they are skipped by design (routes stay manifest-only
    there, but trusted built-ins are all class-based).
    """
    instances = getattr(engine, "_instances", None)
    if not isinstance(instances, dict):
        return []
    return scan_all_routes(instances)
