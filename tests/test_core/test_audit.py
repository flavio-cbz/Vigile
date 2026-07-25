from __future__ import annotations

import os

import aiosqlite
import pytest

from master.core.audit import compute_entry_hash, get_recent_entries, log_action, verify_chain


@pytest.mark.asyncio
async def test_audit_trail(db: aiosqlite.Connection):
    # Log several actions
    e1 = await log_action(
        db, user_id="user-1", action="TEST_ACTION_A", node_id="node-1", details={"k": "v1"}
    )
    e2 = await log_action(
        db, user_id="user-2", action="TEST_ACTION_B", node_id="node-2", details={"k": "v2"}
    )
    e3 = await log_action(db, user_id="user-1", action="TEST_ACTION_C", details={"k": "v3"})

    assert all(isinstance(e, str) and len(e) == 36 for e in [e1, e2, e3])

    # Verify chain
    report = await verify_chain(db)
    assert report["valid"]
    assert report["total_entries"] >= 4

    # Verify chain with max_entries
    report_limit = await verify_chain(db, max_entries=2)
    assert report_limit["valid"]
    assert report_limit["total_entries"] == 2

    # Tamper with an entry (change details) and verify detection
    async with db.execute(
        "SELECT id, entry_hash FROM audit_log ORDER BY sequence DESC LIMIT 1"
    ) as cur:
        last = await cur.fetchone()

    await db.execute(
        "UPDATE audit_log SET details_json='{\"tampered\":true}' WHERE id=?", (last["id"],)
    )
    await db.commit()

    tampered_report = await verify_chain(db)
    assert not tampered_report["valid"]
    assert tampered_report["first_broken_sequence"] is not None

    # Recent entries with filtering
    entries = await get_recent_entries(db, limit=5, node_id="node-1")
    assert len(entries) == 1
    assert entries[0]["user_id"] == "user-1"

    entries_user = await get_recent_entries(db, limit=5, user_id="user-2")
    assert len(entries_user) == 1
    assert entries_user[0]["node_id"] == "node-2"


@pytest.mark.asyncio
async def test_audit_trail_empty_db(temp_dir):
    # Create empty database to test empty cases
    db_path = os.path.join(temp_dir, "empty_audit.db")
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE audit_log (
                id TEXT PRIMARY KEY,
                sequence INTEGER UNIQUE,
                timestamp REAL,
                user_id TEXT,
                action TEXT,
                node_id TEXT,
                details_json TEXT,
                previous_hash TEXT,
                entry_hash TEXT
            )
            """)
        await db.commit()

        # 1. verify_chain on empty DB
        report = await verify_chain(db)
        assert report["valid"] is True
        assert report["total_entries"] == 0

        # 2. log_action on empty DB (Genesis case where head is None)
        e1 = await log_action(db, user_id="system", action="GENESIS_TEST")
        assert isinstance(e1, str)

        # Verify it has sequence 1
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT sequence, previous_hash FROM audit_log WHERE id=?", (e1,)
        ) as cur:
            row = await cur.fetchone()
            assert row["sequence"] == 1
            assert row["previous_hash"] == "0" * 64


@pytest.mark.asyncio
async def test_audit_trail_tamper_previous_hash(db: aiosqlite.Connection):
    # Log two actions
    await log_action(db, user_id="user-1", action="A")
    e2 = await log_action(db, user_id="user-2", action="B")

    # Tamper with the previous_hash of e2
    await db.execute("UPDATE audit_log SET previous_hash='invalid_prev_hash' WHERE id=?", (e2,))
    await db.commit()

    report = await verify_chain(db)
    assert report["valid"] is False
    assert "previous_hash mismatch" in report["error"]
