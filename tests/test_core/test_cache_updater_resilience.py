from __future__ import annotations

import asyncio
from unittest.mock import patch

import aiosqlite
import pytest

from master.core.node_manager import NodeManager


@pytest.mark.asyncio
async def test_cache_updater_catches_operational_error():
    """Cache updater should catch aiosqlite.OperationalError without crashing."""
    nm = NodeManager()
    event = asyncio.Event()

    async def mock_update():
        event.set()
        raise aiosqlite.OperationalError("database is locked")

    with patch.object(nm, "update_all_nodes_cache", mock_update):
        task = asyncio.create_task(nm._cache_updater(1))
        await asyncio.wait_for(event.wait(), timeout=5.0)
        # Error was raised and caught — task is still alive
        assert not task.done()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_cache_updater_catches_generic_exception():
    """Cache updater should catch generic exceptions without crashing."""
    nm = NodeManager()
    event = asyncio.Event()

    async def mock_update():
        event.set()
        raise RuntimeError("unexpected failure")

    with patch.object(nm, "update_all_nodes_cache", mock_update):
        task = asyncio.create_task(nm._cache_updater(1))
        await asyncio.wait_for(event.wait(), timeout=5.0)
        assert not task.done()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_cache_updater_stops_on_cancelled_error():
    """Cache updater should break cleanly — no CancelledError propagation."""
    nm = NodeManager()

    async def mock_update():
        await asyncio.sleep(0.5)

    with patch.object(nm, "update_all_nodes_cache", mock_update):
        task = asyncio.create_task(nm._cache_updater(9999))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pytest.fail("CancelledError should not propagate")
        # Clean exit proves handler correctly caught CancelledError
