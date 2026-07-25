from __future__ import annotations

import asyncio
import time

import pytest

from master.core.node_manager import NodeManager


@pytest.mark.asyncio
async def test_intent_gc_respects_default_max_age():
    """Intent aged between old hardcoded 120s and new default 300s survives cleanup."""
    nm = NodeManager()
    nm._default_intent_max_age = 300.0

    loop = asyncio.get_running_loop()
    f1 = loop.create_future()
    f2 = loop.create_future()

    nm._pending_intents["recent"] = f1
    nm._pending_intents["medium"] = f2
    # recent intent: just created (age ≈ 0)
    nm._intent_created_at["recent"] = time.time()
    # medium intent: 150s old — would be killed by old 120.0 default
    nm._intent_created_at["medium"] = time.time() - 150.0

    cleaned = nm._cleanup_stale_intents()
    # medium is 150s old < 300s default, so it should survive
    assert cleaned == 0
    assert "recent" in nm._pending_intents
    assert "medium" in nm._pending_intents
    assert not f1.cancelled()
    assert not f2.cancelled()


@pytest.mark.asyncio
async def test_intent_gc_cleans_old_intents():
    """Intent older than default_max_age is cleaned up."""
    nm = NodeManager()
    nm._default_intent_max_age = 30.0

    loop = asyncio.get_running_loop()
    f1 = loop.create_future()

    nm._pending_intents["old"] = f1
    nm._intent_created_at["old"] = time.time() - 60.0  # 60s > 30s default

    cleaned = nm._cleanup_stale_intents()
    assert cleaned == 1
    assert "old" not in nm._pending_intents
    assert f1.cancelled()


@pytest.mark.asyncio
async def test_intent_gc_per_intent_max_age():
    """Per-intent intent_max_age overrides the default."""
    nm = NodeManager()
    nm._default_intent_max_age = 300.0

    loop = asyncio.get_running_loop()
    f1 = loop.create_future()
    f2 = loop.create_future()

    nm._pending_intents["short"] = f1
    nm._pending_intents["long"] = f2
    nm._intent_created_at["short"] = time.time() - 30.0
    nm._intent_created_at["long"] = time.time() - 30.0
    # Override max_age for short intent only
    nm._intent_max_age["short"] = 10.0  # 30s > 10s → stale
    # long intent uses default 300s → survives

    cleaned = nm._cleanup_stale_intents()
    assert cleaned == 1
    assert "short" not in nm._pending_intents
    assert "long" in nm._pending_intents
    assert f1.cancelled()
    assert not f2.cancelled()


@pytest.mark.asyncio
async def test_intent_gc_cleans_done_intents():
    """Done intents are always cleaned regardless of age."""
    nm = NodeManager()
    nm._default_intent_max_age = 300.0

    loop = asyncio.get_running_loop()
    f1 = loop.create_future()
    f1.set_result(True)

    nm._pending_intents["done"] = f1
    nm._intent_created_at["done"] = time.time()

    cleaned = nm._cleanup_stale_intents()
    assert cleaned == 1
    assert "done" not in nm._pending_intents


@pytest.mark.asyncio
async def test_send_intent_stores_per_intent_max_age():
    """send_intent with intent_max_age stores it in _intent_max_age dict."""
    nm = NodeManager()
    ws = _make_dummy_ws()
    await nm.register_connection("test-node", ws)

    intent = {"action": "PING"}
    task = asyncio.create_task(
        nm.send_intent("test-node", intent, timeout=1.0, intent_max_age=60.0)
    )
    await asyncio.sleep(0.05)

    # Extract intent_id from sent message
    intent_id = ws.sent_messages[0]["intent_id"]
    assert intent_id in nm._intent_max_age
    assert nm._intent_max_age[intent_id] == 60.0

    # Resolve so the task doesn't hang
    await nm.resolve_intent(intent_id, {"success": True})
    await task

    # After resolution, _intent_max_age should be cleaned
    assert intent_id not in nm._intent_max_age


class _DummyWS:
    def __init__(self):
        self.sent_messages = []
        self.closed = False

    async def send_json(self, data: dict):
        self.sent_messages.append(data)

    async def close(self, code: int = 1000, reason: str = ""):
        self.closed = True


def _make_dummy_ws():
    return _DummyWS()
