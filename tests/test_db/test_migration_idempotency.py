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
                assert row[0] == 1, "Expected exactly 1 alembic_version row after first run"

            await close_db()

            # Second run
            await reset_db()
            conn2 = await init_db(db_path)
            await run_migrations(conn2)

            async with conn2.execute("SELECT COUNT(*) FROM alembic_version") as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == 1, "Expected exactly 1 alembic_version row after second run"

            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_alembic_version_value(self) -> None:
        """The stamped version must be '004' (latest Alembic revision)."""
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test.db")
            await reset_db()
            conn = await init_db(db_path)
            await run_migrations(conn)

            async with conn.execute("SELECT version_num FROM alembic_version LIMIT 1") as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == "006", f"Expected version 006, got {row[0]}"

            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)
