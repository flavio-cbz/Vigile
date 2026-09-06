"""
Tests for the RouteRegistrar GET `?since=` wrapper (T26 / S4).

Contract (docs/contracts/block-contract-v2.md §8.4 + plan S4/D3):
  - Every GET route mounted by RouteRegistrar accepts `?since=<boot_id>:<counter>`.
  - `since` == current engine revision → `{"unchanged": true}` (200) without
    the payload — the client keeps its cache (at-most-once reconciliation).
  - Otherwise the normal response is returned, enriched with the `revision`
    pair `{boot_id, counter}` (extend, don't break).
  - POST routes are NOT wrapped: mutations never get `since` semantics.
  - A malformed `since` never yields a false `unchanged`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from master.core.plugin_base import PluginBase, PluginContext, route
from master.core.route_registrar import RouteRegistrar


class _DataPlugin(PluginBase):
    """Fake plugin: one GET read + one POST mutation."""

    plugin_id = "sinceplug"

    @route("/data", method="GET")
    async def get_data(self, node_id: str | None = None) -> dict:
        return {"node_id": node_id, "ok": True}

    @route("/submit", method="POST")
    async def post_submit(self) -> dict:
        return {"submitted": True}


def _fake_engine(boot_id: str = "boot-test", counter: int = 5) -> SimpleNamespace:
    return SimpleNamespace(revision=SimpleNamespace(boot_id=boot_id, counter=counter))


@pytest.fixture
def since_app(monkeypatch):
    """FastAPI app with the plugin mounted and a fake revision-bearing engine."""
    app = FastAPI()
    registrar = RouteRegistrar(app)
    plugin = _DataPlugin(PluginContext(plugin_id="sinceplug", config={}, db=None))
    registrar.mount("sinceplug", plugin.routes, plugin)

    monkeypatch.setattr("master.core.plugin_manager.plugin_engine", _fake_engine())
    return app


@pytest.mark.asyncio
async def test_get_without_since_returns_data_with_revision(since_app):
    async with AsyncClient(
        transport=ASGITransport(app=since_app), base_url="http://test"
    ) as client:
        res = await client.get("/api/plugins/sinceplug/data")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["revision"] == {"boot_id": "boot-test", "counter": 5}


@pytest.mark.asyncio
async def test_get_with_matching_since_returns_unchanged(since_app):
    async with AsyncClient(
        transport=ASGITransport(app=since_app), base_url="http://test"
    ) as client:
        res = await client.get(
            "/api/plugins/sinceplug/data", params={"since": "boot-test:5"}
        )
    assert res.status_code == 200
    assert res.json() == {"unchanged": True}


@pytest.mark.asyncio
async def test_get_with_stale_since_returns_full_data(since_app):
    async with AsyncClient(
        transport=ASGITransport(app=since_app), base_url="http://test"
    ) as client:
        res = await client.get(
            "/api/plugins/sinceplug/data", params={"since": "boot-test:2"}
        )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["revision"] == {"boot_id": "boot-test", "counter": 5}


@pytest.mark.asyncio
async def test_get_with_wrong_boot_id_full_reload(since_app):
    """S4 (faille 7): a different boot_id ⇒ full reload, never partial reconciliation."""
    async with AsyncClient(
        transport=ASGITransport(app=since_app), base_url="http://test"
    ) as client:
        res = await client.get(
            "/api/plugins/sinceplug/data", params={"since": "other-boot:5"}
        )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["revision"] == {"boot_id": "boot-test", "counter": 5}


@pytest.mark.asyncio
async def test_get_with_malformed_since_never_unchanged(since_app):
    async with AsyncClient(
        transport=ASGITransport(app=since_app), base_url="http://test"
    ) as client:
        res = await client.get("/api/plugins/sinceplug/data", params={"since": "garbage"})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert "unchanged" not in body


@pytest.mark.asyncio
async def test_post_routes_not_wrapped(since_app):
    """POST routes are mutations — no `since` semantics, no revision key."""
    async with AsyncClient(
        transport=ASGITransport(app=since_app), base_url="http://test"
    ) as client:
        res = await client.post("/api/plugins/sinceplug/submit")
    assert res.status_code == 200
    assert res.json() == {"submitted": True}


@pytest.mark.asyncio
async def test_get_handler_params_still_resolved(since_app):
    """The wrapper re-resolves the handler's own query params (node_id here)."""
    async with AsyncClient(
        transport=ASGITransport(app=since_app), base_url="http://test"
    ) as client:
        res = await client.get(
            "/api/plugins/sinceplug/data", params={"node_id": "node-1"}
        )
    assert res.status_code == 200
    body = res.json()
    assert body["node_id"] == "node-1"
    assert body["revision"] == {"boot_id": "boot-test", "counter": 5}