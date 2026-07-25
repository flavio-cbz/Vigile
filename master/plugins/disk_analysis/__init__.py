"""Disk Analysis plugin — visual treemap of node filesystem usage."""
from __future__ import annotations

from master.core.plugin_base import PluginBase


class DiskAnalysisPlugin(PluginBase):
    plugin_id = "disk_analysis"

    async def on_start(self) -> None:
        pass

    async def on_stop(self) -> None:
        pass
