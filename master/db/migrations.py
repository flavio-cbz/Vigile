"""
Vigile — Database Migrations & Seeding

Runs at application startup (idempotent — safe to run on every restart).
Creates all tables if not exists, then seeds the default admin user.
"""

import logging
import os
import time
import uuid

import aiosqlite
from passlib.context import CryptContext

from master.core.audit import GENESIS_HASH, compute_entry_hash
from master.db.models import ALL_TABLES, CREATE_INDEXES

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
        await db.execute("ALTER TABLE nodes ADD COLUMN insight_profile TEXT")
        mutated = True
    if "insight_profile_generated_at" not in columns:
        await db.execute("ALTER TABLE nodes ADD COLUMN insight_profile_generated_at REAL")
        mutated = True
    if "cached_services_json" not in columns:
        await db.execute("ALTER TABLE nodes ADD COLUMN cached_services_json TEXT")
        mutated = True
    if "cached_containers_json" not in columns:
        await db.execute("ALTER TABLE nodes ADD COLUMN cached_containers_json TEXT")
        mutated = True
    if "node_group" not in columns:
        await db.execute("ALTER TABLE nodes ADD COLUMN node_group TEXT")
        mutated = True
    if "disabled" not in columns:
        await db.execute("ALTER TABLE nodes ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0")
        mutated = True

    if mutated:
        await db.commit()
        logger.info("Added insights/caching/group/disabled columns to nodes table.")

    await db.execute("CREATE INDEX IF NOT EXISTS idx_nodes_group ON nodes(node_group)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_nodes_disabled ON nodes(disabled)")
    await db.commit()

    # Self-healing: drop legacy FK on join_tokens.node_id -> nodes.id if present (migration 006)
    await _drop_join_tokens_fk_if_present(db)

    # Stamp Alembic version if not already versioned (idempotent)
    await db.execute(
        "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
    )
    await db.execute(
        "INSERT OR IGNORE INTO alembic_version (version_num) VALUES (?)",
        ("006",),
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
    await db.execute(
        """
    CREATE TABLE join_tokens_new (
        id TEXT PRIMARY KEY, node_id TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE, payload_b64 TEXT NOT NULL,
        consumed INTEGER NOT NULL DEFAULT 0, expires_at REAL NOT NULL, created_at REAL NOT NULL
    )"""
    )
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
    Seed default plugins in plugin_configs table if empty.
    """
    defaults = [("metrics", 1, "{}"), ("systemd", 1, "{}"), ("docker", 1, "{}")]
    for plugin_id, enabled, config in defaults:
        await db.execute(
            """
            INSERT OR IGNORE INTO plugin_configs (plugin_id, enabled, config_json)
            VALUES (?, ?, ?)
            """,
            (plugin_id, enabled, config),
        )
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
    must_change = 1 if os.getenv("TESTING") == "true" else 0

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
