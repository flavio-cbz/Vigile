import time
import pytest
import aiosqlite

from master.core.insights import calculate_node_baseline


@pytest.mark.asyncio
async def test_calculate_node_baseline_empty(tmp_path):
    """Verify calculate_node_baseline returns limited status when no metrics exist."""
    db_path = tmp_path / "test_baseline_empty.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE metrics_snapshots (
                id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL,
                collected_at REAL NOT NULL,
                cpu_percent REAL,
                mem_percent REAL,
                disk_percent REAL
            )
            """
        )
        await db.commit()

        res = await calculate_node_baseline(db, "node-empty-1")
        assert res["node_id"] == "node-empty-1"
        assert res["is_limited"] is True
        assert res["metrics"]["cpu"]["absolute_critical"] == 95.0


@pytest.mark.asyncio
async def test_calculate_node_baseline_with_history(tmp_path):
    """Verify calculate_node_baseline calculates percentiles correctly over 4 days of history."""
    db_path = tmp_path / "test_baseline.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE metrics_snapshots (
                id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL,
                collected_at REAL NOT NULL,
                cpu_percent REAL,
                mem_percent REAL,
                disk_percent REAL
            )
            """
        )
        node_id = "node-baseline-1"
        now = time.time()
        start_ts = now - (4 * 86400)  # 4 days ago

        # Insert 100 snapshots spanning 4 days
        for i in range(100):
            ts = start_ts + (i * 3456)
            cpu = 10.0 + (i % 30)  # CPU 10% to 40%
            ram = 40.0 + (i % 20)  # RAM 40% to 60%
            disk = 50.0 + (i * 0.1)
            await db.execute(
                "INSERT INTO metrics_snapshots (id, node_id, collected_at, cpu_percent, mem_percent, disk_percent) VALUES (?, ?, ?, ?, ?, ?)",
                (f"snap-{i}", node_id, ts, cpu, ram, disk),
            )
        await db.commit()

        res = await calculate_node_baseline(db, node_id)
        assert res["node_id"] == node_id
        assert res["is_limited"] is False
        assert res["data_window_hours"] >= 72.0
        assert "p75" in res["metrics"]["cpu"]
        assert "p90" in res["metrics"]["cpu"]
        assert "p99" in res["metrics"]["cpu"]
        assert res["metrics"]["cpu"]["p75"] >= res["metrics"]["cpu"]["mean"]
