"""
Vigile — LegacyPluginWrapper

Adapter that wraps old ``register(pm)``-style plugins so they work with the
Sprint 9 PluginEngine.

The wrapper:
1. Imports the legacy module (avoiding double-import via ``sys.modules``).
2. Intercepts ``register()`` calls via a ``_FakePluginManager`` that
   accumulates ``(hook_name, fn)`` tuples.
3. On activation, subscribes those tuples to the new HookBus.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from collections.abc import Callable
from typing import Any

from master.core.plugin_base import PluginBase, PluginContext

logger = logging.getLogger(__name__)


class _FakePluginManager:
    """Captures register() calls from legacy plugins.

    Instead of actually registering hooks, this stores them so the
    wrapper can replay them on the new HookBus at activation time.
    """

    def __init__(self, plugin_id: str) -> None:
        self.plugin_id = plugin_id
        self._captured: list[tuple[str, Callable]] = []

    def register(self, hook_name: str, fn: Callable, **kwargs: Any) -> None:
        self._captured.append((hook_name, fn))

    def unregister(self, hook_name: str, plugin_name: str | None = None) -> int:
        before = len(self._captured)
        self._captured = [
            (hn, fn) for hn, fn in self._captured
            if hn != hook_name or (plugin_name is not None and plugin_name != self.plugin_id)
        ]
        return before - len(self._captured)

    @property
    def captured(self) -> list[tuple[str, Callable]]:
        return list(self._captured)


class LegacyPluginBase(PluginBase):
    """PluginBase subclass that wraps a legacy ``register(pm)`` module.

    The legacy module is imported, its ``register()`` is called with a
    ``_FakePluginManager``, and the captured hooks are replayed on the
    new HookBus at activation time.
    """

    plugin_id: str = ""

    def __init__(
        self,
        ctx: PluginContext,
        module: Any,
        captured: list[tuple[str, Callable]],
    ) -> None:
        super().__init__(ctx)
        self._legacy_module = module
        self._captured = captured
        # Populate routes/hooks/scheduled from captured hooks
        existing_hook_verbs = {h["verb"] for h in self.hooks}
        for hook_name, fn in captured:
            if hook_name not in existing_hook_verbs:
                self.hooks.append({"verb": hook_name, "method_name": fn.__name__})


def wrap_legacy_plugin(plugin_id: str, file_path: str) -> LegacyPluginBase | None:
    """Wrap a legacy plugin file into a ``LegacyPluginBase``.

    Args:
        plugin_id: The plugin's public identifier.
        file_path: Absolute path to the plugin's ``.py`` file.

    Returns:
        A ``LegacyPluginBase`` instance if successful, ``None`` on failure.
    """
    if not os.path.isfile(file_path):
        logger.error("LegacyWrapper: file not found: %s", file_path)
        return None

    module_name = f"_legacy_plugin_{plugin_id}"

    # Avoid double import
    if module_name in sys.modules:
        module = sys.modules[module_name]
    else:
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not load spec for {file_path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as exc:
            logger.error(
                "LegacyWrapper: failed to import '%s' from %s: %s",
                plugin_id,
                file_path,
                exc,
            )
            return None

    if not hasattr(module, "register"):
        logger.warning(
            "LegacyWrapper: '%s' has no register() function",
            plugin_id,
        )
        return None

    # Capture register() calls
    fake_pm = _FakePluginManager(plugin_id)
    try:
        module.register(fake_pm)
    except Exception as exc:
        logger.error(
            "LegacyWrapper: register() failed for '%s': %s",
            plugin_id,
            exc,
        )
        return None

    # Build a minimal PluginContext
    ctx = PluginContext(
        plugin_id=plugin_id,
        config={},
        db=None,
    )

    instance = LegacyPluginBase(
        ctx=ctx,
        module=module,
        captured=fake_pm.captured,
    )
    instance.plugin_id = plugin_id

    logger.info(
        "LegacyWrapper: wrapped '%s' with %d captured hooks",
        plugin_id,
        len(fake_pm.captured),
    )
    return instance
