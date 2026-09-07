from __future__ import annotations

import time
import pytest

from master.core.action_proposal import ActionProposal
from master.core.node_manager import NodeManager
from master.core.plugin_base import PluginContext
from master.plugins.metrics import (
    MetricsPlugin,
    _metrics_buffer,
    _on_status_report,
    flush_all,
    flush_metrics,
    purge_old_metrics,
)
from master.core.proposal_autoexpire import _check_metric_resolved


@pytest.mark.asyncio
async def test_metrics_buffer_and_batch_flush(db):
    """CB-5: Snapshots are buffered in memory and flushed to SQLite via executemany."""
    # Ensure buffer is empty
    _metrics_buffer.clear()

    # Insert node
    now = time.time()
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) VALUES ('node-buff', 'test', 'CONNECTED', ?, ?)",
        (now, now),
    )
    await db.commit()

    # Simulate 5 status reports arriving
    for i in range(5):
        snap = {
            "cpu_percent": 10.0 + i,
            "mem_percent": 20.0 + i,
            "disk_percent": 30.0,
            "uptime_seconds": 1000.0 + i,
        }
        await _on_status_report("node-buff", snap, db=db)

    # Check buffer contains 5 items
    assert len(_metrics_buffer) == 5

    # Check nothing committed to DB yet
    cursor = await db.execute(
        "SELECT COUNT(*) FROM metrics_snapshots WHERE node_id = 'node-buff'"
    )
    row = await cursor.fetchone()
    assert row[0] == 0

    # Trigger flush_all
    flushed = await flush_all(db=db)
    assert flushed == 5
    assert len(_metrics_buffer) == 0

    # Check DB now contains 5 items
    cursor = await db.execute(
        "SELECT COUNT(*) FROM metrics_snapshots WHERE node_id = 'node-buff'"
    )
    row = await cursor.fetchone()
    assert row[0] == 5


@pytest.mark.asyncio
async def test_metrics_purge_old_records(db):
    """CB-5: purge_old_metrics deletes records older than retention_days in batches."""
    now = time.time()
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) VALUES ('node-purge', 'test', 'CONNECTED', ?, ?)",
        (now, now),
    )

    # Insert 15 old records (35 days old)
    old_time = now - 35 * 86400
    for i in range(15):
        await db.execute(
            "INSERT INTO metrics_snapshots (id, node_id, collected_at, created_at, cpu_percent, mem_percent, disk_percent, uptime_seconds) "
            "VALUES (?, 'node-purge', ?, ?, 10.0, 20.0, 30.0, 100.0)",
            (f"old-snap-{i}", old_time + i, old_time + i),
        )

    # Insert 3 recent records (1 day old)
    recent_time = now - 1 * 86400
    for i in range(3):
        await db.execute(
            "INSERT INTO metrics_snapshots (id, node_id, collected_at, created_at, cpu_percent, mem_percent, disk_percent, uptime_seconds) "
            "VALUES (?, 'node-purge', ?, ?, 10.0, 20.0, 30.0, 100.0)",
            (f"recent-snap-{i}", recent_time + i, recent_time + i),
        )
    await db.commit()

    # Purge with batch_size=5, retention_days=30
    purged = await purge_old_metrics(db=db, retention_days=30, batch_size=5)
    assert purged == 15

    # Verify only recent records remain
    cursor = await db.execute(
        "SELECT COUNT(*) FROM metrics_snapshots WHERE node_id = 'node-purge'"
    )
    row = await cursor.fetchone()
    assert row[0] == 3


@pytest.mark.asyncio
async def test_node_manager_latest_metrics_cache():
    """CB-6: NodeManager caches latest_metrics in memory without DB queries."""
    nm = NodeManager()
    assert nm.get_latest_metrics("node-123") is None

    metrics_payload = {
        "cpu_percent": 42.5,
        "mem_percent": 68.0,
        "disks": [{"mount_point": "/srv", "device": "/dev/sda1"}],
    }
    nm.set_latest_metrics("node-123", metrics_payload)

    cached = nm.get_latest_metrics("node-123")
    assert cached is not None
    assert cached["cpu_percent"] == 42.5
    assert cached["disks"][0]["mount_point"] == "/srv"


@pytest.mark.asyncio
async def test_proposal_autoexpire_reads_from_node_manager_first(db):
    """CB-6: _check_metric_resolved reads from NodeManager memory before SQL fallback."""
    nm = NodeManager()
    node_id = "node-autoexpire-test"
    proposal = ActionProposal(
        node_id=node_id,
        action="RESTART_SERVICE",
        params={"service": "nginx"},
        reasoning="Charge CPU trop élevée sur ce noeud",
    )

    # Set metric above threshold (> 60% METRIC_OK_THRESHOLD)
    nm.set_latest_metrics(node_id, {"cpu_percent": 85.0})
    reason = await _check_metric_resolved(db, proposal, nm=nm)
    assert reason is None

    # Set metric below threshold (resolved)
    nm.set_latest_metrics(node_id, {"cpu_percent": 30.0})
    reason = await _check_metric_resolved(db, proposal, nm=nm)
    assert reason is not None
    assert "cpu_percent à 30.0%" in reason


@pytest.mark.asyncio
async def test_metrics_plugin_class_methods(db):
    """MetricsPlugin class exposes flush_all and purge_old_metrics."""
    ctx = PluginContext(plugin_id="metrics", config={}, db=db)
    plugin = MetricsPlugin(ctx)
    flushed = await plugin.flush_all(db=db)
    assert isinstance(flushed, int)

    purged = await plugin.purge_old_metrics(db=db, retention_days=30)
    assert isinstance(purged, int)
