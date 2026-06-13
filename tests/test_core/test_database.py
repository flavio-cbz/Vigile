import aiosqlite
import pytest


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
    async with db.execute(
        "SELECT sequence, action, previous_hash FROM audit_log ORDER BY sequence"
    ) as cur:
        first = await cur.fetchone()
    assert first is not None
    assert first["sequence"] == 1
    assert first["previous_hash"] == "0" * 64


@pytest.mark.asyncio
async def test_db_already_initialized(db: aiosqlite.Connection):
    import master.db.database as db_mod

    with pytest.raises(RuntimeError) as excinfo:
        await db_mod.init_db("some_path.db")
    assert "already initialized" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_db_not_initialized():
    import master.db.database as db_mod

    # Temporarily clear _db
    orig = db_mod._db
    db_mod._db = None
    try:
        with pytest.raises(RuntimeError) as excinfo:
            db_mod.get_db_conn()
        assert "not initialized" in str(excinfo.value).lower()
    finally:
        db_mod._db = orig


@pytest.mark.asyncio
async def test_db_reset_active_connection():
    import os
    import tempfile

    import master.db.database as db_mod

    # Create an active connection
    fd, path = tempfile.mkstemp()
    os.close(fd)
    try:
        # Save current connection
        orig = db_mod._db
        db_mod._db = None
        conn = await db_mod.init_db(path)
        assert db_mod._db is not None
        await db_mod.reset_db()
        assert db_mod._db is None
    finally:
        db_mod._db = orig
        try:
            os.remove(path)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_db_transaction_rollback(db: aiosqlite.Connection):
    import master.db.database as db_mod

    # Try inserting a node but raise an error inside transaction
    with pytest.raises(ValueError):
        async with db_mod.transaction(db) as conn:
            await conn.execute(
                "INSERT INTO nodes (id, name, state, created_at, updated_at) VALUES ('nod-tx', 'Tx Test', 'PENDING', 0, 0)"
            )
            raise ValueError("Forced error")

    # Verify node was not inserted
    async with db.execute("SELECT id FROM nodes WHERE id = 'nod-tx'") as cur:
        row = await cur.fetchone()
    assert row is None


@pytest.mark.asyncio
async def test_db_connection_pool(db: aiosqlite.Connection):
    import master.db.database as db_mod

    # database_session should acquire from pool and set contextvar
    async with db_mod.database_session() as conn1:
        assert db_mod.get_db_conn() == conn1

        async with db_mod.database_session() as conn2:
            assert db_mod.get_db_conn() == conn2
            assert conn1 != conn2

        assert db_mod.get_db_conn() == conn1

    # After exiting all sessions, get_db_conn should fallback to primary connection
    assert db_mod.get_db_conn() == db_mod._db
