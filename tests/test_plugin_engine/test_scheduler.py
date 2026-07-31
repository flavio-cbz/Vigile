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

    @pytest.mark.asyncio
    async def test_no_cumulative_drift(self, monkeypatch):
        """Absolute-tick scheduling: each cycle ≈ interval, not interval + handler_time."""
        import time as _time

        scheduler = Scheduler()
        interval = 0.1
        handler_work = 0.03
        num_cycles = 5

        class WorkPlugin:
            def tick(self):
                _time.sleep(handler_work)

        instance = WorkPlugin()

        recorded_sleeps = []
        _original_sleep = asyncio.sleep

        async def _recording_sleep(duration):
            recorded_sleeps.append(duration)
            await _original_sleep(duration)

        monkeypatch.setattr(asyncio, "sleep", _recording_sleep)

        scheduler.start(
            "p1",
            [{"name": "tick", "interval_secs": interval, "handler": "tick"}],
            instance,
        )

        await asyncio.sleep(interval * (num_cycles + 1) + 0.15)
        await scheduler.stop("p1")

        # Filter: only scheduler sleeps are < 2*interval; the test's own
        # await asyncio.sleep(...) and stop internals are much larger.
        # Skip the first scheduler sleep (next_tick init + first increment).
        scheduler_sleeps = [s for s in recorded_sleeps if s < interval * 2][1:]
        assert len(scheduler_sleeps) >= num_cycles - 1

        expected_sleep = interval - handler_work
        tolerance = 0.03

        for i, s in enumerate(scheduler_sleeps[: num_cycles - 1]):
            assert expected_sleep - tolerance <= s <= interval + tolerance, (
                f"Cycle {i + 1}: sleep {s:.4f} not in "
                f"[{expected_sleep - tolerance:.4f}, {interval + tolerance:.4f}]"
            )

        # No cumulative drift: last sleep ≈ first sleep
        if len(scheduler_sleeps) >= 2:
            assert abs(scheduler_sleeps[-1] - scheduler_sleeps[0]) < tolerance * 3, (
                f"Cumulative drift: first={scheduler_sleeps[0]:.4f}, "
                f"last={scheduler_sleeps[-1]:.4f}"
            )
