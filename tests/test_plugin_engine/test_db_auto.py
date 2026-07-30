from __future__ import annotations

import os
import tempfile

import aiosqlite
import pytest
try:
    from pytest_asyncio import fixture as async_fixture
except ImportError:
    async_fixture = pytest.fixture



from master.core.db_auto import DBAuto


@async_fixture(scope="function")
async def db():
    tmp = tempfile.mktemp(suffix=".db")
    conn = await aiosqlite.connect(tmp)
    conn.row_factory = aiosqlite.Row
    yield conn
    await conn.close()
    os.unlink(tmp)


@pytest.mark.asyncio
async def test_create_table(db):
    db_auto = DBAuto(db)
    schema = {
        "events": [
            {"name": "id", "type": "INTEGER", "pk": True},
            {"name": "name", "type": "TEXT", "not_null": True},
        ]
    }
    results = await db_auto.create_tables("test_plugin", schema)
    assert results.get("events") is True
    cursor = await db.execute("PRAGMA table_info(test_plugin_events)")
    rows = await cursor.fetchall()
    col_names = {row["name"] for row in rows}
    assert "id" in col_names
    assert "name" in col_names


@pytest.mark.asyncio
async def test_drop_table(db):
    db_auto = DBAuto(db)
    schema = {
        "temp": [
            {"name": "id", "type": "INTEGER"},
        ]
    }
    await db_auto.create_tables("test", schema)
    await db_auto.drop_tables("test", schema)
    cursor = await db.execute("PRAGMA table_info(test_temp)")
    rows = await cursor.fetchall()
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_create_multiple_tables(db):
    db_auto = DBAuto(db)
    schema = {
        "a": [{"name": "id", "type": "INTEGER", "pk": True}],
        "b": [{"name": "val", "type": "TEXT"}],
    }
    results = await db_auto.create_tables("multi", schema)
    assert results["a"] is True
    assert results["b"] is True
    cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'multi_%'")
    rows = await cursor.fetchall()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_verify_tables_pass(db):
    db_auto = DBAuto(db)
    schema = {
        "data": [
            {"name": "id", "type": "INTEGER", "pk": True},
            {"name": "label", "type": "TEXT"},
        ]
    }
    await db_auto.create_tables("v", schema)
    results = await db_auto.verify_tables("v", schema)
    assert results.get("data") is True


@pytest.mark.asyncio
async def test_verify_tables_missing_column(db):
    db_auto = DBAuto(db)
    schema = {
        "data": [
            {"name": "id", "type": "INTEGER", "pk": True},
        ]
    }
    await db_auto.create_tables("v", schema)
    schema_with_extra = {
        "data": [
            {"name": "id", "type": "INTEGER", "pk": True},
            {"name": "missing_col", "type": "TEXT"},
        ]
    }
    results = await db_auto.verify_tables("v", schema_with_extra)
    assert results.get("data") is False


@pytest.mark.asyncio
async def test_create_table_with_defaults(db):
    db_auto = DBAuto(db)
    schema = {
        "config": [
            {"name": "key", "type": "TEXT", "pk": True},
            {"name": "value", "type": "TEXT", "default": "default_val"},
            {"name": "count", "type": "INTEGER", "default": 0},
            {"name": "active", "type": "BOOLEAN", "default": True},
        ]
    }
    results = await db_auto.create_tables("cfg", schema)
    assert results["config"] is True
    cursor = await db.execute("PRAGMA table_info(cfg_config)")
    rows = await cursor.fetchall()
    col_map = {row["name"]: row for row in rows}
    assert col_map["value"]["dflt_value"] == "'default_val'"
    assert col_map["count"]["dflt_value"] == "0"


@pytest.mark.asyncio
async def test_no_db_raises():
    db_auto = DBAuto()
    with pytest.raises(RuntimeError):
        await db_auto.create_tables("test", {})

    with pytest.raises(RuntimeError):
        await db_auto.drop_tables("test", {})

    with pytest.raises(RuntimeError):
        await db_auto.verify_tables("test", {})


@pytest.mark.asyncio
async def test_set_db(db):
    db_auto = DBAuto()
    db_auto.set_db(db)
    schema = {
        "t": [{"name": "id", "type": "INTEGER", "pk": True}]
    }
    results = await db_auto.create_tables("s", schema)
    assert results["t"] is True
