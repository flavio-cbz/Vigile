"""
Tests for the /batch read-only endpoint (J3a-T16).

Contract (docs/contracts/block-contract-v2.md §5.5, §6.2, §8 S7):
- /batch is READ-ONLY: any sub-request resolving to a mutation command is
  rejected with 403 and NEVER executed (mutations stay on the ActionProposal
  channel).
- Each sub-request is dispatched by command name via the code-derived command
  registry (master/core/command_registry.py) wrapping existing @route handlers
  (danger map D1 — no endpoint body rewrites).
- Node-scope (faille 4): any sub-request injecting needs:["node_id"] re-verifies
  node access PER SUB-REQUEST via the shared NodeManager.get_node helper used
  by /api/nodes — never a whole-batch check.
- Unknown command → 404 fail-closed.
- @route roles are re-applied per sub-request (faille 3 invariant).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import status
from httpx import AsyncClient

import master.core.rate_limiter as rate_limiter_mod
from master.api import deps
from master.core.plugin_base import PluginBase, PluginContext, route
from master.core.security_manager import SecurityManager
from master.main import app


class _ReadPlugin(PluginBase):
    """Fake plugin: one viewer read, one admin-only read, one mutation."""

    plugin_id = "readplug"

    executed_mutations: list[str] = []

    @route("/data", method="GET", roles=["viewer"])
    async def get_data(self, node_id: str | None = None, period: str = "24h") -> dict:
        return {"node_id": node_id, "period": period, "ok": True}

    @route("/admin-data", method="GET", roles=["admin"])
    async def get_admin_data(self) -> dict:
        return {"admin": True}

    @route("/mutate", method="POST", roles=["admin"])
    async def post_mutate(self) -> dict:
        type(self).executed_mutations.append("post_mutate")
        return {"mutated": True}


class _OtherReadPlugin(PluginBase):
    """Second fake plugin: one viewer read (budget-isolation tests)."""

    plugin_id = "otherplug"

    @route("/data", method="GET", roles=["viewer"])
    async def get_data(self) -> dict:
        return {"other": True}


class _V2ReadPlugin(PluginBase):
    """Fake V2 plugin: plugin_id matches the catalog contract ``metrics``.

    ``resource_contract`` is code-derived from the plugin id
    (``command_registry._entry_from_meta``), so a plugin named ``metrics``
    lands on the ``node_read`` catalog entry (read, viewer).
    """

    plugin_id = "metrics"

    @route("/data", method="GET", roles=["viewer"])
    async def get_data(self) -> dict:
        return {"ok": True}


class _V2SystemdPlugin(PluginBase):
    """Fake V2 plugin on the ``systemd`` contract (no declared permissions)."""

    plugin_id = "systemd"

    @route("/status", method="GET", roles=["viewer"])
    async def get_status(self) -> dict:
        return {"systemd": True}


# Unregister test-only classes from global registry so they do not poison other tests
PluginBase._decorated_registry.pop("metrics", None)
PluginBase._decorated_registry.pop("systemd", None)
PluginBase._decorated_registry.pop("otherplug", None)


class _FakeEngine:
    """Stand-in for PluginEngine exposing the `_instances` mapping."""

    def __init__(self, instances: dict, v2_manifests: dict | None = None) -> None:
        self._instances = instances
        self._v2_manifests = v2_manifests or {}

    def get_v2_manifest(self, plugin_id: str):
        return self._v2_manifests.get(plugin_id)


class _FakeNodeManager:
    """NodeManager stand-in: only nodes in `allowed` are accessible."""

    def __init__(self, allowed: set[str]) -> None:
        self._allowed = allowed

    async def get_node(self, db, node_id: str) -> dict | None:
        if node_id in self._allowed:
            return {"id": node_id}
        return None


@pytest.fixture
def auth_headers(security: SecurityManager):
    def _make(role: str = "admin"):
        token = security.create_access_token("test-user", "test_user", role)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
async def client(db):
    from httpx import ASGITransport, AsyncClient

    app.dependency_overrides[deps.get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(deps.get_db, None)


@pytest.fixture
def batch_env(monkeypatch):
    """Mount the fake plugin engine + fake node manager on the app."""
    import master.api.plugins as plugins_mod

    plugin = _ReadPlugin(PluginContext(plugin_id="readplug", config={}, db=None))
    _ReadPlugin.executed_mutations = []

    monkeypatch.setattr(
        plugins_mod, "_get_engine", lambda: _FakeEngine({"readplug": plugin})
    )

    nm = _FakeNodeManager(allowed={"node-y"})
    app.dependency_overrides[deps.get_node_manager] = lambda: nm

    yield plugin

    app.dependency_overrides.pop(deps.get_node_manager, None)
    PluginBase._decorated_registry.pop("readplug", None)


@pytest.fixture
def batch_env_two(monkeypatch):
    """Like ``batch_env`` but mounts two distinct read plugins (isolation tests)."""
    import master.api.plugins as plugins_mod

    read_plugin = _ReadPlugin(PluginContext(plugin_id="readplug", config={}, db=None))
    other_plugin = _OtherReadPlugin(PluginContext(plugin_id="otherplug", config={}, db=None))
    _ReadPlugin.executed_mutations = []

    monkeypatch.setattr(
        plugins_mod,
        "_get_engine",
        lambda: _FakeEngine({"readplug": read_plugin, "otherplug": other_plugin}),
    )

    nm = _FakeNodeManager(allowed={"node-y"})
    app.dependency_overrides[deps.get_node_manager] = lambda: nm

    yield {"readplug": read_plugin, "otherplug": other_plugin}

    app.dependency_overrides.pop(deps.get_node_manager, None)
    PluginBase._decorated_registry.pop("readplug", None)
    PluginBase._decorated_registry.pop("otherplug", None)


@pytest.fixture
def batch_env_v2(monkeypatch):
    """Mount a fake V2 plugin (``metrics`` contract) + its V2 manifest.

    The manifest is a ``SimpleNamespace`` exposing ``.permissions`` — tests
    mutate it in place to exercise the S7 intersection (declared / empty /
    mismatched shapes). The engine lambda re-reads it at request time.
    """
    import master.api.plugins as plugins_mod

    plugin = _V2ReadPlugin(PluginContext(plugin_id="metrics", config={}, db=None))
    manifest = SimpleNamespace(permissions=[{"name": "node_read"}])

    monkeypatch.setattr(
        plugins_mod,
        "_get_engine",
        lambda: _FakeEngine({"metrics": plugin}, v2_manifests={"metrics": manifest}),
    )

    nm = _FakeNodeManager(allowed={"node-y"})
    app.dependency_overrides[deps.get_node_manager] = lambda: nm

    yield SimpleNamespace(plugin=plugin, manifest=manifest)

    app.dependency_overrides.pop(deps.get_node_manager, None)
    PluginBase._decorated_registry.pop("metrics", None)


@pytest.fixture
def batch_env_v2_two(monkeypatch):
    """Two fake V2 plugins: ``metrics`` (declared node_read) + ``systemd`` (wrong contract)."""
    import master.api.plugins as plugins_mod

    metrics_plugin = _V2ReadPlugin(PluginContext(plugin_id="metrics", config={}, db=None))
    systemd_plugin = _V2SystemdPlugin(PluginContext(plugin_id="systemd", config={}, db=None))
    manifests = {
        "metrics": SimpleNamespace(permissions=[{"name": "node_read"}]),
        # node_read belongs to the metrics contract — declared on systemd it
        # does NOT intersect (fail-closed per sub-request).
        "systemd": SimpleNamespace(permissions=[{"name": "node_read"}]),
    }

    monkeypatch.setattr(
        plugins_mod,
        "_get_engine",
        lambda: _FakeEngine(
            {"metrics": metrics_plugin, "systemd": systemd_plugin},
            v2_manifests=manifests,
        ),
    )

    nm = _FakeNodeManager(allowed={"node-y"})
    app.dependency_overrides[deps.get_node_manager] = lambda: nm

    yield SimpleNamespace(metrics=metrics_plugin, systemd=systemd_plugin, manifests=manifests)

    app.dependency_overrides.pop(deps.get_node_manager, None)
    PluginBase._decorated_registry.pop("metrics", None)
    PluginBase._decorated_registry.pop("systemd", None)


@pytest.fixture
def plugin_rate_env(monkeypatch):
    """Patch the S5 limiter singleton + budget provider used by /batch.

    ``set_budget(plugin_id, reads, mutations)`` declares a per-plugin budget;
    plugins without an explicit budget keep the 60 reads/min default. Each
    test gets a fresh ``PluginRateLimiter`` (no cross-test leakage).
    """
    limiter = rate_limiter_mod.PluginRateLimiter(window_seconds=60)
    budgets: dict[str, rate_limiter_mod.PluginBudget] = {}

    async def _budget_provider(
        plugin_id: str, call_type: rate_limiter_mod.PluginCallType
    ) -> rate_limiter_mod.PluginBudget:
        return budgets.get(plugin_id, rate_limiter_mod.PluginBudget())

    monkeypatch.setattr(rate_limiter_mod, "plugin_rate_limiter", limiter)
    monkeypatch.setattr(rate_limiter_mod, "default_plugin_budget_provider", _budget_provider)

    def set_budget(plugin_id: str, reads: int, mutations: int = 60) -> None:
        budgets[plugin_id] = rate_limiter_mod.PluginBudget(
            reads_per_minute=reads, mutations_per_minute=mutations
        )

    return SimpleNamespace(limiter=limiter, set_budget=set_budget)


@pytest.mark.asyncio
async def test_batch_success_executes_read_commands(client, auth_headers, batch_env):
    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("operator"),
        json={
            "requests": [
                {"command": "readplug.get_data", "params": {"node_id": "node-y", "period": "1h"}},
                {"command": "readplug.get_data", "params": {}},
            ]
        },
    )
    assert res.status_code == status.HTTP_200_OK
    results = res.json()["results"]
    assert len(results) == 2
    assert results[0]["status"] == 200
    assert results[0]["data"] == {"node_id": "node-y", "period": "1h", "ok": True}
    assert results[1]["status"] == 200
    assert results[1]["data"] == {"node_id": None, "period": "24h", "ok": True}


@pytest.mark.asyncio
async def test_batch_rejects_mutation_command_403_and_never_executes(
    client, auth_headers, batch_env
):
    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("admin"),
        json={
            "requests": [
                {"command": "readplug.post_mutate", "params": {}},
                {"command": "readplug.get_data", "params": {}},
            ]
        },
    )
    assert res.status_code == status.HTTP_200_OK
    results = res.json()["results"]
    assert results[0]["status"] == 403
    assert "mutation" in results[0]["error"].lower()
    # The sibling read sub-request still succeeds (per-sub-request semantics)
    assert results[1]["status"] == 200
    # The mutation handler must never have run
    assert _ReadPlugin.executed_mutations == []


@pytest.mark.asyncio
async def test_batch_unknown_command_404(client, auth_headers, batch_env):
    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("operator"),
        json={"requests": [{"command": "readplug.nope", "params": {}}]},
    )
    assert res.status_code == status.HTTP_200_OK
    results = res.json()["results"]
    assert results[0]["status"] == 404
    assert "unknown" in results[0]["error"].lower()


@pytest.mark.asyncio
async def test_batch_per_subrequest_node_scope_denial(client, auth_headers, batch_env):
    """User without access to node-x: that sub-request is rejected, others succeed."""
    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("operator"),
        json={
            "requests": [
                {"command": "readplug.get_data", "params": {"node_id": "node-x"}},
                {"command": "readplug.get_data", "params": {"node_id": "node-y"}},
                {"command": "readplug.get_data", "params": {}},
            ]
        },
    )
    assert res.status_code == status.HTTP_200_OK
    results = res.json()["results"]
    assert results[0]["status"] == 403
    assert "node" in results[0]["error"].lower()
    assert results[1]["status"] == 200
    assert results[2]["status"] == 200


@pytest.mark.asyncio
async def test_batch_role_gate_per_subrequest(client, auth_headers, batch_env):
    """@route roles are re-applied per sub-request (faille 3): viewer cannot run admin-only reads."""
    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("viewer"),
        json={
            "requests": [
                {"command": "readplug.get_admin_data", "params": {}},
                {"command": "readplug.get_data", "params": {}},
            ]
        },
    )
    assert res.status_code == status.HTTP_200_OK
    results = res.json()["results"]
    assert results[0]["status"] == 403
    assert results[1]["status"] == 200


@pytest.mark.asyncio
async def test_batch_requires_auth(client, batch_env):
    res = await client.post(
        "/api/plugins/batch",
        json={"requests": [{"command": "readplug.get_data", "params": {}}]},
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.fixture
def batch_env_docker(monkeypatch):
    """Mount the REAL docker plugin (U2) — its POST action route is a mutation.

    ``docker.container_action_route`` is code-derived with method=POST →
    mutation=True, so /batch must reject it with 403 and NEVER invoke the
    handler (no proposal, no dispatch — mutations stay on the
    ActionProposal channel).
    """
    import master.api.plugins as plugins_mod
    from master.plugins.docker import DockerPlugin

    plugin = DockerPlugin(PluginContext(plugin_id="docker", config={}, db=None))

    monkeypatch.setattr(
        plugins_mod, "_get_engine", lambda: _FakeEngine({"docker": plugin})
    )

    nm = _FakeNodeManager(allowed={"node-y"})
    app.dependency_overrides[deps.get_node_manager] = lambda: nm

    yield plugin

    app.dependency_overrides.pop(deps.get_node_manager, None)


@pytest.mark.asyncio
async def test_batch_rejects_docker_mutation_command_403(
    client, auth_headers, batch_env_docker
):
    """U2: the docker container-action POST route is a mutation — 403 on /batch.

    The command must resolve from the code-derived registry (no 404) and be
    rejected by the mutation gate (no 200, no handler invocation): the docker
    actions stay on the ActionProposal channel.
    """
    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("operator"),
        json={
            "requests": [
                {
                    "command": "docker.container_action_route",
                    "params": {"container_id": "abc123", "action": "restart", "node_id": "node-y"},
                },
                {"command": "docker.list_containers_route", "params": {"node_id": "node-y"}},
            ]
        },
    )
    assert res.status_code == status.HTTP_200_OK
    results = res.json()["results"]
    assert results[0]["status"] == 403
    assert "mutation" in results[0]["error"].lower()
    # The sibling read sub-request still succeeds (per-sub-request semantics)
    assert results[1]["status"] == 200
    assert results[1]["data"] == {"containers": [], "count": 0}


@pytest.fixture
def batch_env_systemd(monkeypatch):
    """Mount the REAL systemd plugin (U2) — its POST action route is a mutation.

    ``systemd.service_action_route`` is code-derived with method=POST →
    mutation=True, so /batch must reject it with 403 and NEVER invoke the
    handler (no proposal, no dispatch — mutations stay on the
    ActionProposal channel).
    """
    import master.api.plugins as plugins_mod
    from master.plugins.systemd import SystemdPlugin

    plugin = SystemdPlugin(PluginContext(plugin_id="systemd", config={}, db=None))

    monkeypatch.setattr(
        plugins_mod, "_get_engine", lambda: _FakeEngine({"systemd": plugin})
    )

    nm = _FakeNodeManager(allowed={"node-y"})
    app.dependency_overrides[deps.get_node_manager] = lambda: nm

    yield plugin

    app.dependency_overrides.pop(deps.get_node_manager, None)


@pytest.mark.asyncio
async def test_batch_rejects_systemd_mutation_command_403(
    client, auth_headers, batch_env_systemd
):
    """U2: the systemd service-action POST route is a mutation — 403 on /batch.

    The command must resolve from the code-derived registry (no 404) and be
    rejected by the mutation gate (no 200, no handler invocation): the systemd
    actions stay on the ActionProposal channel.
    """
    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("operator"),
        json={
            "requests": [
                {
                    "command": "systemd.service_action_route",
                    "params": {"service_name": "ssh.service", "action": "restart", "node_id": "node-y"},
                },
                {"command": "systemd.list_services_route", "params": {"node_id": "node-y"}},
            ]
        },
    )
    assert res.status_code == status.HTTP_200_OK
    results = res.json()["results"]
    assert results[0]["status"] == 403
    assert "mutation" in results[0]["error"].lower()
    # The sibling read sub-request still succeeds (per-sub-request semantics)
    assert results[1]["status"] == 200
    assert results[1]["data"] == {"services": [], "count": 0}


# ---------------------------------------------------------------------------
# S5 — per-plugin rate budget on /batch (J3a-T19 → T16 wiring)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_charges_per_plugin_ratio(
    client, auth_headers, batch_env, plugin_rate_env
):
    """S5: 3 sub-requests against ONE plugin with READS=2 → [200, 200, 429].

    The exhausted third sub-request gets its own 429 entry; the batch HTTP
    status stays 200 and the shape stays ``{"results": [...]}``.
    """
    plugin_rate_env.set_budget("readplug", reads=2)

    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("operator"),
        json={
            "requests": [
                {"command": "readplug.get_data", "params": {}},
                {"command": "readplug.get_data", "params": {}},
                {"command": "readplug.get_data", "params": {}},
            ]
        },
    )
    assert res.status_code == status.HTTP_200_OK
    assert set(res.json().keys()) == {"results"}
    results = res.json()["results"]
    assert [r["status"] for r in results] == [200, 200, 429]
    assert "budget" in results[2]["error"].lower()


@pytest.mark.asyncio
async def test_batch_rate_isolation_between_plugins(
    client, auth_headers, batch_env_two, plugin_rate_env
):
    """S5: plugins A (READS=1) and B (READS=1) → batch [A, A, B] = [200, 429, 200].

    B's budget is untouched by A's exhaustion (composite key per plugin).
    """
    plugin_rate_env.set_budget("readplug", reads=1)
    plugin_rate_env.set_budget("otherplug", reads=1)

    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("operator"),
        json={
            "requests": [
                {"command": "readplug.get_data", "params": {}},
                {"command": "readplug.get_data", "params": {}},
                {"command": "otherplug.get_data", "params": {}},
            ]
        },
    )
    assert res.status_code == status.HTTP_200_OK
    results = res.json()["results"]
    assert [r["status"] for r in results] == [200, 429, 200]
    assert results[2]["data"] == {"other": True}


@pytest.mark.asyncio
async def test_batch_no_rate_charge_for_unknown(
    client, auth_headers, batch_env, plugin_rate_env
):
    """S5 ordering: an unknown command returns its 404 entry without a charge.

    READS=0 makes any charge fail with 429 — the 404 proves the charge happens
    only after the dispatch lookup (and the mutation / roles / node-scope gates).
    """
    plugin_rate_env.set_budget("readplug", reads=0)

    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("operator"),
        json={"requests": [{"command": "readplug.nope", "params": {}}]},
    )
    assert res.status_code == status.HTTP_200_OK
    results = res.json()["results"]
    assert results[0]["status"] == 404
    assert "unknown" in results[0]["error"].lower()


# ---------------------------------------------------------------------------
# S7 — permission-intersection gate on /batch (block-contract-v2.md §6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s7_flat_model_legacy_v1(client, auth_headers, batch_env):
    """S7 regression guard: V1 plugins without a V2 manifest stay on the flat model.

    ``_FakeEngine`` exposes no ``get_v2_manifest`` here — the gate must not
    reject anything (``check_permission_intersection`` returns allowed for an
    absent manifest).
    """
    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("viewer"),
        json={"requests": [{"command": "readplug.get_data", "params": {}}]},
    )
    assert res.status_code == status.HTTP_200_OK
    results = res.json()["results"]
    assert results[0]["status"] == 200
    assert results[0]["data"] == {"node_id": None, "period": "24h", "ok": True}


@pytest.mark.asyncio
async def test_s7_v2_declared_permission_allowed(client, auth_headers, batch_env_v2):
    """S7: V2 plugin declaring ``node_read`` (dict form) + viewer role → 200.

    ``metrics.get_data`` is a read command whose ``resource_contract``
    (plugin id ``metrics``) matches the catalog entry ``node_read``
    (mutation=False, min_role=viewer).
    """
    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("viewer"),
        json={"requests": [{"command": "metrics.get_data", "params": {}}]},
    )
    assert res.status_code == status.HTTP_200_OK
    results = res.json()["results"]
    assert results[0]["status"] == 200
    assert results[0]["data"] == {"ok": True}


@pytest.mark.asyncio
async def test_s7_v2_undeclared_permission_denied(client, auth_headers, batch_env_v2):
    """S7 fail-closed: V2 plugin declaring a permission OUTSIDE the closed catalog → 403.

    Note: ``permissions = []`` (or absent) is the FLAT MODEL in
    ``master/core/permissions.py`` (allowed — V1 heritage). The fail-closed
    path triggers on a declared permission that does not intersect: here
    ``totally_made_up`` is not in ``PERMISSION_CATALOG``. The batch HTTP
    status stays 200 and the entry carries the ``permission denied for
    command: ...`` error with the catalog reason.
    """
    batch_env_v2.manifest.permissions = [{"name": "totally_made_up"}]

    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("viewer"),
        json={"requests": [{"command": "metrics.get_data", "params": {}}]},
    )
    assert res.status_code == status.HTTP_200_OK
    results = res.json()["results"]
    assert results[0]["status"] == 403
    assert "permission denied for command: metrics.get_data" in results[0]["error"]
    assert "permission non déclarée" in results[0]["error"]


@pytest.mark.asyncio
async def test_s7_v2_role_below_mim_role_denied(client, auth_headers, batch_env_v2):
    """S7: mutation-shape permission declared on a read command → 403.

    ``restart_service`` (catalog: systemd, mutation=True, min_role=operator)
    does not match the read shape of ``metrics.get_data`` (mutation=False) —
    the intersection fails closed even for an operator.
    """
    batch_env_v2.manifest.permissions = [{"name": "restart_service"}]

    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("operator"),
        json={"requests": [{"command": "metrics.get_data", "params": {}}]},
    )
    assert res.status_code == status.HTTP_200_OK
    results = res.json()["results"]
    assert results[0]["status"] == 403
    assert "permission denied for command: metrics.get_data" in results[0]["error"]


@pytest.mark.asyncio
async def test_s7_per_subrequest_isolation(client, auth_headers, batch_env_v2_two):
    """S7: batch [allowed, denied, allowed] → [200, 403, 200].

    ``metrics`` declares ``node_read`` (its own contract — allowed);
    ``systemd`` declares ``node_read`` too, but that permission belongs to
    the ``metrics`` contract → no intersection → denied. The denial is per
    sub-request — siblings still run.
    """
    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("viewer"),
        json={
            "requests": [
                {"command": "metrics.get_data", "params": {}},
                {"command": "systemd.get_status", "params": {}},
                {"command": "metrics.get_data", "params": {}},
            ]
        },
    )
    assert res.status_code == status.HTTP_200_OK
    results = res.json()["results"]
    assert [r["status"] for r in results] == [200, 403, 200]
    assert results[0]["data"] == {"ok": True}
    assert "permission denied for command: systemd.get_status" in results[1]["error"]
    assert results[2]["data"] == {"ok": True}


# ---------------------------------------------------------------------------
# S4 — `since` reconciliation on /batch (T26)
# ---------------------------------------------------------------------------


class _RevisionEngine(_FakeEngine):
    """_FakeEngine + a revision pair (boot_id, counter) like the real engine."""

    def __init__(
        self,
        instances: dict,
        v2_manifests: dict | None = None,
        boot_id: str = "boot-test",
        counter: int = 3,
    ) -> None:
        super().__init__(instances, v2_manifests)
        self._boot_id = boot_id
        self._counter = counter

    @property
    def revision(self):
        return SimpleNamespace(boot_id=self._boot_id, counter=self._counter)


@pytest.fixture
def batch_env_revision(monkeypatch):
    """Mount a revision-bearing engine (boot-test:3) on the app."""
    import master.api.plugins as plugins_mod

    plugin = _ReadPlugin(PluginContext(plugin_id="readplug", config={}, db=None))
    engine = _RevisionEngine({"readplug": plugin})

    monkeypatch.setattr(plugins_mod, "_get_engine", lambda: engine)

    nm = _FakeNodeManager(allowed={"node-y"})
    app.dependency_overrides[deps.get_node_manager] = lambda: nm

    yield engine

    app.dependency_overrides.pop(deps.get_node_manager, None)
    PluginBase._decorated_registry.pop("readplug", None)


@pytest.mark.asyncio
async def test_batch_since_unchanged_returns_empty(client, auth_headers, batch_env_revision):
    """S4: `since` == current revision → `{unchanged: true}` without results.

    The client keeps its cache; no sub-request is executed (at-most-once).
    """
    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("operator"),
        json={
            "requests": [{"command": "readplug.get_data", "params": {}}],
            "since": "boot-test:3",
        },
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"unchanged": True}


@pytest.mark.asyncio
async def test_batch_since_stale_returns_full_results_with_revision(
    client, auth_headers, batch_env_revision
):
    """S4: stale `since` → full results + the current revision pair."""
    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("operator"),
        json={
            "requests": [{"command": "readplug.get_data", "params": {}}],
            "since": "boot-test:1",
        },
    )
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["results"][0]["status"] == 200
    assert body["revision"] == {"boot_id": "boot-test", "counter": 3}


@pytest.mark.asyncio
async def test_batch_since_wrong_boot_id_full_reload(client, auth_headers, batch_env_revision):
    """S4 (faille 7): a different boot_id ⇒ full reload, never partial reconciliation."""
    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("operator"),
        json={
            "requests": [{"command": "readplug.get_data", "params": {}}],
            "since": "other-boot:3",
        },
    )
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["results"][0]["status"] == 200
    assert body["revision"] == {"boot_id": "boot-test", "counter": 3}


@pytest.mark.asyncio
async def test_batch_since_malformed_never_unchanged(client, auth_headers, batch_env_revision):
    """S4: a malformed `since` never yields a false `{unchanged: true}`."""
    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("operator"),
        json={
            "requests": [{"command": "readplug.get_data", "params": {}}],
            "since": "garbage",
        },
    )
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert "results" in body
    assert body["results"][0]["status"] == 200


@pytest.mark.asyncio
async def test_batch_full_response_carries_revision(client, auth_headers, batch_env_revision):
    """S4: without `since`, the full response still carries the revision pair
    (the client captures it for its next `since` call)."""
    res = await client.post(
        "/api/plugins/batch",
        headers=auth_headers("operator"),
        json={"requests": [{"command": "readplug.get_data", "params": {}}]},
    )
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["results"][0]["status"] == 200
    assert body["revision"] == {"boot_id": "boot-test", "counter": 3}