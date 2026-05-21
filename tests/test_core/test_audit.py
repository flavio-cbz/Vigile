import os
import pytest
import aiosqlite
from master.core.audit import log_action, verify_chain, get_recent_entries


@pytest.mark.asyncio
async def test_audit_trail(db: aiosqlite.Connection):
    # Log several actions
    e1 = await log_action(db, user_id="user-1", action="TEST_ACTION_A", node_id="node-1", details={"k": "v1"})
    e2 = await log_action(db, user_id="user-2", action="TEST_ACTION_B", node_id="node-2", details={"k": "v2"})
    e3 = await log_action(db, user_id="user-1", action="TEST_ACTION_C", details={"k": "v3"})

    assert all(isinstance(e, str) and len(e) == 36 for e in [e1, e2, e3])

    # Verify chain
    report = await verify_chain(db)
    assert report["valid"]
    assert report["total_entries"] >= 4

    # Tamper with an entry and verify detection
    async with db.execute("SELECT id, entry_hash FROM audit_log ORDER BY sequence DESC LIMIT 1") as cur:
        last = await cur.fetchone()

    await db.execute("UPDATE audit_log SET details_json='{\"tampered\":true}' WHERE id=?", (last["id"],))
    await db.commit()

    tampered_report = await verify_chain(db)
    assert not tampered_report["valid"]
    assert tampered_report["first_broken_sequence"] is not None

    # Recent entries
    entries = await get_recent_entries(db, limit=5)
    assert isinstance(entries, list)
    assert all("entry_hash" in e for e in entries)
