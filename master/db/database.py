"""
Vigile — Async SQLite Connection Manager
Provides a context-managed aiosqlite connection with WAL mode enabled.
"""

import asyncio
import contextvars
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite

# Module-level connection reference (fallback / migrations connection)
_db: aiosqlite.Connection | None = None
_db_ctx: contextvars.ContextVar[aiosqlite.Connection] = contextvars.ContextVar("db_conn")


class DatabaseConnectionPool:
    """
    A lightweight connection pool for aiosqlite.
    Allows concurrent reads in WAL mode across multiple connections.
    """

    def __init__(self) -> None:
        self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue()
        self._connections: list[aiosqlite.Connection] = []
        self._path: str = ""

    async def init(self, database_path: str, size: int = 5) -> None:
        self._path = database_path
        for _ in range(size):
            conn = await self._create_connection()
            self._connections.append(conn)
            await self._pool.put(conn)

    async def _create_connection(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._path, timeout=30.0)
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = aiosqlite.Row
        await conn.commit()
        return conn

    async def acquire(self) -> aiosqlite.Connection:
        return await self._pool.get()

    async def release(self, conn: aiosqlite.Connection) -> None:
        if conn in self._connections:
            await self._pool.put(conn)

    async def close_all(self) -> None:
        for conn in self._connections:
            try:
                await conn.close()
            except Exception:
                pass
        self._connections.clear()
        # Drain the queue
        while not self._pool.empty():
            self._pool.get_nowait()


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


async def init_db(database_path: str) -> aiosqlite.Connection:
    """
    Open the SQLite database and configure it for production use.
    Called once at application startup via the FastAPI lifespan.
    NOT thread-safe — designed for single-process async apps only.
    """
    global _db
    if _db is not None:
        raise RuntimeError("Database already initialized. close_db() first.")

    # Primary connection (used for migrations and fallback)
    db = await aiosqlite.connect(database_path, timeout=30.0)

    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("PRAGMA synchronous=NORMAL")
    db.row_factory = aiosqlite.Row

    await db.commit()
    _db = db

    # Initialize the database connection pool
    await _pool.init(database_path, size=5)
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
    Rolls back automatically on exception.

    Usage:
        async with transaction(db) as conn:
            await conn.execute(...)
    """
    await db.execute("BEGIN IMMEDIATE")
    try:
        yield db
        await db.commit()
    except Exception:
        await db.rollback()
        raise
