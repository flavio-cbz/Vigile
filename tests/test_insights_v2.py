import asyncio
import time
import pytest
import aiosqlite

from master.core.insights import InsightsManager, OBSERVATION_THRESHOLDS, DataWindow
from master.core.node_manager import NodeManager


@pytest.mark.asyncio
async def test_observation_thresholds_per_type():
    """Verify that OBSERVATION_THRESHOLDS contains expected values for each insight type."""
    assert OBSERVATION_THRESHOLDS["cpu"] == 2.0
    assert OBSERVATION_THRESHOLDS["ram"] == 2.0
    assert OBSERVATION_THRESHOLDS["disk"] == 24.0
    assert OBSERVATION_THRESHOLDS["profile"] == 24.0


@pytest.mark.asyncio
async def test_insights_cache_and_invalidation():
    """Verify in-memory 5 min cache and explicit invalidation."""
    im = InsightsManager()
    node_id = "test-node-cache-123"

    # Pre-populate cache
    im._insights_cache[node_id] = (time.time(), {"test": "data"})
    assert node_id in im._insights_cache

    # Invalidate cache
    im.invalidate_cache(node_id)
    assert node_id not in im._insights_cache


@pytest.mark.asyncio
async def test_cpu_drift_detection(tmp_path):
    """Test NodeManager._check_cpu_drift logic."""
    db_path = tmp_path / "test_drift.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE metrics_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                collected_at REAL NOT NULL,
                cpu_percent REAL NOT NULL
            )
            """
        )
        await db.commit()

        nm = NodeManager()
        node_id = "node-drift-1"
        now = time.time()

        # Insert 10 older snapshots with low CPU (~10%)
        for i in range(10):
            await db.execute(
                "INSERT INTO metrics_snapshots (node_id, collected_at, cpu_percent) VALUES (?, ?, ?)",
                (node_id, now - 3600 + (i * 60), 10.0),
            )

        # Insert 10 recent snapshots with high CPU (~80%) -> Drift delta = 70 points > 30
        for i in range(10):
            await db.execute(
                "INSERT INTO metrics_snapshots (node_id, collected_at, cpu_percent) VALUES (?, ?, ?)",
                (node_id, now - 600 + (i * 60), 80.0),
            )
        await db.commit()

        drift_detected = await nm._check_cpu_drift(node_id, db)
        assert drift_detected is True

        # Test no drift case
        node_id_stable = "node-stable-1"
        for i in range(20):
            await db.execute(
                "INSERT INTO metrics_snapshots (node_id, collected_at, cpu_percent) VALUES (?, ?, ?)",
                (node_id_stable, now - 1200 + (i * 60), 15.0),
            )
        await db.commit()

        stable_drift = await nm._check_cpu_drift(node_id_stable, db)
        assert stable_drift is False
