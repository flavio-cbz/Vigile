"""
Vigile — Plugin Engine & Lifecycle Manager

Central orchestrator for the Sprint 9 plugin system. Owns the state machine
(LifecycleManager), the four dispatch modes (HookBus), interval tasks
(Scheduler), dynamic route mounting (RouteRegistrar), declarative table
management (DBAuto), and filesystem discovery (Scanner).

States:
    DECOUVERT -> INSTALLED -> ACTIVE -> DEACTIVATED -> UNINSTALL
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from master.core.plugin_base import PluginBase, PluginContext
from master.core.plugin_manifest import PluginManifest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Plugin state constants
# ---------------------------------------------------------------------------

STATE_DECOUVERT = "DECOUVERT"
STATE_INSTALLED = "INSTALLED"
STATE_ACTIVE = "ACTIVE"
STATE_DEACTIVATED = "DEACTIVATED"
STATE_UNINSTALL = "UNINSTALL"

ALL_STATES = frozenset({
    STATE_DECOUVERT, STATE_INSTALLED, STATE_ACTIVE,
    STATE_DEACTIVATED, STATE_UNINSTALL,
})

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    STATE_DECOUVERT: {STATE_INSTALLED},
    STATE_INSTALLED: {STATE_ACTIVE, STATE_UNINSTALL},
    STATE_ACTIVE: {STATE_DEACTIVATED},
    STATE_DEACTIVATED: {STATE_ACTIVE, STATE_UNINSTALL},
    STATE_UNINSTALL: set(),
}


# ---------------------------------------------------------------------------
# LifecycleManager
# ---------------------------------------------------------------------------


class LifecycleError(Exception):
    """Raised on invalid state transitions or lifecycle failures."""


class LifecycleManager:
    """Per-plugin state machine with asyncio.Lock for concurrency safety."""

    def __init__(self) -> None:
        self._states: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._engine: PluginEngine | None = None

    def _lock(self, plugin_id: str) -> asyncio.Lock:
        if plugin_id not in self._locks:
            self._locks[plugin_id] = asyncio.Lock()
        return self._locks[plugin_id]

    def get_state(self, plugin_id: str) -> str:
        return self._states.get(plugin_id, STATE_DECOUVERT)

    def get_all_states(self) -> dict[str, str]:
        return dict(self._states)

    async def transition(
        self, plugin_id: str, target: str, **context: Any
    ) -> None:
        current = self.get_state(plugin_id)
        allowed = _ALLOWED_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise LifecycleError(
                f"Invalid transition {current} -> {target} for plugin '{plugin_id}'"
            )

        async with self._lock(plugin_id):
            if target == STATE_ACTIVE:
                await self._do_activate(plugin_id, context)
            elif target == STATE_DEACTIVATED:
                await self._do_deactivate(plugin_id)
            elif target == STATE_INSTALLED:
                self._states[plugin_id] = STATE_INSTALLED
            elif target == STATE_UNINSTALL:
                await self._do_uninstall(plugin_id)

    async def _do_activate(self, plugin_id: str, context: dict) -> None:
        engine = self._engine
        if engine is None:
            raise LifecycleError("PluginEngine not attached to LifecycleManager")

        manifest: PluginManifest | None = context.get("manifest")
        instance: PluginBase | None = context.get("instance")
        if manifest is None or instance is None:
            raise LifecycleError(
                f"Activation context missing manifest/instance for '{plugin_id}'"
            )

        # Subscribe hooks
        for hook_spec in instance.hooks:
            verb = hook_spec["verb"]
            handler_name = hook_spec["method_name"]
            fn = getattr(instance, handler_name, None)
            if fn is not None:
                engine.hook_bus.register(verb, fn, plugin_name=plugin_id)

        # Start scheduled tasks
        if instance.scheduled:
            engine.scheduler.start(plugin_id, instance.scheduled, instance)

        # Mount routes
        if instance.routes and engine.route_registrar is not None:
            engine.route_registrar.mount(plugin_id, instance.routes, instance)

        self._states[plugin_id] = STATE_ACTIVE

    async def _do_deactivate(self, plugin_id: str) -> None:
        engine = self._engine
        if engine is None:
            raise LifecycleError("PluginEngine not attached to LifecycleManager")

        # Unsubscribe hooks
        for hook_name in list(engine.hook_bus.get_hooks().keys()):
            engine.hook_bus.unregister(hook_name, plugin_id)

        # Stop scheduled tasks
        await engine.scheduler.stop(plugin_id)

        # Unmount routes
        if engine.route_registrar is not None:
            engine.route_registrar.unmount(plugin_id)

        self._states[plugin_id] = STATE_DEACTIVATED

    async def _do_uninstall(self, plugin_id: str) -> None:
        engine = self._engine
        if engine is not None and engine.db_auto is not None:
            manifest = None
            try:
                from master.core.plugin_manifest import PluginManifest
            except ImportError:
                pass
            # Try to get manifest from DB for table cleanup
            plugin_dir = (
                getattr(engine.scanner, "_plugins_dir", None)
                if engine.scanner is not None else None
            )
            if engine.scanner is not None:
                for pid, mf in engine.scanner._discovered_manifests.items():
                    if pid == plugin_id:
                        manifest = mf
                        break
            if manifest is not None and manifest.database:
                engine.db_auto.drop_tables(plugin_id, manifest.database)

        self._states.pop(plugin_id, None)


# ---------------------------------------------------------------------------
# PluginEngine
# ---------------------------------------------------------------------------


class PluginEngine:
    """Central facade for the Sprint 9 plugin system.

    Coordinates LifecycleManager, HookBus, Scheduler, RouteRegistrar,
    DBAuto, and Scanner. Intended as a drop-in superset of the legacy
    PluginManager — old code can continue to reference ``plugin_manager``
    while the engine provides the new lifecycle.
    """

    def __init__(
        self,
        hook_bus: Any = None,
        scheduler: Any = None,
        route_registrar: Any = None,
        db_auto: Any = None,
        scanner: Any = None,
        db: Any = None,
    ) -> None:
        self.lifecycle = LifecycleManager()
        self.lifecycle._engine = self

        self.hook_bus = hook_bus
        self.scheduler = scheduler
        self.route_registrar = route_registrar
        self.db_auto = db_auto
        self.scanner = scanner
        self._db = db

    async def register_hooks_from_instance(
        self, plugin_id: str, instance: PluginBase
    ) -> None:
        """Register a plugin instance's hooks with the hook bus."""
        for hook_spec in instance.hooks:
            verb = hook_spec["verb"]
            handler_name = hook_spec["method_name"]
            fn = getattr(instance, handler_name, None)
            if fn is not None and self.hook_bus is not None:
                self.hook_bus.register(verb, fn, plugin_name=plugin_id)

    async def activate(
        self, plugin_id: str, manifest: PluginManifest, instance: PluginBase
    ) -> None:
        """Activate a plugin: subscribe hooks, start scheduler, mount routes."""
        await self.lifecycle.transition(
            plugin_id,
            STATE_ACTIVE,
            manifest=manifest,
            instance=instance,
        )

    async def deactivate(self, plugin_id: str) -> None:
        """Deactivate a plugin: unsubscribe hooks, stop scheduler, unmount routes."""
        await self.lifecycle.transition(plugin_id, STATE_DEACTIVATED)

    async def install(self, plugin_id: str) -> None:
        """Install a plugin: set state to INSTALLED, create DB tables if needed."""
        await self.lifecycle.transition(plugin_id, STATE_INSTALLED)

    async def uninstall(self, plugin_id: str) -> None:
        """Uninstall a plugin: deactivate first if active, then remove."""
        current = self.lifecycle.get_state(plugin_id)
        if current == STATE_ACTIVE:
            await self.deactivate(plugin_id)
        await self.lifecycle.transition(plugin_id, STATE_UNINSTALL)

    def get_hooks(self) -> dict[str, list[str]]:
        if self.hook_bus is not None:
            return self.hook_bus.get_hooks()
        return {}

    def has_hook(self, hook_name: str) -> bool:
        if self.hook_bus is not None:
            return self.hook_bus.has_hook(hook_name)
        return False

    @property
    def loaded_plugins(self) -> list[str]:
        return [
            pid for pid, state in self.lifecycle.get_all_states().items()
            if state == STATE_ACTIVE
        ]

    async def shutdown(self) -> None:
        """Deactivate all active plugins and shut down the scheduler."""
        for plugin_id, state in list(self.lifecycle.get_all_states().items()):
            if state == STATE_ACTIVE:
                await self.deactivate(plugin_id)
        if self.scheduler is not None:
            await self.scheduler.shutdown()
