"""
Vigile — Async SQLite Connection Manager
Provides a context-managed aiosqlite connection with WAL mode enabled.
"""

import aiosqlite
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from master.config import settings


# Module-level connection reference (initialized at startup)
_db: aiosqlite.Connection | None = None


async def init_db() -> aiosqlite.Connection:
    """
    Open the SQLite database and configure it for production use.
    Called once at application startup via the FastAPI lifespan.
    NOT thread-safe — designed for single-process async apps only.
    """
    global _db
    if _db is not None:
        raise RuntimeError("Database already initialized. close_db() first.")

    db = await aiosqlite.connect(settings.database_path)

    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("PRAGMA synchronous=NORMAL")
    db.row_factory = aiosqlite.Row

    await db.commit()
    _db = db
    return db


async def close_db() -> None:
    """Close the database connection gracefully. Called at shutdown."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None


def get_db_conn() -> aiosqlite.Connection:
    """
    Return the active DB connection.
    Raises RuntimeError if called before init_db().
    """
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


@asynccontextmanager
async def transaction(db: aiosqlite.Connection) -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    Async context manager that wraps operations in an explicit transaction.
    Rolls back automatically on exception.

    Usage:
        async with transaction(db) as conn:
            await conn.execute(...)
    """
    try:
        yield db
        await db.commit()
    except Exception:
        await db.rollback()
        raise
