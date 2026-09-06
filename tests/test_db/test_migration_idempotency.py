from __future__ import annotations

import os
import shutil
import tempfile

import aiosqlite
import pytest

from master.db.database import close_db, init_db, reset_db
from master.db.migrations import run_migrations


class TestMigrationIdempotency:
    """BH-01: run_migrations() must be idempotent — running it twice on the
    same database must not raise."""

    @pytest.mark.asyncio
    async def test_run_twice_no_error(self) -> None:
        """Running migrations on a fresh DB twice must succeed both times."""
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test.db")
            await reset_db()
            conn = await init_db(db_path)

            await run_migrations(conn)
            await close_db()

            # Second run on same DB — must not raise
            await reset_db()
            conn2 = await init_db(db_path)
            try:
                await run_migrations(conn2)
            finally:
                await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_alembic_version_stamped_once(self) -> None:
        """alembic_version table must contain exactly one row after two runs."""
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test.db")
            await reset_db()
            conn = await init_db(db_path)

            await run_migrations(conn)

            async with conn.execute("SELECT COUNT(*) FROM alembic_version") as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == 1, f"Expected exactly 1 alembic_version row after first run, got {row[0]}"

            await close_db()

            # Second run
            await reset_db()
            conn2 = await init_db(db_path)
            await run_migrations(conn2)

            async with conn2.execute("SELECT COUNT(*) FROM alembic_version") as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == 1, f"Expected exactly 1 alembic_version row after second run, got {row[0]}"

            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_run_ten_times_schema_identical(self) -> None:
        """Running migrations 10 times consecutively must not alter sqlite_master DDL catalog."""
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test.db")
            await reset_db()
            conn = await init_db(db_path)
            await run_migrations(conn)

            # Snapshot DDL catalog after run 1
            async with conn.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
            ) as cursor:
                initial_schema = await cursor.fetchall()
            assert len(initial_schema) > 0

            # Run 9 more times
            for _ in range(9):
                await run_migrations(conn)

            async with conn.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
            ) as cursor:
                subsequent_schema = await cursor.fetchall()

            assert subsequent_schema == initial_schema, "DDL catalog altered across successive migration runs"

            # Check alembic_version strictly has 1 row with '010'
            async with conn.execute("SELECT version_num FROM alembic_version") as cursor:
                rows = await cursor.fetchall()
                assert len(rows) == 1
                assert rows[0][0] == "010"

            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_alembic_version_value(self) -> None:
        """The stamped version must contain the latest Alembic revision."""
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test.db")
            await reset_db()
            conn = await init_db(db_path)
            await run_migrations(conn)

            async with conn.execute("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1") as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] >= "009", f"Expected version >= 009, got {row[0]}"

            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_action_proposals_columns_added_to_legacy_db(self) -> None:
        """Legacy action_proposals tables missing dispatch_id/intent_id/expires_at must be migrated."""
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "legacy.db")
            await reset_db()
            conn = await init_db(db_path)
            # Create a legacy action_proposals table lacking dispatch_id, intent_id, expires_at
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS action_proposals (
                    id TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    params_json TEXT NOT NULL DEFAULT '{}',
                    reasoning TEXT NOT NULL,
                    risk_level TEXT NOT NULL DEFAULT 'MEDIUM',
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_by TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            await conn.commit()

            # Run migrations
            await run_migrations(conn)

            async with conn.execute("PRAGMA table_info(action_proposals)") as cursor:
                cols = {row["name"] for row in await cursor.fetchall()}
                assert "dispatch_id" in cols
                assert "intent_id" in cols
                assert "expires_at" in cols

            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_alembic_version_unconditional_uniqueness_with_duplicates(self) -> None:
        """
        Garantie d'unicité inconditionnelle :
        Injecting 3 '010' rows and 2 older version rows into alembic_version
        without primary key constraint, then running run_migrations() must
        leave strictly 1 row with value '010'.
        """
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test_duplicates.db")
            await reset_db()
            conn = await init_db(db_path)

            # Create alembic_version table WITHOUT primary key or unique constraint
            await conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
            # Deliberately inject 3 '010' rows and 2 older version rows
            for ver in ["010", "010", "010", "008", "009"]:
                await conn.execute("INSERT INTO alembic_version (version_num) VALUES (?)", (ver,))
            await conn.commit()

            # Verify initial state has 5 rows
            async with conn.execute("SELECT COUNT(*) FROM alembic_version") as cursor:
                row = await cursor.fetchone()
                assert row is not None and row[0] == 5

            # Run migrations
            await run_migrations(conn)

            # Verify that SELECT COUNT(*) FROM alembic_version is strictly 1
            async with conn.execute("SELECT COUNT(*) FROM alembic_version") as cursor:
                count_row = await cursor.fetchone()
                assert count_row is not None
                assert count_row[0] == 1, f"Expected strictly 1 row in alembic_version, got {count_row[0]}"

            # Verify that the single row has value '010'
            async with conn.execute("SELECT version_num FROM alembic_version") as cursor:
                rows = await cursor.fetchall()
                assert len(rows) == 1
                assert rows[0][0] == "010", f"Expected version_num '010', got {rows[0][0]}"

            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_migration_rebuild_fk_violation_raises(self) -> None:
        """If foreign_key_check detects violations during table rebuild, it raises RuntimeError and rolls back."""
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test_fk.db")
            await reset_db()
            conn = await init_db(db_path)
            # Create a table with an FK constraint and insert an orphaned row with FKs off
            await conn.execute("PRAGMA foreign_keys=OFF")
            await conn.execute("CREATE TABLE parent (id TEXT PRIMARY KEY)")
            await conn.execute("CREATE TABLE child (id TEXT PRIMARY KEY, parent_id TEXT, FOREIGN KEY(parent_id) REFERENCES parent(id))")
            await conn.execute("INSERT INTO child VALUES ('c1', 'nonexistent')")
            await conn.commit()
            await conn.execute("PRAGMA foreign_keys=ON")

            # Also create join_tokens with an FK to nodes so _drop_join_tokens_fk_if_present triggers
            await conn.execute("CREATE TABLE nodes (id TEXT PRIMARY KEY)")
            await conn.execute("""
                CREATE TABLE join_tokens (
                    id TEXT PRIMARY KEY, node_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE, payload_b64 TEXT NOT NULL,
                    consumed INTEGER NOT NULL DEFAULT 0, expires_at REAL NOT NULL, created_at REAL NOT NULL,
                    FOREIGN KEY (node_id) REFERENCES nodes(id)
                )
            """)
            await conn.commit()

            from master.db.migrations import _drop_join_tokens_fk_if_present
            with pytest.raises(RuntimeError, match="Foreign key violations detected"):
                await _drop_join_tokens_fk_if_present(conn)

            # Ensure PRAGMA foreign_keys is restored to ON
            async with conn.execute("PRAGMA foreign_keys") as cursor:
                row = await cursor.fetchone()
                assert row is not None and row[0] == 1

            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)



