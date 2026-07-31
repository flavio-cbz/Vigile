from __future__ import annotations

import asyncio
import sys

import pytest

from master.core.hook_bus import HookBus


class TestHookBusSync:
    def test_call_no_hooks(self):
        bus = HookBus()
        assert bus.call("nonexistent") == []

    def test_call_single(self):
        bus = HookBus()

        def handler(**kw):
            return 42

        bus.register("test", handler)
        assert bus.call("test") == [42]

    def test_call_skips_async(self):
        bus = HookBus()

        async def async_handler(**kw):
            return 99

        bus.register("test", async_handler)
        assert bus.call("test") == []

    def test_call_collects_results(self):
        bus = HookBus()

        def h1(**kw):
            return "a"

        def h2(**kw):
            return "b"

        bus.register("test", h1)
        bus.register("test", h2)
        assert bus.call("test") == ["a", "b"]

    def test_call_skips_none(self):
        bus = HookBus()

        def h1(**kw):
            return None

        def h2(**kw):
            return "val"

        bus.register("test", h1)
        bus.register("test", h2)
        assert bus.call("test") == ["val"]

    def test_call_exception_isolation(self):
        bus = HookBus()

        def failing(**kw):
            raise ValueError("boom")

        def working(**kw):
            return "ok"

        bus.register("test", failing)
        bus.register("test", working)
        assert bus.call("test") == ["ok"]

    def test_call_first_returns_first(self):
        bus = HookBus()

        def h1(**kw):
            return "first"

        def h2(**kw):
            return "second"

        bus.register("test", h1)
        bus.register("test", h2)
        assert bus.call_first("test") == "first"

    def test_call_first_no_match(self):
        bus = HookBus()
        assert bus.call_first("test") is None

    def test_call_first_skips_async(self):
        bus = HookBus()

        async def a(**kw):
            return "async"

        def sync_fn(**kw):
            return "sync"

        bus.register("test", a)
        bus.register("test", sync_fn)
        assert bus.call_first("test") == "sync"


class TestHookBusAsync:
    @pytest.mark.asyncio
    async def test_async_call_no_hooks(self):
        bus = HookBus()
        assert await bus.async_call("nonexistent") == []

    @pytest.mark.asyncio
    async def test_async_call_async_hook(self):
        bus = HookBus()

        async def handler(**kw):
            return 42

        bus.register("test", handler)
        results = await bus.async_call("test")
        assert len(results) == 1
        assert results[0]["success"] is True
        assert results[0]["result"] == 42
        assert results[0]["error"] is None
        assert results[0]["plugin_name"] == "anonymous"

    @pytest.mark.asyncio
    async def test_async_call_sync_hook(self):
        bus = HookBus()

        def handler(**kw):
            return "sync_val"

        bus.register("test", handler)
        results = await bus.async_call("test")
        assert len(results) == 1
        assert results[0]["success"] is True
        assert results[0]["result"] == "sync_val"
        assert results[0]["error"] is None

    @pytest.mark.asyncio
    async def test_async_call_collects_all(self):
        bus = HookBus()

        async def a(**kw):
            return 1

        async def b(**kw):
            return 2

        bus.register("test", a)
        bus.register("test", b)
        results = await bus.async_call("test")
        assert len(results) == 2
        assert {r["result"] for r in results if r["success"]} == {1, 2}

    @pytest.mark.asyncio
    async def test_async_call_exception_isolation(self):
        bus = HookBus()

        async def failing(**kw):
            raise ValueError("boom")

        async def working(**kw):
            return "ok"

        bus.register("test", failing)
        bus.register("test", working)
        results = await bus.async_call("test")
        # Both hooks are present in results — one failed, one succeeded
        assert len(results) == 2
        failed = [r for r in results if not r["success"]]
        succeeded = [r for r in results if r["success"]]
        assert len(failed) == 1
        assert "boom" in failed[0]["error"]
        assert len(succeeded) == 1
        assert succeeded[0]["result"] == "ok"

    @pytest.mark.asyncio
    async def test_async_call_first(self):
        bus = HookBus()

        async def a(**kw):
            return "a"

        async def b(**kw):
            return "b"

        bus.register("test", a)
        bus.register("test", b)
        result = await bus.async_call_first("test")
        assert result in ("a", "b")

    @pytest.mark.asyncio
    async def test_async_call_first_no_hooks(self):
        bus = HookBus()
        assert await bus.async_call_first("nonexistent") is None

    @pytest.mark.asyncio
    async def test_systemexit_in_async_hook(self):
        bus = HookBus()

        async def suicide(**kw):
            raise SystemExit(1)

        async def survivor(**kw):
            return "alive"

        bus.register("test", suicide)
        bus.register("test", survivor)
        results = await bus.async_call("test")
        assert len(results) == 2
        failed = [r for r in results if not r["success"]]
        succeeded = [r for r in results if r["success"]]
        assert len(failed) == 1
        assert len(succeeded) == 1
        assert succeeded[0]["result"] == "alive"


class TestHookBusRegistration:
    def test_register_and_unregister(self):
        bus = HookBus()

        def h(**kw):
            pass

        bus.register("test", h, plugin_name="p1")
        assert bus.has_hook("test")

        removed = bus.unregister("test", "p1")
        assert removed == 1
        assert not bus.has_hook("test")

    def test_unregister_removes_cleanup_empty(self):
        bus = HookBus()

        def h(**kw):
            pass

        bus.register("test", h, plugin_name="p1")
        bus.unregister("test", "p1")
        assert not bus.has_hook("test")
        assert "test" not in bus._hooks

    def test_unregister_nonexistent(self):
        bus = HookBus()
        assert bus.unregister("nonexistent", "p1") == 0

    def test_get_hooks(self):
        bus = HookBus()

        def h1(**kw):
            pass

        def h2(**kw):
            pass

        bus.register("hook_a", h1, plugin_name="p1")
        bus.register("hook_b", h2, plugin_name="p2")

        hooks = bus.get_hooks()
        assert "hook_a" in hooks
        assert "hook_b" in hooks
        assert "p1" in hooks["hook_a"]
        assert "p2" in hooks["hook_b"]

    def test_multiple_handlers_per_hook(self):
        bus = HookBus()

        def h1(**kw):
            return 1

        def h2(**kw):
            return 2

        bus.register("test", h1, plugin_name="p1")
        bus.register("test", h2, plugin_name="p2")
        assert bus.call("test") == [1, 2]

    def test_has_hook_false_on_empty(self):
        bus = HookBus()
        assert not bus.has_hook("anything")


class TestHookBusTimeout:
    def test_custom_default_timeout(self):
        bus = HookBus(default_timeout=5.0)
        assert bus._default_timeout == 5.0

    def test_default_timeout_is_30(self):
        bus = HookBus()
        assert bus._default_timeout == 30.0

    @pytest.mark.asyncio
    async def test_async_call_uses_default_timeout(self):
        """async_call uses self._default_timeout when no per-call override."""
        bus = HookBus(default_timeout=0.1)

        async def slow(**kw):
            await asyncio.sleep(1.0)

        bus.register("test", slow)
        results = await bus.async_call("test")
        assert len(results) == 1
        assert results[0]["success"] is False
        assert "Timeout" in results[0]["error"]

    @pytest.mark.asyncio
    async def test_async_call_per_call_timeout_override(self):
        """async_call accepts a per-call timeout that overrides the default."""
        bus = HookBus(default_timeout=10.0)

        async def slow(**kw):
            await asyncio.sleep(1.0)

        bus.register("test", slow)
        results = await bus.async_call("test", timeout=0.1)
        assert len(results) == 1
        assert results[0]["success"] is False
        assert "0.1" in results[0]["error"]

    @pytest.mark.asyncio
    async def test_async_call_first_timeout_override(self):
        """async_call_first passes timeout through to async_call."""
        bus = HookBus(default_timeout=10.0)

        async def slow(**kw):
            await asyncio.sleep(1.0)

        bus.register("test", slow)
        result = await bus.async_call_first("test", timeout=0.1)
        assert result is None


class TestHookBusDrain:
    @pytest.mark.asyncio
    async def test_wait_for_drain_no_inflight(self):
        """wait_for_drain returns True immediately when no hooks are in-flight."""
        bus = HookBus()
        assert await bus.wait_for_drain("plugin_a") is True

    @pytest.mark.asyncio
    async def test_wait_for_drain_waits_for_completion(self):
        """wait_for_drain blocks until in-flight hooks complete."""
        bus = HookBus(default_timeout=10.0)
        done = asyncio.Event()

        async def slow_hook(**kw):
            await asyncio.sleep(0.3)
            done.set()

        bus.register("test", slow_hook, plugin_name="p1")
        task = asyncio.create_task(bus.async_call("test"))
        await asyncio.sleep(0.05)

        drain_task = asyncio.create_task(bus.wait_for_drain("p1", timeout=5.0))
        await asyncio.sleep(0.05)
        assert not drain_task.done()

        await asyncio.gather(task, drain_task)
        assert done.is_set()
        assert drain_task.result() is True

    @pytest.mark.asyncio
    async def test_wait_for_drain_timeout(self):
        """wait_for_drain returns False when timeout expires."""
        bus = HookBus(default_timeout=10.0)
        drain_started = asyncio.Event()

        async def slow_hook(**kw):
            await asyncio.sleep(2.0)

        bus.register("test", slow_hook, plugin_name="p1")
        task = asyncio.create_task(bus.async_call("test"))
        await asyncio.sleep(0.05)

        result = await bus.wait_for_drain("p1", timeout=0.2)
        assert result is False

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestHookBusMetrics:
    def test_get_metrics_empty(self):
        bus = HookBus()
        assert bus.get_metrics() == {}

    def test_call_records_success(self):
        bus = HookBus()

        def handler(**kw):
            return 42

        bus.register("test", handler, plugin_name="p1")
        bus.call("test")

        metrics = bus.get_metrics()
        assert "test:p1" in metrics
        assert metrics["test:p1"]["invocations"] == 1
        assert metrics["test:p1"]["errors"] == 0
        assert metrics["test:p1"]["avg_duration"] > 0

    def test_call_records_error(self):
        bus = HookBus()

        def failing(**kw):
            raise ValueError("boom")

        bus.register("test", failing, plugin_name="p1")
        bus.call("test")

        metrics = bus.get_metrics()
        assert metrics["test:p1"]["invocations"] == 1
        assert metrics["test:p1"]["errors"] == 1

    def test_call_first_records_metrics(self):
        bus = HookBus()

        def h1(**kw):
            return None

        def h2(**kw):
            return "val"

        bus.register("test", h1, plugin_name="p1")
        bus.register("test", h2, plugin_name="p2")
        bus.call_first("test")

        metrics = bus.get_metrics()
        assert metrics["test:p1"]["invocations"] == 1
        assert metrics["test:p1"]["errors"] == 0
        assert metrics["test:p2"]["invocations"] == 1
        assert metrics["test:p2"]["errors"] == 0

    @pytest.mark.asyncio
    async def test_async_call_records_success(self):
        bus = HookBus()

        async def handler(**kw):
            return 42

        bus.register("test", handler, plugin_name="p1")
        await bus.async_call("test")

        metrics = bus.get_metrics()
        assert metrics["test:p1"]["invocations"] == 1
        assert metrics["test:p1"]["errors"] == 0
        assert metrics["test:p1"]["avg_duration"] > 0

    @pytest.mark.asyncio
    async def test_async_call_records_error(self):
        bus = HookBus()

        async def failing(**kw):
            raise ValueError("boom")

        bus.register("test", failing, plugin_name="p1")
        await bus.async_call("test")

        metrics = bus.get_metrics()
        assert metrics["test:p1"]["invocations"] == 1
        assert metrics["test:p1"]["errors"] == 1
