from __future__ import annotations

"""
Vigile — Async SQLite Connection Manager
Provides a context-managed aiosqlite connection with WAL mode enabled.
"""

import asyncio
import contextvars
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT: float = 30.0

# Module-level connection reference (fallback / migrations connection)
_db: aiosqlite.Connection | None = None
_db_ctx: contextvars.ContextVar[aiosqlite.Connection] = contextvars.ContextVar("db_conn")


class DatabaseConnectionPool:
    """
    A lightweight connection pool for aiosqlite.
    Allows concurrent reads in WAL mode across multiple connections.
    """

    def __init__(self, timeout: float | None = None) -> None:
        self._pool: asyncio.Queue[aiosqlite.Connection] | None = None
        self._connections: list[aiosqlite.Connection] = []
        self._path: str = ""
        self._timeout: float = timeout if timeout is not None else DEFAULT_TIMEOUT

    async def init(
        self,
        database_path: str,
        size: int | None = None,
        timeout: float | None = None,
        pool_size: int = 5,
    ) -> None:
        effective_size = size if size is not None else pool_size
        self._path = database_path
        self._timeout = timeout if timeout is not None else self._timeout
        # Recreate the queue in the current event loop to avoid
        # "bound to a different event loop" errors after reset_db().
        # maxsize must match pool size to avoid deadlock when size > 5.
        self._pool = asyncio.Queue(maxsize=effective_size)
        self._connections = []
        for _ in range(effective_size):
            conn = await self._create_connection()
            self._connections.append(conn)
            await self._pool.put(conn)

    async def _create_connection(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._path, timeout=getattr(self, "_timeout", DEFAULT_TIMEOUT))
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = aiosqlite.Row
        await conn.commit()
        return conn

    async def _is_healthy(self, conn: aiosqlite.Connection) -> bool:
        """Check if connection is alive and working."""
        try:
            async with conn.execute("SELECT 1") as cursor:
                row = await cursor.fetchone()
                return row is not None and row[0] == 1
        except Exception:
            return False

    async def acquire(self) -> aiosqlite.Connection:
        if self._pool is None:
            raise RuntimeError("Database connection pool not initialized. Call init_db() first.")

        try:
            conn = await asyncio.wait_for(self._pool.get(), timeout=self._timeout)
        except (asyncio.TimeoutError, TimeoutError):
            raise asyncio.TimeoutError(f"Database connection pool acquire timed out after {self._timeout}s")

        if not await self._is_healthy(conn):
            try:
                if conn in self._connections:
                    self._connections.remove(conn)
                await conn.close()
            except Exception:
                pass
            conn = await self._create_connection()
            self._connections.append(conn)
        return conn

    async def release(self, conn: aiosqlite.Connection) -> None:
        if conn in self._connections:
            if not await self._is_healthy(conn):
                try:
                    self._connections.remove(conn)
                    await conn.close()
                except Exception:
                    pass
                try:
                    conn = await self._create_connection()
                    self._connections.append(conn)
                except Exception:
                    # Retry once before failing
                    try:
                        conn = await self._create_connection()
                        self._connections.append(conn)
                    except Exception as exc:
                        logger.error("Failed to replace unhealthy connection in pool: %s", exc)
                        raise RuntimeError(f"Failed to replace unhealthy connection in pool: {exc}") from exc
            if self._pool is not None:
                await self._pool.put(conn)

    async def close_all(self) -> None:
        for conn in self._connections:
            try:
                await conn.close()
            except Exception:
                pass
        self._connections.clear()
        # Drain the queue
        if self._pool is not None:
            while not self._pool.empty():
                self._pool.get_nowait()
            self._pool = None


_pool: DatabaseConnectionPool = DatabaseConnectionPool()


@asynccontextmanager
async def database_session() -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    Async context manager to acquire a connection from the pool,
    bind it to the task-local context variable, and release it on exit.
    """
    conn = await _pool.acquire()
    token = _db_ctx.set(conn)
    try:
        yield conn
    finally:
        _db_ctx.reset(token)
        await _pool.release(conn)


async def init_db(
    database_path: str, timeout: float | None = None, pool_size: int | None = None
) -> aiosqlite.Connection:
    """
    Open the SQLite database and configure it for production use.
    Called once at application startup via the FastAPI lifespan.
    NOT thread-safe — designed for single-process async apps only.
    """
    global _db
    if _db is not None:
        raise RuntimeError("Database already initialized. close_db() first.")

    # Primary connection (used for migrations and fallback)
    db = await aiosqlite.connect(database_path, timeout=timeout if timeout is not None else DEFAULT_TIMEOUT)

    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.execute("PRAGMA busy_timeout=5000")
    db.row_factory = aiosqlite.Row

    await db.commit()
    _db = db

    # Initialize the database connection pool
    from master.config import settings

    effective_pool_size = pool_size if pool_size is not None else settings.db_pool_size
    await _pool.init(database_path, pool_size=effective_pool_size, timeout=timeout)
    return db


async def close_db() -> None:
    """Close the database connection gracefully. Called at shutdown."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
    await _pool.close_all()


def get_db_conn() -> aiosqlite.Connection:
    """
    Return the active DB connection.
    Checks the context variable first, falls back to the primary connection.
    """
    try:
        return _db_ctx.get()
    except LookupError:
        if _db is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")
        return _db


async def reset_db() -> None:
    """
    Reset the database state for testing.
    Closes the connection and clears the global reference.
    """
    global _db
    if _db is not None:
        await _db.close()
        _db = None
    await _pool.close_all()


@asynccontextmanager
async def transaction(db: aiosqlite.Connection) -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    Async context manager that wraps operations in an explicit transaction.
    Uses BEGIN IMMEDIATE to serialize writing transactions at file level in WAL mode.
    Reentrant: if a transaction is already active on the connection, yields directly.
    Rolls back automatically on exception.

    Usage:
        async with transaction(db) as conn:
            await conn.execute(...)
    """
    if db.in_transaction:
        yield db
        return

    await db.execute("BEGIN IMMEDIATE")
    try:
        yield db
        await db.commit()
    except BaseException:
        if db.in_transaction:
            await db.rollback()
        raise
