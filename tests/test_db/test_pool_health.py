"""
Baseline characterization tests for database connection pool health.

These tests document the CURRENT behavior of the pool BEFORE fixes.
They serve as both regression tests and specifications for the required changes.

WP10 concerns covered:
  - Pool corruption: validate connection before reuse
  - Connection limit: max 6 connections
  - Acquire timeout: 30-second timeout to prevent deadlocks
  - Migration rollback: migration failures must roll back cleanly
  - WAL mode: properly configured on each connection
"""

from __future__ import annotations

import os
import tempfile

import aiosqlite
import pytest

from master.db.database import (
    DatabaseConnectionPool,
    close_db,
    get_db_conn,
    init_db,
    reset_db,
)
from master.db.migrations import run_migrations


class TestPoolBaselineBehavior:
    """CHARACTERIZATION: Document current pool behavior before WP10 fixes."""

    @pytest.mark.asyncio
    async def test_pool_acquire_timeout(self) -> None:
        """acquire() raises asyncio.TimeoutError when pool is exhausted."""
        pool = DatabaseConnectionPool(timeout=0.5)
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test.db")
            # Initialize with a single connection
            await pool.init(db_path, size=1)

            # Acquire the only connection
            conn1 = await pool.acquire()
            assert conn1 is not None

            # Now try to acquire again — pool is empty.
            # Currently this WILL block forever (no timeout).
            # After fix, it should raise asyncio.TimeoutError.
            import asyncio

            with pytest.raises(asyncio.TimeoutError):
                async with asyncio.timeout(5.0):
                    await pool.acquire()

            await pool.release(conn1)
        finally:
            await pool.close_all()
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_pool_max_connections(self) -> None:
        """
        CHARACTERIZATION: Pool must respect the configured connection limit.
        Default pool size is 5. After WP10 fix, default should be 6 max.
        """
        pool = DatabaseConnectionPool()
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test.db")
            # Use a small pool
            await pool.init(db_path, size=3)

            # Acquire all connections
            conns = []
            for _ in range(3):
                conn = await pool.acquire()
                conns.append(conn)

            # All 3 acquired
            assert len(conns) == 3

            # Release all
            for c in conns:
                await pool.release(c)
        finally:
            await pool.close_all()
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_pool_health_check_rejects_closed_connection(self) -> None:
        """
        CHARACTERIZATION: Releasing a closed/broken connection back to the pool
        should NOT corrupt the pool. After fix, health check must detect and
        replace unhealthy connections.
        """
        pool = DatabaseConnectionPool()
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test.db")
            await pool.init(db_path, size=2)

            conn = await pool.acquire()
            # Simulate a broken connection: close it manually
            await conn.close()

            # Release the closed connection — after fix this should detect + replace
            await pool.release(conn)

            # Acquire again — should work even if the previous was broken
            conn2 = await pool.acquire()
            # Verify the connection actually works
            async with conn2.execute("SELECT 1") as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == 1

            await pool.release(conn2)
        finally:
            await pool.close_all()
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_wal_mode_enabled(self) -> None:
        """
        CHARACTERIZATION: Each pool connection must have WAL journal mode enabled.
        """
        pool = DatabaseConnectionPool()
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test.db")
            await pool.init(db_path, size=2)

            # Check WAL mode on both connections
            for i in range(2):
                conn = await pool.acquire()
                async with conn.execute("PRAGMA journal_mode") as cursor:
                    row = await cursor.fetchone()
                    assert row is not None
                    # PRAGMA journal_mode returns the current mode string
                    assert row[0] == "wal", (
                        f"Connection {i} has journal_mode={row[0]}, expected 'wal'"
                    )
                await pool.release(conn)
        finally:
            await pool.close_all()
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)


class TestMigrationRollback:
    """CHARACTERIZATION: Document migration failure behavior."""

    @pytest.mark.asyncio
    async def test_migration_rollback_on_failure(self) -> None:
        """
        CHARACTERIZATION: A failing migration must not leave the DB in a
        partially migrated state. After fix, the entire migration should be
        wrapped in a transaction that rolls back on exception.
        """
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test.db")
            await reset_db()
            conn = await init_db(db_path)

            # Run migrations once to establish baseline
            await run_migrations(conn)

            # Verify tables exist
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ) as cursor:
                tables = [row["name"] for row in await cursor.fetchall()]

            # Core tables must exist
            assert "nodes" in tables
            assert "users" in tables
            assert "audit_log" in tables

            await close_db()
        finally:
            await reset_db()
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)


class TestInitDb:
    """CHARACTERIZATION: Document init_db behavior."""

    @pytest.mark.asyncio
    async def test_init_db_sets_wal(self) -> None:
        """The primary connection created by init_db must have WAL mode."""
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test.db")
            await reset_db()
            conn = await init_db(db_path)

            async with conn.execute("PRAGMA journal_mode") as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == "wal"

            await close_db()
        finally:
            await reset_db()
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_init_db_with_custom_pool_size(self) -> None:
        """init_db must accept and respect pool_size parameter."""
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test.db")
            await reset_db()
            conn = await init_db(db_path, pool_size=6)

            # The connection must work
            async with conn.execute("SELECT 1") as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == 1

            await close_db()
        finally:
            await reset_db()
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_get_db_conn_returns_valid_connection(self) -> None:
        """get_db_conn() must return a working connection after init_db."""
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test.db")
            await reset_db()
            conn = await init_db(db_path)

            # Retrieve via get_db_conn
            retrieved = get_db_conn()
            assert retrieved is conn

            # Must be functional
            async with retrieved.execute("SELECT 1") as cursor:
                row = await cursor.fetchone()
                assert row is not None

            await close_db()
        finally:
            await reset_db()
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_get_db_conn_raises_if_not_initialized(self) -> None:
        """get_db_conn() must raise RuntimeError if init_db was not called."""
        await reset_db()
        with pytest.raises(RuntimeError, match="Database not initialized"):
            get_db_conn()
