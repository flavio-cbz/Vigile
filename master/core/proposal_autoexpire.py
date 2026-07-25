"""
Vigile — Auto-expiration for stale action proposals.

Cancels PENDING proposals when:
  1. TTL exceeded (proposal created more than 1 hour ago).
  2. The triggering metric condition has resolved (heuristic keyword matching
     in the `reasoning` field against the node's latest metrics snapshot).

Design notes:
  - Metric matching uses keyword heuristics on free-form LLM output, which is
    inherently approximate. The 80 % threshold is conservative by design.
  - Hard-deleting proposals would break the audit trail; we set status REJECTED
    with rejected_by="system" and a descriptive reason.
  - This module is wired as a periodic background task in main.py (lifespan).
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

#: Proposals older than this (seconds) are auto-canceled unconditionally.
PROPOSAL_TTL: float = 3600.0  # 1 hour

#: If the corresponding metric is below this threshold the condition is
#: considered resolved.
METRIC_OK_THRESHOLD: float = 80.0

_RESOURCE_KEYWORDS: dict[str, list[str]] = {
    "disk_percent": [
        "disk",
        "espace disque",
        "stockage",
        "storage",
        "volume",
        "disque",
        "disk usage",
        "utilisation disque",
    ],
    "mem_percent": [
        "memory",
        "ram",
        "mémoire",
        "mem",
        "memory usage",
        "utilisation mémoire",
        "swap",
    ],
    "cpu_percent": [
        "cpu",
        "processeur",
        "processor",
        "load",
        "cpu load",
        "charge cpu",
    ],
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def auto_expire_proposals(db, nm=None) -> int:
    """Check every PENDING proposal and auto-cancel stale/resolved ones.

    Returns the number of proposals canceled during this pass.
    """
    from master.core.action_proposal import ActionProposal
    from master.core.audit import AuditAction, log_action

    now = time.time()
    canceled = 0

    async with db.execute(
        "SELECT * FROM action_proposals WHERE status = 'PENDING' ORDER BY created_at ASC"
    ) as cursor:
        rows = [dict(r) for r in await cursor.fetchall()]

    for row in rows:
        proposal = ActionProposal.from_db_row(row)

        # 1. TTL check — unconditional expiry for very old proposals
        age = now - proposal.created_at
        if age > PROPOSAL_TTL:
            await _do_cancel(db, proposal, "Délai expiré (proposition trop ancienne)", log_action)
            canceled += 1
            continue

        # 2. Metric condition check — heuristic keyword matching
        reason = await _check_metric_resolved(db, proposal)
        if reason:
            await _do_cancel(db, proposal, reason, log_action)
            canceled += 1

    if canceled:
        logger.info("Auto-expire: canceled %d stale proposal(s).", canceled)
    return canceled


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _check_metric_resolved(db, proposal) -> str | None:
    """Return a human-readable reason if the triggering metric has recovered.

    Returns ``None`` when the proposal doesn't reference a measurable metric
    or there is no metrics data to check against.
    """
    reasoning_lower = proposal.reasoning.lower()

    # Determine which metric to inspect based on reasoning keywords
    metric = None
    for metric_name, keywords in _RESOURCE_KEYWORDS.items():
        if any(kw in reasoning_lower for kw in keywords):
            metric = metric_name
            break

    if metric is None:
        return None  # Non-metric proposal (e.g. restart container) — skip

    # Fetch the latest metrics snapshot for the relevant node
    # SAFE: metric is from fixed _RESOURCE_KEYWORDS whitelist (disk_percent, mem_percent, cpu_percent)
    async with db.execute(
        f"SELECT {metric}, collected_at FROM metrics_snapshots "
        f"WHERE node_id = ? ORDER BY collected_at DESC LIMIT 1",
        (proposal.node_id,),
    ) as cursor:
        row = await cursor.fetchone()

    if row is None:
        return None  # No metrics data yet

    current_value = row[metric]

    if current_value < METRIC_OK_THRESHOLD:
        return (
            f"Condition résolue: {metric} à {current_value:.1f}% "
            f"(< {METRIC_OK_THRESHOLD:.0f}%)"
        )

    return None


async def _do_cancel(db, proposal, reason: str, log_action) -> None:
    """Transition a PENDING proposal to REJECTED with a system reason."""
    proposal.status = "REJECTED"
    proposal.rejected_by = "system"
    proposal.rejection_reason = f"Auto-canceled: {reason}"
    proposal.updated_at = time.time()

    db_data = proposal.to_db_dict()
    await db.execute(
        """
        UPDATE action_proposals SET
            status = ?, rejected_by = ?, rejection_reason = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            db_data["status"],
            db_data["rejected_by"],
            db_data["rejection_reason"],
            db_data["updated_at"],
            proposal.id,
        ),
    )
    await db.commit()

    logger.info("Proposal %s auto-canceled: %s", proposal.id, reason)

    # Only log to audit if the proposal had a node_id (non-null)
    if proposal.node_id:
        await log_action(
            db,
            user_id="system",
            action="PROPOSAL_REJECTED",
            node_id=proposal.node_id,
            details={
                "proposal_id": proposal.id,
                "action": proposal.action,
                "reason": reason,
            },
        )
