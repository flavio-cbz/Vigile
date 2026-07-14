"""
Vigile — Scanner

Filesystem plugin discovery for the Sprint 9 Plugin Engine.

Scans a directory for plugin subdirectories containing ``manifest.json``,
validates the manifest against ``PluginManifest``, and triggers
installation or upgrade via the LifecycleManager.

Orphan detection: plugins that are ACTIVE in the DB but have no
corresponding directory are flagged and deactivated.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from master.core.plugin_manifest import PluginManifest

logger = logging.getLogger(__name__)


class ScanResult:
    """Result of a single scan pass."""

    def __init__(self) -> None:
        self.installed: list[str] = []
        self.upgraded: list[str] = []
        self.orphans: list[str] = []
        self.errors: list[tuple[str, str]] = []

    @property
    def success_count(self) -> int:
        return len(self.installed) + len(self.upgraded)

    @property
    def total_count(self) -> int:
        return self.success_count + len(self.orphans)

    def merge(self, other: ScanResult) -> None:
        self.installed.extend(other.installed)
        self.upgraded.extend(other.upgraded)
        self.orphans.extend(other.orphans)
        self.errors.extend(other.errors)


class Scanner:
    """Filesystem scanner for plugin discovery."""

    def __init__(
        self,
        plugins_dir: str = "master/plugins",
        lifecycle: Any = None,
        db: Any = None,
    ) -> None:
        self._plugins_dir = plugins_dir
        self._lifecycle = lifecycle
        self._db = db
        self._scan_lock = asyncio.Lock()
        # plugin_id -> PluginManifest cache
        self._discovered_manifests: dict[str, PluginManifest] = {}

    def set_lifecycle(self, lifecycle: Any) -> None:
        self._lifecycle = lifecycle

    def set_db(self, db: Any) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    async def scan(self, plugins_dir: str | None = None) -> ScanResult:
        """Scan *plugins_dir* for plugin directories with ``manifest.json``.

        Returns a ``ScanResult`` summarising what was installed, upgraded,
        and detected as orphaned.
        """
        async with self._scan_lock:
            result = ScanResult()
            directory = plugins_dir or self._plugins_dir

            if not os.path.isdir(directory):
                logger.warning("Scanner: plugins directory not found: %s", directory)
                return result

            discovered: dict[str, PluginManifest] = {}

            for entry in sorted(os.listdir(directory)):
                full_path = os.path.join(directory, entry)
                if os.path.isdir(full_path):
                    manifest_path = os.path.join(full_path, "manifest.json")
                    if not os.path.isfile(manifest_path):
                        continue

                    try:
                        manifest = self._load_manifest(manifest_path)
                        if manifest is None:
                            continue
                        discovered[manifest.id] = manifest
                    except Exception as exc:
                        result.errors.append((entry, str(exc)))
                        logger.error(
                            "Scanner: error loading manifest from '%s': %s",
                            manifest_path,
                            exc,
                        )
                elif entry.endswith(".py") and not entry.startswith("_"):
                    try:
                        from master.core.plugin_manager import canonical_plugin_id
                        plugin_id = canonical_plugin_id(entry[:-3])
                        # Create a virtual manifest for legacy flat .py files
                        manifest = PluginManifest(
                            id=plugin_id,
                            name=plugin_id.replace("_", " ").title(),
                            version="1.0.0",
                            description="Legacy Python plugin.",
                        )
                        discovered[manifest.id] = manifest
                    except Exception as exc:
                        result.errors.append((entry, str(exc)))
                        logger.error(
                            "Scanner: error wrapping legacy plugin '%s': %s",
                            entry,
                            exc,
                        )

            self._discovered_manifests.update(discovered)

            # Compare with lifecycle state
            if self._lifecycle is not None:
                await self._reconcile(discovered, result)

            return result

    def _load_manifest(self, manifest_path: str) -> PluginManifest | None:
        """Load and validate a ``manifest.json`` file."""
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        manifest = PluginManifest(**data)

        # Check min_master_version if set
        # (actual version comparison omitted — caller can check)
        if manifest.min_master_version:
            logger.info(
                "Scanner: manifest '%s' requires master >= %s",
                manifest.id,
                manifest.min_master_version,
            )

        return manifest

    async def _reconcile(
        self,
        discovered: dict[str, PluginManifest],
        result: ScanResult,
    ) -> None:
        """Compare discovered manifests against lifecycle state.

        Installs new plugins, upgrades existing ones, and detects orphans.
        """
        lifecycle = self._lifecycle
        if lifecycle is None:
            return

        for plugin_id, manifest in discovered.items():
            current_state = lifecycle.get_state(plugin_id)

            if current_state == "DECOUVERT":
                await lifecycle.transition(plugin_id, "INSTALLED")
                result.installed.append(plugin_id)
                logger.info("Scanner: installed plugin '%s' v%s", plugin_id, manifest.version)
            else:
                result.upgraded.append(plugin_id)

        # Orphan detection: plugins in INSTALLED or ACTIVE but not discovered
        current_states = lifecycle.get_all_states()
        for plugin_id, state in current_states.items():
            if state not in ("INSTALLED", "ACTIVE") or plugin_id in discovered:
                continue

            # Skip legacy .py plugins (loaded via sandbox subprocess) —
            # they don't have manifest.json directories so the scanner
            # would incorrectly flag them as orphans.
            if self._is_legacy_py_plugin(plugin_id):
                continue

            result.orphans.append(plugin_id)
            logger.warning(
                "Scanner: orphan plugin '%s' (state=%s) — deactivating",
                plugin_id,
                state,
            )
            if state == "ACTIVE":
                await lifecycle.transition(plugin_id, "DEACTIVATED")

    # ------------------------------------------------------------------
    # Manifest retrieval
    # ------------------------------------------------------------------

    def get_manifest(self, plugin_id: str) -> PluginManifest | None:
        """Return the cached manifest for *plugin_id*, if any."""
        return self._discovered_manifests.get(plugin_id)

    def get_all_manifests(self) -> dict[str, PluginManifest]:
        """Return all discovered manifests."""
        return dict(self._discovered_manifests)

    def _is_legacy_py_plugin(self, plugin_id: str) -> bool:
        """Check if *plugin_id* corresponds to a legacy ``.py`` plugin file."""
        # Reverse the canonical mapping: metrics -> metrics_plugin, etc.
        # _BUILTIN_PLUGIN_ID_TO_FILE lives in plugin_manager
        from master.core.plugin_manager import plugin_file_stem

        stem = plugin_file_stem(plugin_id)
        plugin_path = os.path.join(self._plugins_dir, f"{stem}.py")
        return os.path.isfile(plugin_path)

    def get_plugins_dir(self) -> str:
        return self._plugins_dir
