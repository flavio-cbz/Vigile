from __future__ import annotations

"""
Tests for the plugins table migration (migration 008).

Covers:
- Schema: plugins table exists with expected columns and defaults.
- Seed data: metrics, systemd, docker seeded at version 1.0.0 / status RUNNING.
- Idempotency: running run_migrations twice does not raise, dupes not inserted,
  alembic_version stamped exactly once at 008.
- Legacy migration: a pre-existing plugin_configs table is migrated into plugins
  and dropped, with config_json preserved.
"""

import os
import shutil
import tempfile

import aiosqlite
import pytest

from master.db.database import close_db, init_db, reset_db
from master.db.migrations import run_migrations

EXPECTED_COLUMNS = {
    "id",
    "version",
    "enabled",
    "status",
    "config_json",
    "manifest_hash",
    "updated_at",
}

DEFAULT_PLUGIN_IDS = ("metrics", "systemd", "docker")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _fresh_db(tmp: str) -> aiosqlite.Connection:
    """Create a fresh migrated DB in tmp, return the open connection."""
    await reset_db()
    db_path = os.path.join(tmp, "test.db")
    conn = await init_db(db_path)
    try:
        await run_migrations(conn)
    except Exception:
        await close_db()
        raise
    return conn


async def _columns(conn: aiosqlite.Connection, table: str) -> set[str]:
    async with conn.execute(f"PRAGMA table_info({table})") as cursor:
        return {row["name"] for row in await cursor.fetchall()}


async def _plugins_rows(conn: aiosqlite.Connection) -> list[dict]:
    async with conn.execute(
        "SELECT id, version, enabled, status, config_json, manifest_hash FROM plugins ORDER BY id"
    ) as cursor:
        return [dict(r) for r in await cursor.fetchall()]


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestPluginsSchema:
    @pytest.mark.asyncio
    async def test_plugins_table_exists(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            conn = await _fresh_db(tmp)
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='plugins'"
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == "plugins"
            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_plugins_table_has_expected_columns(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            conn = await _fresh_db(tmp)
            cols = await _columns(conn, "plugins")
            missing = EXPECTED_COLUMNS - cols
            assert not missing, f"plugins table missing columns: {missing}"
            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_plugin_configs_dropped_after_migration(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            conn = await _fresh_db(tmp)
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='plugin_configs'"
            ) as cursor:
                row = await cursor.fetchone()
                assert row is None, "plugin_configs should be dropped after migration"
            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_index_on_plugins_enabled_and_status(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            conn = await _fresh_db(tmp)
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='plugins'"
            ) as cursor:
                names = {row[0] for row in await cursor.fetchall()}
            assert "idx_plugins_enabled" in names
            assert "idx_plugins_status" in names
            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Seed data tests
# ---------------------------------------------------------------------------


class TestPluginsSeedData:
    @pytest.mark.asyncio
    async def test_default_plugins_seeded(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            conn = await _fresh_db(tmp)
            rows = await _plugins_rows(conn)
            ids = {r["id"] for r in rows}
            for pid in DEFAULT_PLUGIN_IDS:
                assert pid in ids, f"default plugin '{pid}' not seeded"
            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_default_plugins_version_and_status(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            conn = await _fresh_db(tmp)
            rows = {r["id"]: r for r in await _plugins_rows(conn)}
            for pid in DEFAULT_PLUGIN_IDS:
                assert rows[pid]["version"] == "1.0.0", f"{pid} version mismatch"
                assert rows[pid]["status"] == "RUNNING", f"{pid} status mismatch"
                assert rows[pid]["enabled"] == 1, f"{pid} not enabled"
            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_default_plugins_config_json_default(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            conn = await _fresh_db(tmp)
            rows = {r["id"]: r for r in await _plugins_rows(conn)}
            for pid in DEFAULT_PLUGIN_IDS:
                assert rows[pid]["config_json"] == "{}", f"{pid} config_json not default"
            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Idempotency tests
# ---------------------------------------------------------------------------


class TestPluginsMigrationIdempotency:
    @pytest.mark.asyncio
    async def test_run_migrations_twice_no_error(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            await reset_db()
            db_path = os.path.join(tmp, "test.db")
            conn = await init_db(db_path)
            await run_migrations(conn)
            await close_db()

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
    async def test_run_migrations_twice_no_duplicate_seeds(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            await reset_db()
            db_path = os.path.join(tmp, "test.db")
            conn = await init_db(db_path)
            await run_migrations(conn)
            await close_db()

            await reset_db()
            conn2 = await init_db(db_path)
            try:
                await run_migrations(conn2)
                async with conn2.execute("SELECT COUNT(*) FROM plugins") as cursor:
                    row = await cursor.fetchone()
                    assert row is not None
                    assert row[0] == len(DEFAULT_PLUGIN_IDS), "seeds should not duplicate"
            finally:
                await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_alembic_version_stamped_009(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            conn = await _fresh_db(tmp)
            async with conn.execute("SELECT version_num FROM alembic_version LIMIT 1") as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == "009", f"Expected 009, got {row[0]}"
            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_alembic_version_single_row_after_double_run(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            await reset_db()
            db_path = os.path.join(tmp, "test.db")
            conn = await init_db(db_path)
            await run_migrations(conn)
            await close_db()

            await reset_db()
            conn2 = await init_db(db_path)
            try:
                await run_migrations(conn2)
                async with conn2.execute("SELECT COUNT(*) FROM alembic_version") as cursor:
                    row = await cursor.fetchone()
                    assert row is not None
                    assert row[0] == 1, "alembic_version should have exactly one row"
            finally:
                await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Legacy plugin_configs migration tests
# ---------------------------------------------------------------------------


class TestLegacyPluginConfigsMigration:
    @pytest.mark.asyncio
    async def test_existing_plugin_configs_migrated(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            await reset_db()
            db_path = os.path.join(tmp, "test.db")
            conn = await init_db(db_path)
            await conn.execute(
                "CREATE TABLE plugin_configs (plugin_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1, config_json TEXT NOT NULL DEFAULT '{}')"
            )
            await conn.execute(
                "INSERT INTO plugin_configs (plugin_id, enabled, config_json) VALUES (?, 1, ?)",
                ("legacy_plugin", '{"key":"value"}'),
            )
            await conn.commit()

            await run_migrations(conn)

            async with conn.execute(
                "SELECT id, enabled, config_json FROM plugins WHERE id = 'legacy_plugin'"
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == "legacy_plugin"
                assert row[1] == 1
                assert row[2] == '{"key":"value"}'

            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='plugin_configs'"
            ) as cursor:
                assert (await cursor.fetchone()) is None
            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_migrated_legacy_plugin_defaults(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            await reset_db()
            db_path = os.path.join(tmp, "test.db")
            conn = await init_db(db_path)
            await conn.execute(
                "CREATE TABLE plugin_configs (plugin_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1, config_json TEXT NOT NULL DEFAULT '{}')"
            )
            await conn.execute(
                "INSERT INTO plugin_configs (plugin_id, enabled, config_json) VALUES (?, 0, '{}')",
                ("disabled_legacy",),
            )
            await conn.commit()

            await run_migrations(conn)

            async with conn.execute(
                "SELECT version, status, manifest_hash FROM plugins WHERE id = 'disabled_legacy'"
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == "0.0.0"
                assert row[1] == "INSTALLED"
                assert row[2] is None
            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_legacy_config_preserved_on_redundant_seed(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            await reset_db()
            db_path = os.path.join(tmp, "test.db")
            conn = await init_db(db_path)
            await conn.execute(
                "CREATE TABLE plugin_configs (plugin_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1, config_json TEXT NOT NULL DEFAULT '{}')"
            )
            await conn.execute(
                "INSERT INTO plugin_configs (plugin_id, enabled, config_json) VALUES ('metrics', 1, '{\"custom\":true}')"
            )
            await conn.commit()

            await run_migrations(conn)

            async with conn.execute(
                "SELECT config_json FROM plugins WHERE id = 'metrics'"
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert '{"custom":true}' in row[0]
            await close_db()
        finally:
            await reset_db()
            shutil.rmtree(tmp, ignore_errors=True)
