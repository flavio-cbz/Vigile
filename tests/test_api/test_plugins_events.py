"""
Tests for the plugin-invalidation SSE stream (T26 / S4).

Contract (docs/contracts/block-contract-v2.md §8.4 + plan S4/D3):
  - GET /api/plugins/events/stream is EventSource-friendly: auth via
    `?token=<jwt>` (no Authorization header possible), 401 on missing/invalid
    token.
  - Events flow on topic `plugins.invalidated` with payload
    `{plugin_id, boot_id, revision, action}` — the client uses the pair
    (boot_id, revision) as its `since` cursor for /batch and plugin GETs.
  - Replay of the ring buffer on (re)connect — a fresh client synchronizes.
  - S7 permission filter at delivery: `(role >= min_role ∧ p ∈ permissions)`
    for the plugin concerned; admins receive everything; an "unloaded" event
    (manifest gone) is fail-closed to admins only.

Note on test mechanics: the streaming tests drive the route function directly
(no httpx). httpx ASGITransport cannot cancel an infinite SSE app task on early
connection close, so any HTTP-stream test hangs at context exit. Auth failures
(401) return before streaming and are tested over real HTTP.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from master.api import deps
from master.api.plugins_events import stream as stream_route
from master.core.event_bus import event_bus
from master.core.security_manager import SecurityManager


@pytest.fixture
async def sse_client(db):
    from httpx import ASGITransport, AsyncClient

    from master.main import app

    app.dependency_overrides[deps.get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(deps.get_db, None)


@pytest.fixture
def fake_engine(monkeypatch):
    manifests: dict = {}

    def _set(pid: str, permissions) -> None:
        manifests[pid] = SimpleNamespace(permissions=permissions)

    def _remove(pid: str) -> None:
        manifests.pop(pid, None)

    def _engine():
        return SimpleNamespace(get_served_manifest=lambda pid: manifests.get(pid))

    monkeypatch.setattr("master.api.plugins_events._get_engine", _engine)
    return SimpleNamespace(set=_set, remove=_remove)


@pytest.fixture
def fast_keepalive(monkeypatch):
    """Shrink the SSE heartbeat so idle streams emit `: keepalive` immediately."""
    monkeypatch.setattr("master.api.plugins_events._KEEPALIVE_SECONDS", 0.05)


def _token(security: SecurityManager, role: str = "viewer") -> str:
    return security.create_access_token("test-user", "test_user", role)


async def _open_stream(security: SecurityManager, role: str = "viewer"):
    """Return the live body generator of the SSE stream (hermetic, no HTTP)."""
    token = _token(security, role)
    req = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/plugins/events/stream",
            "query_string": b"",
            "headers": [],
            "client": ("test", 1234),
            "server": ("test", 80),
            "scheme": "http",
        },
        receive=lambda: asyncio.sleep(3600),  # never disconnect
    )
    resp = await stream_route(req, token=token, bus=event_bus)
    return resp.body_iterator


async def _collect_data_lines(agen, predicate, timeout: float = 3.0) -> dict:
    """Read SSE data lines until `predicate` matches; raise on stream end/timeout."""

    async def _read():
        async for chunk in agen:
            text = chunk.decode() if isinstance(chunk, bytes) else chunk
            for line in text.splitlines():
                if line.startswith("data: "):
                    payload = json.loads(line[6:])
                    if predicate(payload):
                        return payload
        return None

    result = await asyncio.wait_for(_read(), timeout=timeout)
    assert result is not None, "SSE stream ended before the expected event arrived"
    return result


async def _collect_until_idle(agen, idle: float = 0.3) -> list[str]:
    """Read chunks for `idle` seconds, return all raw lines seen."""
    got: list[str] = []
    async def _reader():
        async for chunk in agen:
            text = chunk.decode() if isinstance(chunk, bytes) else chunk
            got.extend(text.splitlines())

    try:
        await asyncio.wait_for(_reader(), timeout=idle)
    except (asyncio.TimeoutError, TimeoutError):
        pass
    return got


# ---------------------------------------------------------------------------
# Auth (real HTTP — 401 returns before streaming)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_requires_token(sse_client):
    res = await sse_client.get("/api/plugins/events/stream")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_stream_rejects_invalid_token(sse_client):
    res = await sse_client.get(
        "/api/plugins/events/stream", params={"token": "garbage-token"}
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_stream_accepts_valid_token(sse_client, security, fake_engine, fast_keepalive):
    agen = await _open_stream(security)
    try:
        # First frame must be the (fast) keepalive — proves the stream is live.
        async for chunk in agen:
            if ": keepalive" in chunk:
                break
    finally:
        await agen.aclose()


# ---------------------------------------------------------------------------
# Delivery + permission filter (S7)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_delivers_event_with_permission(security, fake_engine):
    """A viewer with a manifest declaring node_read receives the invalidation."""
    fake_engine.set("metrics", [{"name": "node_read"}])

    agen = await _open_stream(security, "viewer")
    try:
        await event_bus.publish(
            "plugins.invalidated",
            {
                "plugin_id": "metrics",
                "boot_id": "b1",
                "revision": 1,
                "action": "loaded",
            },
        )
        # `boot_id: b1` est réservé aux tests — le ring buffer peut contenir
        # de vrais événements (boot_id UUID) publiés par l'engine pendant le
        # reste de la suite ; le prédicat doit les ignorer.
        payload = await _collect_data_lines(
            agen, lambda p: p["boot_id"] == "b1" and p["revision"] == 1
        )
        assert payload["plugin_id"] == "metrics"
    finally:
        await agen.aclose()


@pytest.mark.asyncio
async def test_stream_filters_unloaded_events_for_viewer(security, fake_engine):
    """Fail-closed: an 'unloaded' event (manifest gone) is hidden from viewers."""
    fake_engine.set("metrics", [{"name": "node_read"}])

    agen = await _open_stream(security, "viewer")
    try:
        await event_bus.publish(
            "plugins.invalidated",
            {
                "plugin_id": "metrics",
                "boot_id": "b1",
                "revision": 2,
                "action": "unloaded",
            },
        )
        # The manifest is removed at swap time — simulate that here.
        fake_engine.remove("metrics")

        got = await _collect_until_idle(agen)
        assert not any("unloaded" in line for line in got)
    finally:
        await agen.aclose()


@pytest.mark.asyncio
async def test_stream_admin_receives_unloaded(security, fake_engine):
    fake_engine.set("metrics", [{"name": "node_read"}])

    agen = await _open_stream(security, "admin")
    try:
        await event_bus.publish(
            "plugins.invalidated",
            {
                "plugin_id": "metrics",
                "boot_id": "b1",
                "revision": 3,
                "action": "unloaded",
            },
        )
        # `boot_id: b1` est réservé aux tests — ignore les vrais événements
        # (boot_id UUID) du ring buffer publiés par l'engine.
        payload = await _collect_data_lines(
            agen, lambda p: p["boot_id"] == "b1" and p["action"] == "unloaded"
        )
        assert payload["plugin_id"] == "metrics"
    finally:
        await agen.aclose()


@pytest.mark.asyncio
async def test_stream_unknown_plugin_fail_closed_for_viewer(security, fake_engine):
    """A viewer must never receive events for plugins without a served manifest."""
    agen = await _open_stream(security, "viewer")
    try:
        await event_bus.publish(
            "plugins.invalidated",
            {
                "plugin_id": "ghost",
                "boot_id": "b1",
                "revision": 9,
                "action": "loaded",
            },
        )
        got = await _collect_until_idle(agen)
        assert not any("ghost" in line for line in got)
    finally:
        await agen.aclose()


@pytest.mark.asyncio
async def test_stream_replays_ring_buffer(security, fake_engine):
    """A (re)connecting client sees the buffered event immediately."""
    fake_engine.set("metrics", [{"name": "node_read"}])

    await event_bus.publish(
        "plugins.invalidated",
        {
            "plugin_id": "metrics",
            "boot_id": "b1",
            "revision": 4,
            "action": "loaded",
        },
    )

    agen = await _open_stream(security, "viewer")
    try:
        payload = await _collect_data_lines(
            agen, lambda p: p["plugin_id"] == "metrics" and p["revision"] == 4
        )
        assert payload["action"] == "loaded"
    finally:
        await agen.aclose()


@pytest.mark.asyncio
async def test_stream_keepalive_when_idle(security, fake_engine, fast_keepalive):
    agen = await _open_stream(security, "viewer")
    try:
        # Nothing published → the (fast) wait_for times out → keepalive comment.
        got = await _collect_until_idle(agen, idle=0.5)
        assert any(line == ": keepalive" for line in got)
    finally:
        await agen.aclose()