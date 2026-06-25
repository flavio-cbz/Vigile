"""
Vigile — Audit Trail

Implements an append-only, chained SHA256 audit log.
Every entry includes the hash of the previous entry, making
any tampering with historical records detectable.

Design:
  - Each entry has a monotonic `sequence` number (ordering guarantee)
  - entry_hash = sha256(previous_hash | sequence | timestamp | action |
                        user_id | node_id | details_json)
  - The genesis entry (sequence=1) uses '0'*64 as previous_hash
  - verify_chain() walks the entire log and recomputes all hashes

The hash function is pure Python stdlib (hashlib) — no dependencies.
"""

import hashlib
import json
import logging
import time
import uuid
from enum import StrEnum
from typing import Any

import aiosqlite

from master.core.lock import LoopBoundLock

logger = logging.getLogger(__name__)


class AuditAction(StrEnum):
    USER_LOGIN = "USER_LOGIN"
    USER_LOGOUT = "USER_LOGOUT"
    USER_CHANGE_PASSWORD = "USER_CHANGE_PASSWORD"
    REFRESH_THEFT_DETECTED = "REFRESH_THEFT_DETECTED"
    TOKEN_REFRESH = "TOKEN_REFRESH"
    PROPOSAL_APPROVED = "PROPOSAL_APPROVED"
    PROPOSAL_REJECTED = "PROPOSAL_REJECTED"
    GENERATE_JOIN_TOKEN = "GENERATE_JOIN_TOKEN"
    REVOKE_NODE = "REVOKE_NODE"
    UPDATE_LLM_SETTINGS = "UPDATE_LLM_SETTINGS"
    UPDATE_INTENT_CONFIG = "UPDATE_INTENT_CONFIG"
    UPLOAD_PLUGIN = "UPLOAD_PLUGIN"
    CONFIGURE_PLUGIN = "CONFIGURE_PLUGIN"
    TOGGLE_PLUGIN = "TOGGLE_PLUGIN"
    DELETE_PLUGIN = "DELETE_PLUGIN"
    NODE_ENROLLED = "NODE_ENROLLED"
    NODE_RECONNECTED = "NODE_RECONNECTED"
    INTENT_RESULT = "INTENT_RESULT"
    CACHE_REFRESH = "CACHE_REFRESH"
    NODE_LOST = "NODE_LOST"
    NODE_STALE = "NODE_STALE"
    RESTART_SERVICE = "RESTART_SERVICE"
    RESTART_CONTAINER = "RESTART_CONTAINER"


# Serialize writes to prevent sequence collision
_audit_lock = LoopBoundLock()

# Sentinel for the first entry in the chain
GENESIS_HASH = "0" * 64


# Core hash computation (shared with migrations.py for genesis entry)
def compute_entry_hash(
    previous_hash: str,
    sequence: int,
    timestamp: float,
    action: str,
    user_id: str,
    node_id: str | None,
    details_json: str,
) -> str:
    """
    Deterministic SHA256 of all entry fields.
    Fields joined with '|' — a character that cannot appear in any field value
    (UUIDs, action names, and JSON all use different separators).
    """
    raw = "|".join(
        [
            previous_hash,
            str(sequence),
            f"{timestamp:.6f}",
            action,
            user_id,
            node_id or "",
            details_json,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def log_action(
    db: aiosqlite.Connection,
    *,
    user_id: str,
    action: AuditAction | str,
    node_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> str:
    """
    Append a new entry to the audit log.

    Steps:
      1. Fetch the current chain head (latest sequence + entry_hash)
      2. Compute the new entry_hash over all fields
      3. Insert atomically

    Returns the entry_id (UUID string).

    Raises:
      RuntimeError if the DB is in an inconsistent state.
    """
    details_json = json.dumps(details or {}, separators=(",", ":"), ensure_ascii=False)
    timestamp = time.time()
    entry_id = str(uuid.uuid4())

    # Serialized via asyncio.Lock to prevent sequence collision under concurrency.
    # (BEGIN IMMEDIATE alone isn't sufficient because await points inside the
    # critical section allow other coroutines to interleave.)
    async with _audit_lock:
        async with db.execute(
            "SELECT sequence, entry_hash FROM audit_log ORDER BY sequence DESC LIMIT 1"
        ) as cursor:
            head = await cursor.fetchone()

        if head is None:
            previous_hash = GENESIS_HASH
            sequence = 1
        else:
            previous_hash = head["entry_hash"]
            sequence = head["sequence"] + 1

        entry_hash = compute_entry_hash(
            previous_hash=previous_hash,
            sequence=sequence,
            timestamp=timestamp,
            action=action,
            user_id=user_id,
            node_id=node_id,
            details_json=details_json,
        )

        await db.execute(
            """
            INSERT INTO audit_log
                (id, sequence, timestamp, user_id, action, node_id,
                 details_json, previous_hash, entry_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                sequence,
                timestamp,
                user_id,
                action,
                node_id,
                details_json,
                previous_hash,
                entry_hash,
            ),
        )
        await db.commit()

    logger.info(
        "AUDIT seq=%d action=%s user=%s node=%s",
        sequence,
        action,
        user_id,
        node_id or "-",
    )
    return entry_id


async def verify_chain(
    db: aiosqlite.Connection,
    *,
    max_entries: int | None = None,
) -> dict[str, Any]:
    """
    Walk the audit log and verify the hash chain integrity.

    Args:
        max_entries: limit the number of entries verified (None = all).
                     Useful for large tables where full scan is expensive.

    Returns a report dict:
      {
        "valid": bool,
        "total_entries": int,
        "first_broken_sequence": int | None,
        "error": str | None,
      }
    """
    report: dict[str, Any] = {
        "valid": True,
        "total_entries": 0,
        "first_broken_sequence": None,
        "error": None,
    }

    if max_entries is not None:
        sql = """
            SELECT id, sequence, timestamp, user_id, action, node_id,
                   details_json, previous_hash, entry_hash
            FROM audit_log
            ORDER BY sequence DESC
            LIMIT ?
        """
        async with db.execute(sql, (max_entries,)) as cursor:
            rows = await cursor.fetchall()
        rows.reverse()
    else:
        sql = """
            SELECT id, sequence, timestamp, user_id, action, node_id,
                   details_json, previous_hash, entry_hash
            FROM audit_log
            ORDER BY sequence ASC
        """
        async with db.execute(sql) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        report["total_entries"] = 0
        return report

    first_row = rows[0]
    if first_row["sequence"] == 1:
        expected_previous_hash = GENESIS_HASH
    else:
        expected_previous_hash = first_row["previous_hash"]

    count = 0
    for row in rows:
        count += 1
        seq = row["sequence"]

        if row["previous_hash"] != expected_previous_hash:
            report["valid"] = False
            report["first_broken_sequence"] = seq
            report["error"] = (
                f"Sequence {seq}: previous_hash mismatch. "
                f"Expected '{expected_previous_hash[:12]}...', "
                f"got '{row['previous_hash'][:12]}...'"
            )
            break

        computed = compute_entry_hash(
            previous_hash=row["previous_hash"],
            sequence=seq,
            timestamp=row["timestamp"],
            action=row["action"],
            user_id=row["user_id"],
            node_id=row["node_id"],
            details_json=row["details_json"],
        )

        if computed != row["entry_hash"]:
            report["valid"] = False
            report["first_broken_sequence"] = seq
            report["error"] = (
                f"Sequence {seq}: entry_hash mismatch. " f"Record has been tampered with."
            )
            break

        expected_previous_hash = row["entry_hash"]

    report["total_entries"] = count
    if report["valid"]:
        logger.info("Audit chain verification OK — %d entries verified.", count)
    else:
        logger.error(
            "Audit chain BROKEN at sequence %s: %s",
            report["first_broken_sequence"],
            report["error"],
        )

    return report


async def get_recent_entries(
    db: aiosqlite.Connection,
    *,
    limit: int = 100,
    node_id: str | None = None,
    user_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch recent audit entries, optionally filtered by node or user.
    Returns a list of dicts ordered newest-first.
    """
    conditions = []
    params: list[Any] = []

    if node_id:
        conditions.append("node_id = ?")
        params.append(node_id)
    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    sql = f"""
        SELECT id, sequence, timestamp, user_id, action, node_id,
               details_json, previous_hash, entry_hash
        FROM audit_log
        {where}
        ORDER BY sequence DESC
        LIMIT ?
    """

    rows = []
    async with db.execute(sql, params) as cursor:
        async for row in cursor:
            rows.append(
                {
                    "id": row["id"],
                    "sequence": row["sequence"],
                    "timestamp": row["timestamp"],
                    "user_id": row["user_id"],
                    "action": row["action"],
                    "node_id": row["node_id"],
                    "details": json.loads(row["details_json"]),
                    "previous_hash": row["previous_hash"],
                    "entry_hash": row["entry_hash"],
                }
            )

    return rows
