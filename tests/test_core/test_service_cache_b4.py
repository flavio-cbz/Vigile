"""B4 — Service cache & collector tests.

Covers:
- test_service_cache_stale (cold start)
- test_service_collector_partial_failure (1 node timeout does not wipe cache)
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from master.core.node_manager import NodeState, node_manager
from master.db.service_cache import get_cached_services, is_stale, set_cached_services
from master.core.jobs.service_collector import collect_services_for_all_nodes


SERVICES_A = json.dumps([{"name": "ssh.service", "state": "active", "status": "running"}])
SERVICES_B = json.dumps([{"name": "nginx.service", "state": "active", "status": "running"}])


async def _setup_node(db, name="b4-node"):
    nid = await node_manager.create_node(db, name=name)
    await node_manager.transition_state(db, nid, NodeState.ENROLLING)
    await node_manager.transition_state(db, nid, NodeState.UNCONFIGURED)
    await node_manager.transition_state(db, nid, NodeState.CONNECTED)
    return nid


@pytest.mark.asyncio
async def test_service_cache_stale(db):
    """Cold start: no cache → stale, then after write → fresh, then after TTL → stale."""
    nid = await _setup_node(db, "cache-stale")
    j, ts = await get_cached_services(db, nid)
    assert j is None
    assert ts is None
    assert is_stale(ts) is True

    now = time.time()
    await set_cached_services(db, nid, SERVICES_A, now)
    j2, ts2 = await get_cached_services(db, nid)
    assert j2 == SERVICES_A
    assert ts2 is not None
    assert abs(ts2 - now) < 2
    assert is_stale(ts2) is False
    # Simulate TTL expiry (300s + 10)
    assert is_stale(ts2, now=ts2 + 400) is True


@pytest.mark.asyncio
async def test_service_cache_only_if_success_guards(db):
    """H7bis: set_cached_services n'écrit QUE si success:true && parsed!=None.
    Ici on teste que le cache existant est préservé si on n'appelle pas set sur échec."""
    nid = await _setup_node(db, "cache-guard")
    now = time.time()
    await set_cached_services(db, nid, SERVICES_A, now)
    j1, _ = await get_cached_services(db, nid)
    assert j1 is not None and json.loads(j1)[0]["name"] == "ssh.service"
    # Simulate collector receiving success:false → do NOT call set
    # Cache must stay as before
    j2, ts2 = await get_cached_services(db, nid)
    assert j2 == SERVICES_A


@pytest.mark.asyncio
async def test_service_collector_partial_failure(db, monkeypatch):
    """1 node timeout does not wipe cache of the other node. Uses Semaphore(5) + return_exceptions."""
    nid_ok = await _setup_node(db, "collector-ok")
    nid_fail = await _setup_node(db, "collector-fail")

    # Pre-seed both with caches
    now = time.time()
    await set_cached_services(db, nid_ok, SERVICES_A, now)
    await set_cached_services(db, nid_fail, SERVICES_A, now)

    # Prepare connected ids
    monkeypatch.setattr(node_manager, "connected_node_ids", lambda: [nid_ok, nid_fail])
    # Also is_connected must return True for port.query guard
    async def _is_connected(nid):
        return True
    monkeypatch.setattr(node_manager, "is_connected", _is_connected)

    # Mock _send_intent to succeed for ok, timeout for fail
    orig_send = node_manager._send_intent

    async def fake_send(node_id, intent, *, timeout=None, intent_max_age=None):
        if node_id == nid_ok:
            return {"success": True, "output": SERVICES_B}
        if node_id == nid_fail:
            raise TimeoutError("Worker did not respond")
        return {"success": False, "error": "unknown"}

    monkeypatch.setattr(node_manager, "_send_intent", fake_send)

    result = await collect_services_for_all_nodes(db, node_manager)
    # One collected, one error
    assert result["collected"] == 1
    assert any(nid_fail in e for e in result["errors"]) or len(result["errors"]) == 1

    # nid_ok cache must have been updated to SERVICES_B
    j_ok, _ = await get_cached_services(db, nid_ok)
    assert j_ok is not None and json.loads(j_ok)[0]["name"] == "nginx.service"

    # nid_fail cache must be preserved (not wiped to empty)
    j_fail, _ = await get_cached_services(db, nid_fail)
    assert j_fail == SERVICES_A


@pytest.mark.asyncio
async def test_set_cached_services_rejects_poison(db):
    """Vérifie que set_cached_services rejette bien les valeurs empoisonnées
    (None, non-str, vide, whitespace, null, invalid JSON, dict non-liste, etc.)."""
    nid = await _setup_node(db, "poison-node")

    # 1. On an initially empty node, poisoned inputs must not write anything
    poison_values = [
        None,
        "",
        "   ",
        "null",
        "invalid json {",
        json.dumps({"error": "should be a list"}),
        json.dumps(12345),
        json.dumps("plain string not a list"),
    ]
    for poison in poison_values:
        await set_cached_services(db, nid, poison, time.time())  # type: ignore[arg-type]
        j, ts = await get_cached_services(db, nid)
        assert j is None, f"Expected None for poison {poison!r}, got {j!r}"
        assert ts is None

    # 2. On a node with valid cache, poisoned inputs must not overwrite existing cache
    now = time.time()
    await set_cached_services(db, nid, SERVICES_A, now)
    j_valid, ts_valid = await get_cached_services(db, nid)
    assert j_valid == SERVICES_A
    assert ts_valid == now

    for poison in poison_values:
        await set_cached_services(db, nid, poison, time.time() + 100)  # type: ignore[arg-type]
        j_after, ts_after = await get_cached_services(db, nid)
        assert j_after == SERVICES_A, f"Cache overwritten by poison {poison!r}"
        assert ts_after == now


@pytest.mark.asyncio
async def test_invalidate_cached_services(db):
    """Vérifie que invalidate_cached_services positionne cached_services_at = 0."""
    from master.db.service_cache import invalidate_cached_services

    nid = await _setup_node(db, "inval-node")
    now = time.time()
    await set_cached_services(db, nid, SERVICES_A, now)

    j, ts = await get_cached_services(db, nid)
    assert j == SERVICES_A
    assert is_stale(ts) is False

    await invalidate_cached_services(db, nid)

    j_inval, ts_inval = await get_cached_services(db, nid)
    assert j_inval == SERVICES_A
    assert ts_inval == 0
    assert is_stale(ts_inval) is True

