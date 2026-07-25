from __future__ import annotations

import asyncio
import sys

import pytest

from master.core.hook_bus import HookBus


class TestCrashResilience:
    @pytest.mark.asyncio
    async def test_systemexit_in_async_call(self):
        bus = HookBus()

        async def suicide(**kw):
            raise SystemExit(1)

        async def survivor(**kw):
            return "ok"

        bus.register("test", suicide, plugin_name="suicide")
        bus.register("test", survivor, plugin_name="survivor")
        results = await bus.async_call("test")
        assert results == ["ok"]

    @pytest.mark.asyncio
    async def test_keyboardinterrupt_in_async_call(self):
        bus = HookBus()

        async def interrupter(**kw):
            raise KeyboardInterrupt()

        async def survivor(**kw):
            return "ok"

        bus.register("test", interrupter, plugin_name="interrupter")
        bus.register("test", survivor, plugin_name="survivor")
        results = await bus.async_call("test")
        assert results == ["ok"]

    @pytest.mark.asyncio
    async def test_hook_timeout_does_not_block_others(self):
        bus = HookBus()

        async def slow(**kw):
            await asyncio.sleep(999)

        async def fast(**kw):
            return "done"

        bus.register("test", slow, plugin_name="slow")
        bus.register("test", fast, plugin_name="fast")
        results = await asyncio.wait_for(
            bus.async_call("test"), timeout=35.0
        )
        assert results == ["done"]

    def test_exception_in_call_isolation(self):
        bus = HookBus()

        def failing(**kw):
            raise ValueError("boom")

        def ok(**kw):
            return "ok"

        bus.register("test", failing, plugin_name="failing")
        bus.register("test", ok, plugin_name="ok")
        assert bus.call("test") == ["ok"]

    def test_call_first_with_exception(self):
        bus = HookBus()

        def failing(**kw):
            raise ValueError("boom")

        def after(**kw):
            return "after"

        bus.register("test", failing, plugin_name="failing")
        bus.register("test", after, plugin_name="after")
        result = bus.call_first("test")
        assert result == "after"

    @pytest.mark.asyncio
    async def test_baseexception_reraise_blocked(self):
        bus = HookBus()

        class CustomBaseError(BaseException):
            pass

        async def custom_raise(**kw):
            raise CustomBaseError("custom")

        async def ok(**kw):
            return "ok"

        bus.register("test", custom_raise, plugin_name="custom")
        bus.register("test", ok, plugin_name="ok")
        results = await bus.async_call("test")
        assert results == ["ok"]

    @pytest.mark.asyncio
    async def test_concurrent_calls_dont_interfere(self):
        bus = HookBus()
        results = []

        async def slow(**kw):
            await asyncio.sleep(0.1)
            results.append("slow")

        async def fast(**kw):
            results.append("fast")

        bus.register("a", slow, plugin_name="a")
        bus.register("b", fast, plugin_name="b")

        await asyncio.gather(
            bus.async_call("a"),
            bus.async_call("b"),
        )
        assert "fast" in results
        assert "slow" in results