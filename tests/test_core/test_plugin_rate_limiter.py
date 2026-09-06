from __future__ import annotations

"""
S5 — Per-plugin, per-user rate limiting (J3a-T19).

Two independent sliding-window budgets per plugin per user: READS vs MUTATIONS
(plan faille 8). Composite key ``plugin:{plugin_id}:{user_id}:{call_type}``.
The budget is resolved from the plugin manifest with an admin override in the
plugin config (``config_json["rate_limits"]``); cancellation releases the quota
via a token, timeout consumes it until the window expires.
"""

import time

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from master.core.rate_limiter import (
    PLUGIN_DEFAULT_MUTATIONS_PER_MINUTE,
    PLUGIN_DEFAULT_READS_PER_MINUTE,
    PluginBudget,
    PluginCallType,
    PluginRateLimitToken,
    PluginRateLimiter,
    plugin_budget_from_config,
    require_plugin_budget,
    resolve_plugin_budget,
)

USER = lambda _request: "user-1"  # noqa: E731 - static user provider for tests


@pytest.mark.asyncio
async def test_dual_budgets_are_independent():
    """READS and MUTATIONS are two separate budgets: exhausting one never
    consumes the other (plan faille 8)."""
    limiter = PluginRateLimiter(window_seconds=60)
    budget = PluginBudget(reads_per_minute=3, mutations_per_minute=1)
    now = 1_000.0

    for _ in range(3):
        token = await limiter.acquire("plex", "user-1", PluginCallType.READS, budget, now=now)
        assert token is not None
    assert await limiter.acquire("plex", "user-1", PluginCallType.READS, budget, now=now) is None

    # Mutation budget untouched by read exhaustion
    assert (
        await limiter.acquire("plex", "user-1", PluginCallType.MUTATIONS, budget, now=now)
        is not None
    )
    assert (
        await limiter.acquire("plex", "user-1", PluginCallType.MUTATIONS, budget, now=now)
        is None
    )


@pytest.mark.asyncio
async def test_composite_key_isolates_users_and_plugins():
    """Composite key plugin:{plugin_id}:{user_id}:{call_type}: two users of the
    same plugin, and two plugins of the same user, never share a budget."""
    limiter = PluginRateLimiter(window_seconds=60)
    budget = PluginBudget(reads_per_minute=1, mutations_per_minute=1)
    now = 1_000.0

    assert (
        await limiter.acquire("plex", "alice", PluginCallType.READS, budget, now=now)
        is not None
    )
    # Alice exhausted, Bob untouched
    assert await limiter.acquire("plex", "alice", PluginCallType.READS, budget, now=now) is None
    assert (
        await limiter.acquire("plex", "bob", PluginCallType.READS, budget, now=now) is not None
    )
    # Different plugin, same user, untouched
    assert (
        await limiter.acquire("metrics", "alice", PluginCallType.READS, budget, now=now)
        is not None
    )


@pytest.mark.asyncio
async def test_release_frees_quota_and_is_idempotent():
    """A cancelled attempt releases exactly its own slot immediately
    (plan Partie 4 §4); double release is a no-op."""
    limiter = PluginRateLimiter(window_seconds=60)
    budget = PluginBudget(reads_per_minute=2, mutations_per_minute=2)
    now = 1_000.0

    t1 = await limiter.acquire("plex", "u1", PluginCallType.READS, budget, now=now)
    t2 = await limiter.acquire("plex", "u1", PluginCallType.READS, budget, now=now)
    assert t1 is not None and t2 is not None
    assert await limiter.acquire("plex", "u1", PluginCallType.READS, budget, now=now) is None

    await t1.release()
    await t1.release()  # idempotent — must not over-release

    # Exactly one slot freed
    assert (
        await limiter.acquire("plex", "u1", PluginCallType.READS, budget, now=now) is not None
    )
    assert await limiter.acquire("plex", "u1", PluginCallType.READS, budget, now=now) is None


@pytest.mark.asyncio
async def test_timeout_consumes_budget_until_window_expiry():
    """Timeout path (no release) consumes the full budget until the window
    elapses (plan Partie 4 §4)."""
    limiter = PluginRateLimiter(window_seconds=60)
    budget = PluginBudget(reads_per_minute=2, mutations_per_minute=2)
    now = 1_000.0

    assert (
        await limiter.acquire("plex", "u1", PluginCallType.READS, budget, now=now) is not None
    )
    assert (
        await limiter.acquire("plex", "u1", PluginCallType.READS, budget, now=now) is not None
    )
    # No release: still denied mid-window
    assert (
        await limiter.acquire("plex", "u1", PluginCallType.READS, budget, now=now + 30) is None
    )
    # Window elapsed: expired slots no longer count
    assert (
        await limiter.acquire("plex", "u1", PluginCallType.READS, budget, now=now + 60.001)
        is not None
    )


@pytest.mark.asyncio
async def test_cleanup_expired_prunes_stale_buckets():
    """Lifespan cleanup prunes buckets whose newest entry fell out of the
    window, mirroring RateLimiter.cleanup_expired."""
    limiter = PluginRateLimiter(window_seconds=60)
    budget = PluginBudget()

    assert (
        await limiter.acquire("plex", "u1", PluginCallType.READS, budget) is not None
    )
    key = "plugin:plex:u1:reads"
    assert key in limiter._buckets

    # Fresh entries survive a cleanup pass
    await limiter.cleanup_expired()
    assert key in limiter._buckets

    # Stale injected bucket is pruned
    now = time.time()
    limiter._buckets[key] = [(now - 61.0, 1)]
    await limiter.cleanup_expired()
    assert key not in limiter._buckets


def test_resolve_plugin_budget_precedence():
    """Budget resolution: defaults → manifest → admin override wins."""
    defaults = resolve_plugin_budget(None, None)
    assert defaults.reads_per_minute == PLUGIN_DEFAULT_READS_PER_MINUTE
    assert defaults.mutations_per_minute == PLUGIN_DEFAULT_MUTATIONS_PER_MINUTE

    manifest_only = resolve_plugin_budget({"reads_per_minute": 30}, None)
    assert manifest_only.reads_per_minute == 30
    assert manifest_only.mutations_per_minute == PLUGIN_DEFAULT_MUTATIONS_PER_MINUTE

    # Override wins for the key it sets; manifest still fills the other
    overridden = resolve_plugin_budget(
        {"reads_per_minute": 30, "mutations_per_minute": 5}, {"reads_per_minute": 120}
    )
    assert overridden.reads_per_minute == 120
    assert overridden.mutations_per_minute == 5

    # Invalid manifest value → default; negative → 0 (deny-all, fail closed)
    fallback = resolve_plugin_budget(
        {"reads_per_minute": "abc", "mutations_per_minute": -3}, None
    )
    assert fallback.reads_per_minute == PLUGIN_DEFAULT_READS_PER_MINUTE
    assert fallback.mutations_per_minute == 0


def test_plugin_budget_from_config():
    """Admin override lives under the reserved 'rate_limits' key of the plugin
    config (plugins.config_json); absent key → None (no override)."""
    assert plugin_budget_from_config({}) is None
    assert plugin_budget_from_config({"url": "http://localhost"}) is None

    overridden = plugin_budget_from_config({"rate_limits": {"reads_per_minute": 5}})
    assert overridden is not None
    assert overridden.reads_per_minute == 5
    assert overridden.mutations_per_minute == PLUGIN_DEFAULT_MUTATIONS_PER_MINUTE


def test_require_plugin_budget_dependency_enforces_budget():
    """FastAPI dependency enforces the per-user budget; exhaustion → 429 with
    Retry-After. Reads exhaustion does not touch the mutation budget."""
    limiter = PluginRateLimiter(window_seconds=60)
    budget = PluginBudget(reads_per_minute=2, mutations_per_minute=1)
    app = FastAPI()

    @app.get(
        "/reads",
        dependencies=[
            Depends(
                require_plugin_budget(
                    "plex",
                    PluginCallType.READS,
                    budget=budget,
                    user_provider=USER,
                    limiter=limiter,
                )
            )
        ],
    )
    def reads_route():
        return {"ok": True}

    @app.post(
        "/mutate",
        dependencies=[
            Depends(
                require_plugin_budget(
                    "plex",
                    PluginCallType.MUTATIONS,
                    budget=budget,
                    user_provider=USER,
                    limiter=limiter,
                )
            )
        ],
    )
    def mutate_route():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/reads").status_code == 200
    assert client.get("/reads").status_code == 200
    denied = client.get("/reads")
    assert denied.status_code == 429
    assert denied.headers["Retry-After"] == "60"

    # Mutation budget untouched by read exhaustion
    assert client.post("/mutate").status_code == 200
    assert client.post("/mutate").status_code == 429


def test_require_plugin_budget_dependency_returns_releasable_token():
    """The dependency returns a token the handler can release on cancel:
    at limit 1, a released attempt frees the quota for the next call."""
    limiter = PluginRateLimiter(window_seconds=60)
    app = FastAPI()

    @app.get("/scan")
    async def scan(
        token: PluginRateLimitToken = Depends(
            require_plugin_budget(
                "plex",
                PluginCallType.READS,
                budget=PluginBudget(reads_per_minute=1, mutations_per_minute=1),
                user_provider=USER,
                limiter=limiter,
            )
        ),
    ):
        # Simulated cancelled attempt → quota released immediately
        await token.release()
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/scan").status_code == 200
    assert client.get("/scan").status_code == 200  # released slot allows the next call
