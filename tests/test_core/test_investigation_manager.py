from __future__ import annotations

import asyncio
import json
import os
import time
from types import SimpleNamespace

import pytest

from master.core.investigation_manager import InvestigationManager, investigation_manager
from master.db.database import close_db, init_db, reset_db
from master.db.migrations import run_migrations
from master.endpoints import health_check


async def _seed_node(db, node_id: str) -> None:
    now = time.time()
    await db.execute(
        "INSERT INTO nodes (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (node_id, f"node-{node_id}", now, now),
    )
    await db.commit()


async def _seed_alert(db, alert_id: str, node_id: str) -> None:
    now = time.time()
    await db.execute(
        "INSERT INTO alerts (id, node_id, alert_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (alert_id, node_id, "disk_usage_high", now, now),
    )
    await db.commit()


async def _call_alert(
    mgr: InvestigationManager,
    db,
    *,
    alert_id: str,
    node_id: str = "node-1",
    message: str = "Disk usage above 90%",
) -> str | None:
    return await mgr.on_alert_fired(
        node_id=node_id,
        alert_name="disk_usage_high",
        severity="critical",
        message=message,
        alert_id=alert_id,
        db=db,
        details={"disk": "/"},
    )


async def _wait_idle(mgr: InvestigationManager, timeout: float = 5.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while mgr._background_tasks and loop.time() < deadline:
        await asyncio.sleep(0.02)
    await mgr.ensure_tasks_complete(timeout=1.0)


class TestOnAlertFired:
    @pytest.mark.asyncio
    async def test_queues_investigation_and_releases_reservation(self, db) -> None:
        """on_alert_fired inserts a 'queued' record, returns its id, and frees
        the reservation once the background investigation completes."""
        mgr = InvestigationManager(max_concurrent=2)
        await _seed_node(db, "node-1")
        await _seed_alert(db, "alert-1", "node-1")

        iid = await _call_alert(mgr, db, alert_id="alert-1")
        assert iid is not None

        async with db.execute(
            "SELECT * FROM investigations WHERE id = ?", (iid,)
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        row = dict(row)
        assert row["node_id"] == "node-1"
        assert row["alert_name"] == "disk_usage_high"
        ctx = json.loads(row["context_json"])
        assert ctx["alert_id"] == "alert-1"

        # Background task runs with its own pooled connection; once idle the
        # reservation must be released (second alert is NOT dropped).
        await _wait_idle(mgr)
        assert mgr._reserved == 0
        await _seed_alert(db, "alert-2", "node-1")
        iid2 = await _call_alert(mgr, db, alert_id="alert-2")
        assert iid2 is not None
        await _wait_idle(mgr)
        assert mgr.dropped_count == 0

    @pytest.mark.asyncio
    async def test_cap_reached_persists_dropped_record(self, db, monkeypatch) -> None:
        """When the cap is reached, on_alert_fired persists a 'dropped' record
        and increments dropped_count instead of silently returning None."""
        mgr = InvestigationManager(max_concurrent=1)
        await _seed_node(db, "node-1")
        await _seed_alert(db, "alert-1", "node-1")
        await _seed_alert(db, "alert-2", "node-1")

        started = asyncio.Event()
        release = asyncio.Event()

        async def holding_run(inv_id: str, node_id: str) -> None:
            started.set()
            await release.wait()

        monkeypatch.setattr(mgr, "_run_investigation", holding_run)

        iid1 = await _call_alert(mgr, db, alert_id="alert-1", message="first")
        assert iid1 is not None
        await asyncio.wait_for(started.wait(), timeout=2.0)

        # In-flight investigation keeps status 'queued' (fake never updates it)
        async with db.execute(
            "SELECT status FROM investigations WHERE id = ?", (iid1,)
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None and row["status"] == "queued"

        iid2 = await _call_alert(mgr, db, alert_id="alert-2", message="second")
        assert iid2 is None
        assert mgr.dropped_count == 1

        async with db.execute(
            "SELECT * FROM investigations WHERE status = 'dropped'"
        ) as cursor:
            rows = [dict(r) for r in await cursor.fetchall()]
        assert len(rows) == 1
        dropped = rows[0]
        assert dropped["alert_id"] == "alert-2"
        ctx = json.loads(dropped["context_json"])
        assert ctx["alert_id"] == "alert-2"
        assert ctx["message"] == "second"
        result = json.loads(dropped["result"])
        assert result["status"] == "dropped"
        assert "queue full (1/1)" in result["reason"]

        release.set()
        await mgr.ensure_tasks_complete(timeout=2.0)


class TestMigration:
    @pytest.mark.asyncio
    async def test_check_accepts_dropped_after_migrations(self, db) -> None:
        """After run_migrations, the investigations CHECK constraint accepts
        status='dropped' (insert + select round-trip)."""
        await _seed_node(db, "node-1")
        now = time.time()
        await db.execute(
            """INSERT INTO investigations
               (id, alert_id, node_id, alert_name, severity, status,
                context_json, result, created_at, updated_at)
               VALUES (?, NULL, 'node-1', 'disk_usage_high', 'critical',
                       'dropped', '{}', ?, ?, ?)""",
            (
                "inv-drop-1",
                json.dumps({"status": "dropped", "reason": "queue full"}),
                now,
                now,
            ),
        )
        await db.commit()

        async with db.execute(
            "SELECT status, result FROM investigations WHERE id = 'inv-drop-1'"
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        assert row["status"] == "dropped"
        assert json.loads(row["result"])["status"] == "dropped"

    @pytest.mark.asyncio
    async def test_old_schema_rebuilt_idempotently(self, temp_dir) -> None:
        """A DB whose investigations table has the OLD CHECK constraint is
        rebuilt by the migration: data survives, 'dropped' becomes accepted,
        indexes are recreated, and a second run is a no-op."""
        db_path = os.path.join(temp_dir, "migrate.db")
        await reset_db()
        conn = await init_db(db_path)
        try:
            await conn.execute(
                """CREATE TABLE investigations (
                    id            TEXT PRIMARY KEY,
                    alert_id      TEXT,
                    node_id       TEXT NOT NULL,
                    alert_name    TEXT NOT NULL,
                    severity      TEXT NOT NULL DEFAULT 'warning',
                    status        TEXT NOT NULL DEFAULT 'queued'
                                  CHECK(status IN ('queued', 'in_progress', 'completed', 'failed')),
                    context_json  TEXT NOT NULL DEFAULT '{}',
                    result        TEXT,
                    created_at    REAL NOT NULL,
                    completed_at  REAL,
                    updated_at    REAL NOT NULL
                )"""
            )
            await conn.execute(
                "INSERT INTO investigations (id, node_id, alert_name, status, created_at, updated_at) "
                "VALUES ('legacy-1', 'node-legacy', 'old_alert', 'completed', 1.0, 1.0)"
            )
            await conn.commit()

            await run_migrations(conn)

            # Legacy row survived the rebuild
            async with conn.execute(
                "SELECT status FROM investigations WHERE id = 'legacy-1'"
            ) as cursor:
                row = await cursor.fetchone()
            assert row is not None and row["status"] == "completed"

            # The three indexes were recreated on the rebuilt table
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_investigations%'"
            ) as cursor:
                idxs = {r[0] for r in await cursor.fetchall()}
            assert idxs == {
                "idx_investigations_node",
                "idx_investigations_status",
                "idx_investigations_alert",
            }

            # 'dropped' is now accepted (FK on node_id enforced → seed node)
            now = time.time()
            await conn.execute(
                "INSERT INTO nodes (id, name, created_at, updated_at) VALUES ('node-legacy', 'n', ?, ?)",
                (now, now),
            )
            await conn.execute(
                "INSERT INTO investigations (id, node_id, alert_name, status, created_at, updated_at) "
                "VALUES ('drop-1', 'node-legacy', 'x', 'dropped', ?, ?)",
                (now, now),
            )
            await conn.commit()

            # Idempotent: a second run must not raise nor duplicate rows
            await run_migrations(conn)
            async with conn.execute("SELECT COUNT(*) FROM investigations") as cursor:
                assert (await cursor.fetchone())[0] == 2
        finally:
            await close_db()
            await reset_db()


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_includes_dropped_counter(self) -> None:
        """The /health payload exposes the investigations-dropped counter."""
        app = SimpleNamespace(state=SimpleNamespace(startup_time=time.time()))
        request = SimpleNamespace(app=app)

        resp = await health_check(request)
        payload = json.loads(resp.body)

        assert "investigations_dropped" in payload
        assert payload["investigations_dropped"] == investigation_manager.dropped_count
