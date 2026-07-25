from __future__ import annotations

"""
Vigile — Database Migrations & Seeding

Runs at application startup (idempotent — safe to run on every restart).
Creates all tables if not exists, then seeds the default admin user.
"""

import logging
import time
import uuid

import aiosqlite
from passlib.context import CryptContext

from master.config import settings
from master.core.audit import GENESIS_HASH, compute_entry_hash
from master.db.models import ALL_TABLES, CREATE_INDEXES, CREATE_INVESTIGATIONS

logger = logging.getLogger(__name__)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def run_migrations(db: aiosqlite.Connection) -> None:
    """
    Idempotent migration runner.
    Creates all tables and indexes, then seeds initial data.
    """
    logger.info("Running database migrations...")

    # Create tables
    for ddl in ALL_TABLES:
        await db.execute(ddl)

    # Create indexes
    for idx_sql in CREATE_INDEXES:
        await db.execute(idx_sql)

    await db.commit()
    logger.info("Tables and indexes OK.")

    # Idempotent dynamic columns upgrade for insights and caching
    async with db.execute("PRAGMA table_info(nodes)") as cursor:
        columns = [row["name"] for row in await cursor.fetchall()]

    mutated = False
    if "insight_profile" not in columns:
        await db.execute("ALTER TABLE nodes ADD COLUMN insight_profile TEXT DEFAULT NULL")
        mutated = True
    if "insight_profile_generated_at" not in columns:
        await db.execute(
            "ALTER TABLE nodes ADD COLUMN insight_profile_generated_at REAL DEFAULT NULL"
        )
        mutated = True
    if "cached_services_json" not in columns:
        await db.execute("ALTER TABLE nodes ADD COLUMN cached_services_json TEXT DEFAULT '[]'")
        mutated = True
    if "cached_containers_json" not in columns:
        await db.execute("ALTER TABLE nodes ADD COLUMN cached_containers_json TEXT DEFAULT '[]'")
        mutated = True
    if "node_group" not in columns:
        await db.execute("ALTER TABLE nodes ADD COLUMN node_group TEXT DEFAULT ''")
        mutated = True
    if "disabled" not in columns:
        await db.execute("ALTER TABLE nodes ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0")
        mutated = True
    if "version" not in columns:
        await db.execute("ALTER TABLE nodes ADD COLUMN version TEXT DEFAULT NULL")
        mutated = True
    if "worker_version" not in columns:
        await db.execute("ALTER TABLE nodes ADD COLUMN worker_version TEXT DEFAULT NULL")
        mutated = True
    if "cached_disk_scan_json" not in columns:
        await db.execute("ALTER TABLE nodes ADD COLUMN cached_disk_scan_json TEXT DEFAULT NULL")
        mutated = True
    if "cached_disk_scan_at" not in columns:
        await db.execute("ALTER TABLE nodes ADD COLUMN cached_disk_scan_at REAL DEFAULT NULL")
        mutated = True

    async with db.execute("PRAGMA table_info(metrics_snapshots)") as cursor:
        metrics_columns = [row["name"] for row in await cursor.fetchall()]
    if "disks_json" not in metrics_columns:
        await db.execute("ALTER TABLE metrics_snapshots ADD COLUMN disks_json TEXT DEFAULT NULL")
        mutated = True
    if "top_processes_json" not in metrics_columns:
        await db.execute("ALTER TABLE metrics_snapshots ADD COLUMN top_processes_json TEXT DEFAULT NULL")
        mutated = True

    # Network I/O / Disk I/O / thermal / PSI / resource columns added with the
    # richer MetricsSnapshot struct in worker v0.7+. These were never migrated,
    # causing every STATUS_REPORT INSERT to fail with
    # "table metrics_snapshots has no column named net_bytes_recv".
    for col, ctype in [
        ("net_bytes_recv", "INTEGER"), ("net_bytes_sent", "INTEGER"),
        ("net_packets_recv", "INTEGER"), ("net_packets_sent", "INTEGER"),
        ("net_errors_in", "INTEGER"), ("net_errors_out", "INTEGER"),
        ("net_drops_in", "INTEGER"), ("net_drops_out", "INTEGER"),
        ("disk_reads", "INTEGER"), ("disk_writes", "INTEGER"),
        ("disk_read_bytes", "INTEGER"), ("disk_write_bytes", "INTEGER"),
        ("temp_celsius", "REAL"), ("psi_cpu_avg10", "REAL"),
        ("psi_mem_avg10", "REAL"), ("psi_io_avg10", "REAL"),
        ("file_handles_used", "INTEGER"), ("file_handles_max", "INTEGER"),
        ("entropy_avail", "INTEGER"), ("context_switches", "INTEGER"),
        ("cpu_throttled_count", "INTEGER"),
    ]:
        if col not in metrics_columns:
            await db.execute(
                f"ALTER TABLE metrics_snapshots ADD COLUMN {col} {ctype} DEFAULT NULL"
            )
            mutated = True

    if mutated:
        await db.commit()
        logger.info(
            "Added insights/caching/group/disabled/version/worker_version/disks_json/top_processes columns."
        )

    # Migration: add trust_level column to automation_rules (Sprint 9)
    async with db.execute("PRAGMA table_info(automation_rules)") as cursor:
        ar_columns = [row["name"] for row in await cursor.fetchall()]
    if "trust_level" not in ar_columns:
        await db.execute(
            "ALTER TABLE automation_rules ADD COLUMN trust_level TEXT NOT NULL DEFAULT 'auto'"
        )
        logger.info("Added trust_level column to automation_rules.")
        await db.commit()

    # Migration: create investigations table (Sprint 9) — CREATE TABLE IF NOT EXISTS handles new DBs
    async with db.execute("PRAGMA table_info(investigations)") as cursor:
        inv_columns = [row["name"] for row in await cursor.fetchall()]
    if not inv_columns:
        # Table doesn't exist in old DBs — CREATE TABLE IF NOT EXISTS above handles new ones
        # but the table was already executed by ALL_TABLES at startup, so this is a no-op
        # for new databases. For old ones it was missed — need separate CREATE.
        await db.execute(CREATE_INVESTIGATIONS)
        logger.info("Created investigations table.")
        await db.commit()

    await db.execute("CREATE INDEX IF NOT EXISTS idx_nodes_group ON nodes(node_group)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_nodes_disabled ON nodes(disabled)")
    await db.commit()

    # Self-healing: drop legacy FK on join_tokens.node_id -> nodes.id if present (migration 006)
    await _drop_join_tokens_fk_if_present(db)

    # Migration 008: rename plugin_configs -> plugins and add version/status/manifest_hash columns
    await _migrate_plugin_configs_to_plugins(db)

    # Migration 009: add discovered_at, installed_at, activated_at, last_run_at, deactivated_at, manifest_json columns to plugins table
    async with db.execute("PRAGMA table_info(plugins)") as cursor:
        cols = {row["name"] for row in await cursor.fetchall()}

    if "discovered_at" not in cols:
        await db.execute("ALTER TABLE plugins ADD COLUMN discovered_at TIMESTAMP")
    if "installed_at" not in cols:
        await db.execute("ALTER TABLE plugins ADD COLUMN installed_at TIMESTAMP")
    if "activated_at" not in cols:
        await db.execute("ALTER TABLE plugins ADD COLUMN activated_at TIMESTAMP")
    if "last_run_at" not in cols:
        await db.execute("ALTER TABLE plugins ADD COLUMN last_run_at TIMESTAMP")
    if "deactivated_at" not in cols:
        await db.execute("ALTER TABLE plugins ADD COLUMN deactivated_at TIMESTAMP")
    if "manifest_json" not in cols:
        await db.execute("ALTER TABLE plugins ADD COLUMN manifest_json TEXT")
    await db.commit()
    logger.info("Migration 009: added discovered_at, installed_at, activated_at, last_run_at, deactivated_at, manifest_json columns to plugins table.")

    # Stamp Alembic version if not already versioned (idempotent)
    await db.execute(
        "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
    )
    await db.execute(
        "INSERT OR IGNORE INTO alembic_version (version_num) VALUES (?)",
        ("008",),
    )
    await db.execute(
        "INSERT OR IGNORE INTO alembic_version (version_num) VALUES (?)",
        ("009",),
    )
    await db.commit()

    # Seed data
    await _seed_default_admin(db)
    await _seed_default_plugins(db)
    logger.info("Migrations complete.")


async def _drop_join_tokens_fk_if_present(db: aiosqlite.Connection) -> None:
    """Drop legacy FK on join_tokens.node_id -> nodes.id if present (migration 006)."""
    async with db.execute("PRAGMA foreign_key_list(join_tokens)") as cursor:
        fks = [dict(row) for row in await cursor.fetchall()]

    has_fk = any(fk.get("from") == "node_id" and fk.get("table") == "nodes" for fk in fks)
    if not has_fk:
        return

    logger.info("Dropping legacy FK join_tokens.node_id -> nodes.id (migration 006).")
    await db.execute("PRAGMA foreign_keys=OFF")
    await db.execute("DROP TABLE IF EXISTS join_tokens_new")
    await db.execute("""
    CREATE TABLE IF NOT EXISTS join_tokens_new (
        id TEXT PRIMARY KEY, node_id TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE, payload_b64 TEXT NOT NULL,
        consumed INTEGER NOT NULL DEFAULT 0, expires_at REAL NOT NULL, created_at REAL NOT NULL
    )""")
    await db.execute("INSERT INTO join_tokens_new SELECT * FROM join_tokens")
    await db.execute("DROP TABLE join_tokens")
    await db.execute("ALTER TABLE join_tokens_new RENAME TO join_tokens")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_join_tokens_node_id ON join_tokens(node_id)")
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_join_tokens_consumed ON join_tokens(consumed, expires_at)"
    )
    await db.execute("PRAGMA foreign_keys=ON")
    await db.commit()
    logger.info("Legacy FK dropped successfully.")


async def _seed_default_plugins(db: aiosqlite.Connection) -> None:
    """
    Seed default plugins in the plugins table if not present.
    Each default plugin is seeded at version 1.0.0 with status RUNNING.
    """
    defaults = [("metrics", 1, "1.0.0", "RUNNING"), ("systemd", 1, "1.0.0", "RUNNING"), ("docker", 1, "1.0.0", "RUNNING")]
    for plugin_id, enabled, version, status in defaults:
        await db.execute(
            """
            INSERT OR IGNORE INTO plugins (id, version, enabled, status, config_json)
            VALUES (?, ?, ?, ?, '{}')
            """,
            (plugin_id, version, enabled, status),
        )
    await db.commit()


async def _migrate_plugin_configs_to_plugins(db: aiosqlite.Connection) -> None:
    """
    Migration 008: rename legacy plugin_configs table to plugins and add
    version, status, and manifest_hash columns.

    The legacy plugin_configs table (plugin_id, enabled, config_json) is
    copied into the new plugins schema (id, version, enabled, status,
    config_json, manifest_hash, updated_at). Existing plugin_configs rows are
    preserved verbatim: version defaults to '0.0.0', status to 'INSTALLED',
    manifest_hash to NULL. Then ADD COLUMN brings the new columns onto any
    pre-existing plugins table created by CREATE_PLUGINS.

    Idempotent: a no-op when the rename already occurred.
    """
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='plugin_configs'"
    ) as cursor:
        row = await cursor.fetchone()

    if row is not None:
        logger.info("Migration 008: migrating plugin_configs -> plugins.")
        await db.execute(
            """
            INSERT OR IGNORE INTO plugins (id, enabled, config_json)
            SELECT plugin_id, enabled, config_json FROM plugin_configs
            """
        )
        await db.execute("DROP TABLE plugin_configs")
        await db.commit()
        logger.info("Migration 008: plugin_configs renamed to plugins.")

    # Ensure new columns exist on plugins table (idempotent for fresh + migrated DBs)
    async with db.execute("PRAGMA table_info(plugins)") as cursor:
        cols = {row["name"] for row in await cursor.fetchall()}

    if "version" not in cols:
        await db.execute("ALTER TABLE plugins ADD COLUMN version TEXT NOT NULL DEFAULT '0.0.0'")
    if "status" not in cols:
        await db.execute("ALTER TABLE plugins ADD COLUMN status TEXT NOT NULL DEFAULT 'INSTALLED'")
    if "manifest_hash" not in cols:
        await db.execute("ALTER TABLE plugins ADD COLUMN manifest_hash TEXT")
    await db.commit()


async def _seed_default_admin(db: aiosqlite.Connection) -> None:
    """
    Creates the default admin user if no users exist.
    Credentials: admin / admin — dev convenience account, not for production.
    Set TESTING=true to force a password change on first login.
    """
    async with db.execute("SELECT COUNT(*) FROM users") as cursor:
        row = await cursor.fetchone()
        if row is None or row[0] > 0:
            return

    now = time.time()
    user_id = str(uuid.uuid4())
    password_hash = _pwd_context.hash("admin")
    must_change = 1 if settings.testing else 0

    await db.execute(
        """
        INSERT INTO users (id, username, password_hash, role, is_active, must_change_password, created_at, updated_at)
        VALUES (?, ?, ?, 'admin', 1, ?, ?, ?)
        """,
        (user_id, "admin", password_hash, must_change, now, now),
    )

    # Log the seeding event in the audit trail
    await _seed_genesis_audit(db, user_id)

    await db.commit()
    logger.warning(
        "⚠️  Default admin user created (admin/admin). "
        "CHANGE THIS PASSWORD IMMEDIATELY in production!"
    )


async def _seed_genesis_audit(db: aiosqlite.Connection, admin_user_id: str) -> None:
    """
    Insert the genesis (first) audit log entry.
    This anchors the entire hash chain.
    """
    now = time.time()
    entry_id = str(uuid.uuid4())
    action = "SYSTEM_INIT"
    details = '{"message": "Database initialized. Genesis audit entry."}'

    entry_hash = compute_entry_hash(
        previous_hash=GENESIS_HASH,
        sequence=1,
        timestamp=now,
        action=action,
        user_id=admin_user_id,
        node_id=None,
        details_json=details,
    )

    await db.execute(
        """
        INSERT INTO audit_log
            (id, sequence, timestamp, user_id, action, node_id,
             details_json, previous_hash, entry_hash)
        VALUES (?, 1, ?, ?, ?, NULL, ?, ?, ?)
        """,
        (entry_id, now, admin_user_id, action, details, GENESIS_HASH, entry_hash),
    )
