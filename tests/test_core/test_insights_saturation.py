import asyncio
import json
import time
import unittest.mock as mock

import pytest
import aiosqlite

from master.core.insights import DiagnosticReport, InsightsManager, NodeProfile

class FakeNodeManager:
    """Minimal NodeManager fake returning a canned node dict."""

    def __init__(self, node: dict):
        self._node = node

    async def get_node(self, db, node_id):
        return self._node


@pytest.mark.asyncio
async def test_disk_insight_under_6h():
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE metrics_snapshots (
                node_id TEXT,
                collected_at REAL,
                disk_used_bytes INTEGER,
                disk_total_bytes INTEGER,
                disk_percent REAL
            )
        """)

        now = time.time()
        # Add 3 snapshots over 2 hours
        total = 100 * (1024**3)
        await db.execute("INSERT INTO metrics_snapshots VALUES (?, ?, ?, ?, ?)", ("n1", now - 7200, 50 * (1024**3), total, 50.0))
        await db.execute("INSERT INTO metrics_snapshots VALUES (?, ?, ?, ?, ?)", ("n1", now - 3600, 52 * (1024**3), total, 52.0))
        await db.execute("INSERT INTO metrics_snapshots VALUES (?, ?, ?, ?, ?)", ("n1", now, 54 * (1024**3), total, 54.0))
        await db.commit()

        im = InsightsManager()
        latest = {"disk_total_bytes": total, "disk_used_bytes": 54 * (1024**3), "disk_percent": 54.0}
        res = await im._calculate_disk_insight("n1", db, latest)

        assert res is not None
        assert res["confidence"] == "none"
        assert res["headline"] == "Collecte en cours"

@pytest.mark.asyncio
async def test_disk_insight_early_estimation_6h_to_24h():
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE metrics_snapshots (
                node_id TEXT,
                collected_at REAL,
                disk_used_bytes INTEGER,
                disk_total_bytes INTEGER,
                disk_percent REAL
            )
        """)

        now = time.time()
        total = 100 * (1024**3)
        # Add 10 snapshots over 10 hours growing at 2 GB/day (free = 40 GB -> ~20 days left)
        for i in range(10):
            t = now - 36000 + i * 3600
            used = (50 + (i * 0.0833)) * (1024**3)
            await db.execute("INSERT INTO metrics_snapshots VALUES (?, ?, ?, ?, ?)", ("n1", t, int(used), total, 55.0))
        await db.commit()

        im = InsightsManager()
        latest = {"disk_total_bytes": total, "disk_used_bytes": 60 * (1024**3), "disk_percent": 60.0}
        res = await im._calculate_disk_insight("n1", db, latest)

        assert res is not None
        assert res["confidence"] == "medium"
        assert "confiance moyenne" in res["headline"]
        assert "À prévoir avant" in res["detail"]

@pytest.mark.asyncio
async def test_disk_insight_priority_exception_under_24h_saturation():
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE metrics_snapshots (
                node_id TEXT,
                collected_at REAL,
                disk_used_bytes INTEGER,
                disk_total_bytes INTEGER,
                disk_percent REAL
            )
        """)

        now = time.time()
        total = 100 * (1024**3)
        # 8 hours of data, rapid growth of 5 GB/h with only 3 GB free left
        for i in range(8):
            t = now - 28800 + i * 3600
            used = (60 + i * 5) * (1024**3)
            await db.execute("INSERT INTO metrics_snapshots VALUES (?, ?, ?, ?, ?)", ("n1", t, int(used), total, 95.0))
        await db.commit()

        im = InsightsManager()
        latest = {"disk_total_bytes": total, "disk_used_bytes": 97 * (1024**3), "disk_percent": 97.0}
        res = await im._calculate_disk_insight("n1", db, latest)

        assert res is not None
        assert res["severity"] == "critical"
        assert "Risque de saturation aujourd’hui" in res["headline"]

@pytest.mark.asyncio
async def test_disk_insight_ignores_outlier_spike():
    """A transient +50 GB spike (backup written then deleted) must not skew the slope."""
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE metrics_snapshots (
                node_id TEXT,
                collected_at REAL,
                disk_used_bytes INTEGER,
                disk_total_bytes INTEGER,
                disk_percent REAL
            )
        """)

        now = time.time()
        total = 500 * (1024**3)
        base = 100 * (1024**3)
        # 9 points at ~1 GB usage + 1 point at +50 GB (write at the very end).
        for i in range(10):
            t = now - 18 * 3600 + i * 2 * 3600
            used = base if i < 9 else 150 * (1024**3)
            await db.execute("INSERT INTO metrics_snapshots VALUES (?, ?, ?, ?, ?)", ("n1", t, used, total, 30.0))
        await db.commit()

        im = InsightsManager()
        latest = {"disk_total_bytes": total, "disk_used_bytes": 150 * (1024**3), "disk_percent": 30.0}
        res = await im._calculate_disk_insight("n1", db, latest)

        assert res is not None
        assert res["severity"] == "ok"
        assert res["headline"] == "Disque stable"
        assert res["raw"]["growth_gb_per_day"] < 5.0

@pytest.mark.asyncio
async def test_disk_insight_mass_deletion_keeps_growth_rate():
    """A mass deletion (level shift) must not zero the growth estimate:
    the underlying growth rate must still be reported."""
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE metrics_snapshots (
                node_id TEXT,
                collected_at REAL,
                disk_used_bytes INTEGER,
                disk_total_bytes INTEGER,
                disk_percent REAL
            )
        """)

        now = time.time()
        total = 500 * (1024**3)
        used = 400 * (1024**3)
        growth = 2.0 / 24.0 * (1024**3)  # ~2 GB/day
        # 24 snapshots over 24h, steady +2 GB/day growth, -50 GB at midpoint.
        for i in range(24):
            t = now - 86400 + i * 3600
            if i == 12:
                used -= 50 * (1024**3)
            else:
                used += int(growth)
            await db.execute("INSERT INTO metrics_snapshots VALUES (?, ?, ?, ?, ?)", ("n1", t, int(used), total, 70.0))
        await db.commit()

        im = InsightsManager()
        latest = {"disk_total_bytes": total, "disk_used_bytes": int(used), "disk_percent": 70.0}
        res = await im._calculate_disk_insight("n1", db, latest)

        assert res is not None
        # Real growth is ~2 GB/day; the -50 GB step must not zero it out.
        assert 1.0 < res["raw"]["growth_gb_per_day"] < 5.0

@pytest.mark.asyncio
async def test_disk_insight_without_filter_would_be_skewed():
    """Sanity: the same data without the IQR filter yields a high slope (regression on raw points)."""
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE metrics_snapshots (
                node_id TEXT,
                collected_at REAL,
                disk_used_bytes INTEGER,
                disk_total_bytes INTEGER,
                disk_percent REAL
            )
        """)

        now = time.time()
        total = 500 * (1024**3)
        base = 100 * (1024**3)
        for i in range(10):
            t = now - 18 * 3600 + i * 2 * 3600
            used = base if i < 9 else 150 * (1024**3)
            await db.execute("INSERT INTO metrics_snapshots VALUES (?, ?, ?, ?, ?)", ("n1", t, used, total, 30.0))
        await db.commit()

        im = InsightsManager()
        latest = {"disk_total_bytes": total, "disk_used_bytes": 150 * (1024**3), "disk_percent": 30.0}

        # Bypass the filter by copying the raw regression on unfiltered points.
        snapshots = []
        async with db.execute(
            "SELECT collected_at, disk_used_bytes FROM metrics_snapshots WHERE node_id = ? ORDER BY collected_at ASC",
            ("n1",),
        ) as cursor:
            async for r in cursor:
                snapshots.append({"collected_at": r[0], "disk_used_bytes": r[1]})

        t0 = snapshots[0]["collected_at"]
        x = [(s["collected_at"] - t0) / 86400.0 for s in snapshots]
        y = [s["disk_used_bytes"] / (1024**3) for s in snapshots]
        n = len(snapshots)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xx = sum(xi * xi for xi in x)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        raw_slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x)

        assert raw_slope > 5.0  # the step dominates without filtering

@pytest.mark.asyncio
async def test_stale_profile_triggers_reprofile_while_serving_insights():
    """Profile older than 7 days spawns a re-profile task but insights still return."""
    async with aiosqlite.connect(":memory:") as db:
        db.row_factory = aiosqlite.Row  # get_insights() relies on dict(row)
        await db.execute("""
            CREATE TABLE metrics_snapshots (
                node_id TEXT,
                collected_at REAL,
                disk_used_bytes INTEGER,
                disk_total_bytes INTEGER,
                disk_percent REAL
            )
        """)

        node_id = "n1"
        now = time.time()
        total = 100 * (1024**3)
        used = 20 * (1024**3)
        for i in range(4):
            await db.execute("INSERT INTO metrics_snapshots VALUES (?, ?, ?, ?, ?)", (node_id, now - (30 - i * 10) * 3600, used, total, 20.0))
        await db.commit()

        node = {
            "id": node_id,
            "name": "stale-node",
            "hostname": "stale-host",
            "online": True,
            "insight_profile": '{"node_id": "n1", "known_heavy_processes": [], "baseline_ram_percent": 70.0, "context_label": "Serveur test"}',
            "insight_profile_generated_at": now - 8 * 86400,
            "cached_services_json": "[]",
            "cached_containers_json": "[]",
        }

        im = InsightsManager()
        im.generate_profile = mock.AsyncMock(
            return_value=NodeProfile(node_id=node_id)
        )
        res = await im.get_insights(node_id, db, FakeNodeManager(node))
        await im.ensure_tasks_complete(timeout=5.0)

        assert im.generate_profile.call_count == 1
        # Stale-while-revalidate: insights still served from the old profile.
        assert res["profile_confidence"] == "high"
        assert len(res["insights"]) == 3

@pytest.mark.asyncio
async def test_fresh_profile_does_not_trigger_reprofile():
    """A profile generated less than 7 days ago must not spawn a re-profile task."""
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE metrics_snapshots (
                node_id TEXT,
                collected_at REAL,
                disk_used_bytes INTEGER,
                disk_total_bytes INTEGER,
                disk_percent REAL
            )
        """)

        node_id = "n1"
        now = time.time()
        node = {
            "id": node_id,
            "name": "fresh-node",
            "hostname": "fresh-host",
            "online": True,
            "insight_profile": '{"node_id": "n1", "known_heavy_processes": [], "baseline_ram_percent": 70.0, "context_label": "Serveur test"}',
            "insight_profile_generated_at": now - 3600,
            "cached_services_json": "[]",
            "cached_containers_json": "[]",
        }

        im = InsightsManager()
        im.generate_profile = mock.AsyncMock(
            return_value=NodeProfile(node_id=node_id)
        )
        res = await im.get_insights(node_id, db, FakeNodeManager(node))
        await im.ensure_tasks_complete(timeout=5.0)

        assert im.generate_profile.call_count == 0
        assert node_id not in im._profiling_nodes
        # No snapshots -> "En attente de métriques" early return, no crash.
        assert res["insights"][0]["headline"] == "En attente de métriques"

@pytest.mark.asyncio
async def test_profile_generation_inflight_guard_prevents_duplicates():
    """Concurrent get_insights calls must not double-spawn profile generation."""
    async with aiosqlite.connect(":memory:") as db:
        node = {"id": "n1", "name": "n", "hostname": "h", "online": True}

        im = InsightsManager()
        release = asyncio.Event()

        async def slow_profile(node_id, db, nm, **kwargs):
            await release.wait()
            return NodeProfile(node_id=node_id)

        im.generate_profile = slow_profile

        res1 = await im.get_insights("n1", db, FakeNodeManager(node))
        assert "n1" in im._profiling_nodes
        assert res1["insights"][0]["headline"] == "Analyse du profil en cours"
        assert len(im._background_tasks) == 1

        # Second call while generation is in-flight: no duplicate spawn.
        res2 = await im.get_insights("n1", db, FakeNodeManager(node))
        assert "n1" in im._profiling_nodes
        assert len(im._background_tasks) == 1
        assert res2["insights"][0]["headline"] == "Analyse du profil en cours"

        release.set()
        await im.ensure_tasks_complete(timeout=5.0)
        assert "n1" not in im._profiling_nodes

@pytest.mark.asyncio
async def test_analyze_anomaly_trims_services_and_containers_in_prompt():
    """The LLM prompt must contain at most 20 trimmed services/containers each."""
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("CREATE TABLE metrics_snapshots (node_id TEXT, collected_at REAL)")
        await db.execute("CREATE TABLE audit_log (action TEXT, details_json TEXT, created_at REAL, node_id TEXT)")
        await db.commit()

        services = [
            {"service": f"svc-{i}", "state": "active" if i % 2 == 0 else "inactive"}
            for i in range(50)
        ]
        containers = [
            {"name": f"ctn-{i}", "state": "running" if i % 2 == 0 else "exited"}
            for i in range(50)
        ]
        node = {
            "id": "n1",
            "name": "test-server",
            "cached_services_json": json.dumps(services),
            "cached_containers_json": json.dumps(containers),
        }

        captured: dict = {}

        async def fake_create(response_model, messages, **kwargs):
            captured["messages"] = messages
            return DiagnosticReport(headline="h", explanation="e", suggested_action="s")

        im = InsightsManager()
        im._sllm = mock.Mock()
        im._sllm.create = fake_create

        report = await im.analyze_anomaly("n1", db, FakeNodeManager(node))
        assert report.headline == "h"

        content = captured["messages"][0]["content"]
        lines = content.split("\n")

        def extract(prefix: str):
            line = next(l for l in lines if l.startswith(prefix))
            return json.loads(line[len(prefix):])

        services_parsed = extract("- Active Services: ")
        containers_parsed = extract("- Active Containers: ")
        assert len(services_parsed) <= 20
        assert len(containers_parsed) <= 20
        # Preferred entries come first: with 25 active / 25 inactive, the
        # trimmed 20 must be entirely active (resp. running).
        assert all(s["state"] == "active" for s in services_parsed)
        assert all(c["state"] == "running" for c in containers_parsed)

def test_trim_json_entries_caps_and_prefers_active():
    items = [{"service": f"s{i}", "state": "inactive"} for i in range(30)]
    out = json.loads(InsightsManager._trim_json_entries(json.dumps(items), preferred_state="active"))
    assert len(out) == 20
    assert out[0]["state"] == "inactive"

def test_trim_json_entries_prefers_running_via_status():
    items = [
        {"name": "a", "state": "exited", "status": "Exited (0)"},
        {"name": "b", "state": "running", "status": "Up 3 hours"},
        {"name": "c", "state": "created", "status": "Up 1 hour"},
    ]
    out = json.loads(InsightsManager._trim_json_entries(json.dumps(items), preferred_state="running"))
    assert out[0]["name"] == "b"
    assert out[1]["name"] == "c"  # "up" in status string counts as running

def test_trim_json_entries_malformed_falls_back_to_truncated():
    raw = "not-json-" + "x" * 10000
    out = InsightsManager._trim_json_entries(raw, preferred_state="active")
    assert out == raw[:6000]

def test_diagnostic_report_enforces_max_lengths():
    with pytest.raises(Exception):
        DiagnosticReport(headline="h" * 201, explanation="e", suggested_action="s")
    with pytest.raises(Exception):
        DiagnosticReport(headline="h", explanation="e" * 4001, suggested_action="s")
    with pytest.raises(Exception):
        DiagnosticReport(headline="h", explanation="e", suggested_action="s" * 1001)
    with pytest.raises(Exception):
        DiagnosticReport(
            headline="h", explanation="e", suggested_action="s",
            correlated_cause=[f"c{i}" for i in range(21)],
        )
    ok = DiagnosticReport(headline="h", explanation="e", suggested_action="s")
    assert ok.correlated_cause == []

