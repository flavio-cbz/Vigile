import pytest
import aiosqlite


@pytest.mark.asyncio
async def test_db_setup_and_migrations(db: aiosqlite.Connection):
    assert db is not None

    # Check all tables exist
    for table in ["nodes", "join_tokens", "worker_tokens", "users", "audit_log"]:
        async with db.execute(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None, f"Table {table} should exist"

    # Check admin user was seeded
    async with db.execute("SELECT username, role FROM users WHERE username='admin'") as cur:
        user = await cur.fetchone()
    assert user is not None
    assert user["role"] == "admin"

    # Check audit genesis entry
    async with db.execute("SELECT sequence, action, previous_hash FROM audit_log ORDER BY sequence") as cur:
        first = await cur.fetchone()
    assert first is not None
    assert first["sequence"] == 1
    assert first["previous_hash"] == "0" * 64
