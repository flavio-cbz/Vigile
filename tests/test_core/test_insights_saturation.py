import time
import pytest
import aiosqlite
from master.core.insights import InsightsManager

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
