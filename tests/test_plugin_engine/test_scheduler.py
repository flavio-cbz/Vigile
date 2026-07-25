from __future__ import annotations

import asyncio

import pytest

from master.core.scheduler import Scheduler


class TestScheduler:
    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        scheduler = Scheduler()
        calls = []

        class FakePlugin:
            async def tick(self):
                calls.append("tick")

        instance = FakePlugin()
        scheduler.start("p1", [{"name": "tick", "interval_secs": 0.05, "handler": "tick"}], instance)

        await asyncio.sleep(0.12)
        await scheduler.stop("p1")

        assert len(calls) >= 2

    @pytest.mark.asyncio
    async def test_stop_no_tasks(self):
        scheduler = Scheduler()
        await scheduler.stop("nonexistent")

    @pytest.mark.asyncio
    async def test_shutdown_cancels_all(self):
        scheduler = Scheduler()
        calls = []

        class FakePlugin:
            async def tick(self):
                calls.append("tick")

        instance = FakePlugin()
        scheduler.start("p1", [{"name": "tick", "interval_secs": 0.05, "handler": "tick"}], instance)
        scheduler.start("p2", [{"name": "tock", "interval_secs": 0.05, "handler": "tick"}], instance)

        await asyncio.sleep(0.1)
        await scheduler.shutdown()

        assert not scheduler.has_tasks("p1")
        assert not scheduler.has_tasks("p2")

    @pytest.mark.asyncio
    async def test_has_tasks(self):
        scheduler = Scheduler()

        class FakePlugin:
            async def tick(self):
                pass

        instance = FakePlugin()
        assert not scheduler.has_tasks("p1")

        scheduler.start("p1", [{"name": "tick", "interval_secs": 60, "handler": "tick"}], instance)
        assert scheduler.has_tasks("p1")

        await scheduler.stop("p1")
        assert not scheduler.has_tasks("p1")

    @pytest.mark.asyncio
    async def test_active_callbacks_tracking(self):
        scheduler = Scheduler()
        event = asyncio.Event()

        class FakePlugin:
            async def slow(self):
                event.set()
                await asyncio.sleep(0.5)

        instance = FakePlugin()
        scheduler.start("p1", [{"name": "slow", "interval_secs": 60, "handler": "slow"}], instance)

        await event.wait()
        await asyncio.sleep(0.05)

        assert scheduler.active_callbacks("p1") >= 1
        await scheduler.stop("p1")

    @pytest.mark.asyncio
    async def test_sync_handler(self):
        scheduler = Scheduler()
        calls = []

        class FakePlugin:
            def tick(self):
                calls.append("tick")

        instance = FakePlugin()
        scheduler.start("p1", [{"name": "tick", "interval_secs": 0.05, "handler": "tick"}], instance)

        await asyncio.sleep(0.12)
        await scheduler.stop("p1")

        assert len(calls) >= 2

    @pytest.mark.asyncio
    async def test_handler_not_found(self):
        scheduler = Scheduler()

        class FakePlugin:
            pass

        instance = FakePlugin()
        scheduler.start("p1", [{"name": "missing", "interval_secs": 0.05, "handler": "nonexistent"}], instance)

        await asyncio.sleep(0.1)
        await scheduler.stop("p1")

    @pytest.mark.asyncio
    async def test_stop_timeout(self):
        scheduler = Scheduler()

        class FakePlugin:
            async def hang(self):
                await asyncio.sleep(999)

        instance = FakePlugin()
        scheduler.start("p1", [{"name": "hang", "interval_secs": 60, "handler": "hang"}], instance)

        await asyncio.sleep(0.05)
        await scheduler.stop("p1")

        assert not scheduler.has_tasks("p1")
