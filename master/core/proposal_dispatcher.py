from __future__ import annotations

"""
Vigile — ApprovedProposalDispatcher

Enforces HITL zero-bypass for approved ActionProposal dispatch.

The dispatcher guarantees:
  1. Only APPROVED proposals are dispatched (state machine guard)
  2. CAS (Compare-And-Swap) prevents double-dispatch race conditions
  3. Every dispatch produces an AuditAction.INTENT_DISPATCH entry
  4. Results are persisted and audited atomically
"""

import json
import time
import uuid
from typing import Any

import aiosqlite
import logging

from master.core.action_proposal import ActionProposal
from master.core.audit import AuditAction, log_action
from master.core.lock import LoopBoundLock
from master.core.node_manager import NodeManager
from master.db.database import transaction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class ProposalDispatcherError(Exception):
    """Base error for proposal dispatch operations."""


class ProposalNotFoundError(ProposalDispatcherError):
    """Raised when the proposal does not exist in the database."""


class ProposalNotApprovedError(ProposalDispatcherError):
    """Raised when the proposal is not in APPROVED status."""


class AlreadyDispatchedError(ProposalDispatcherError):
    """Raised when another dispatcher already claimed this proposal via CAS."""


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class ApprovedProposalDispatcher:
    """
    Dispatches approved ActionProposals to Workers with HITL zero-bypass.

    Uses DB-level CAS (Compare-And-Swap) to prevent double-dispatch even
    under concurrent dispatcher instances. Every dispatch and result
    resolution is recorded in the audit chain.

    Constructor receives NodeManager via strict DI — never reads settings
    or env vars.

    Usage::

        dispatcher = ApprovedProposalDispatcher(node_manager=nm)
        result = await dispatcher.dispatch_approved(proposal_id, db)
    """

    def __init__(self, node_manager: NodeManager) -> None:
        """
        Args:
            node_manager: The NodeManager instance for Worker intent dispatch.
                          Injected via DI — no settings/env lookup.
        """
        self._node_manager = node_manager
        # In-process lock to serialize dispatch attempts for the same proposal.
        # The authoritative guard is the DB CAS, but the in-memory lock
        # prevents wasted round-trips under contention.
        self._lock: LoopBoundLock = LoopBoundLock()

    async def dispatch_approved(
        self,
        proposal_id: str,
        db: aiosqlite.Connection,
        *,
        intent_timeout: float | None = None,
    ) -> dict[str, Any]:
        """
        Dispatch an approved ActionProposal to its target Worker.

        Lifecycle:
          1. Load the ActionProposal from DB
          2. Verify status == APPROVED (rejects PENDING/EXECUTED/FAILED/REJECTED)
          3. CAS claim: ``UPDATE ... SET dispatch_id = ?, intent_id = ?,
             expires_at = ? WHERE id = ? AND dispatch_id IS NULL
             AND status = 'APPROVED'``
          4. Generate ``dispatch_id`` (uuid4) and ``intent_id`` (uuid4)
          5. Set ``expires_at = now + 300s`` (5 min TTL for EXECUTED/FAILED)
          6. Call ``node_manager._send_intent(node_id, intent_dict)``
          7. On success → proposal EXECUTED, persisted, audited
          8. On failure → proposal FAILED, persisted, audited
          9. Append ``AuditAction.INTENT_DISPATCH`` entry

        Args:
            proposal_id: The ActionProposal ID to dispatch.
            db: aiosqlite connection (injected, not imported).
            intent_timeout: Seconds to wait for Worker response
                (default: 30.0).

        Returns:
            The Worker result dict (``{"success": ..., ...}``).

        Raises:
            ProposalNotFoundError: proposal_id does not exist.
            ProposalNotApprovedError: proposal is not in APPROVED state.
            AlreadyDispatchedError: another dispatcher already claimed it.
            RuntimeError: the target node is not connected.
            TimeoutError: the Worker did not respond in time.
        """
        async with self._lock:
            return await self._dispatch_approved_impl(
                proposal_id, db, intent_timeout=intent_timeout,
            )

    async def _dispatch_approved_impl(
        self,
        proposal_id: str,
        db: aiosqlite.Connection,
        *,
        intent_timeout: float | None,
    ) -> dict[str, Any]:
        """Inner implementation of dispatch_approved (under lock)."""
        # ── Step 1: Load proposal ────────────────────────────────────────
        async with db.execute(
            "SELECT * FROM action_proposals WHERE id = ?",
            (proposal_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise ProposalNotFoundError(f"Proposal {proposal_id} not found")

        proposal = ActionProposal.from_db_row(dict(row))

        # ── Step 2: Verify APPROVED ──────────────────────────────────────
        if proposal.status != "APPROVED":
            raise ProposalNotApprovedError(
                f"Proposal {proposal_id} is in state {proposal.status!r}, "
                f"expected APPROVED",
            )

        # ── Step 3: CAS claim (Compare-And-Swap) ─────────────────────────
        dispatch_id = str(uuid.uuid4())
        intent_id = str(uuid.uuid4())
        now = time.time()
        expires_at = now + 300.0  # 5-minute TTL

        async with transaction(db) as tx_db:
            cursor = await tx_db.execute(
                """UPDATE action_proposals
                   SET dispatch_id = ?, intent_id = ?, expires_at = ?,
                       updated_at = ?
                   WHERE id = ? AND dispatch_id IS NULL AND status = 'APPROVED'""",
                (dispatch_id, intent_id, expires_at, now, proposal_id),
            )
            if cursor.rowcount == 0:
                # Determine the reason for CAS failure
                async with tx_db.execute(
                    "SELECT dispatch_id, status FROM action_proposals WHERE id = ?",
                    (proposal_id,),
                ) as check:
                    current = await check.fetchone()
                if current is None:
                    raise ProposalNotFoundError(
                        f"Proposal {proposal_id} not found "
                        f"(concurrent deletion?)",
                    )
                if current["status"] != "APPROVED":
                    raise ProposalNotApprovedError(
                        f"Proposal {proposal_id} is {current['status']!r}, "
                        f"not APPROVED",
                    )
                raise AlreadyDispatchedError(
                    f"Proposal {proposal_id} already claimed by "
                    f"dispatch_id={current['dispatch_id']}",
                )

        # ── Step 4: Send intent to Worker ────────────────────────────────
        intent_dict: dict[str, Any] = {
            "action": proposal.action,
            "params": proposal.params,
            "intent_id": intent_id,
        }

        try:
            result = await self._node_manager._send_intent(
                proposal.node_id,
                intent_dict,
                timeout=intent_timeout,
            )
            success = result.get("success", False)
            proposal.complete(success=success, result_data=result)
        except (RuntimeError, TimeoutError) as exc:
            result = {"success": False, "error": str(exc)}
            proposal.complete(success=False, result_data=result)

        # ── Step 5: Persist result ───────────────────────────────────────
        db_data = proposal.to_db_dict()
        async with transaction(db) as tx_db:
            await tx_db.execute(
                """UPDATE action_proposals
                   SET status = ?, updated_at = ?, executed_at = ?,
                       result_json = ?
                   WHERE id = ?""",
                (
                    db_data["status"],
                    db_data["updated_at"],
                    db_data["executed_at"],
                    db_data["result_json"],
                    proposal_id,
                ),
            )

        # ── Step 6: Audit dispatch ───────────────────────────────────────
        user_id = proposal.approved_by or "system"
        await log_action(
            db,
            user_id=user_id,
            action=AuditAction.INTENT_DISPATCH,
            node_id=proposal.node_id,
            details={
                "proposal_id": proposal_id,
                "dispatch_id": dispatch_id,
                "intent_id": intent_id,
                "action": proposal.action,
                "status": proposal.status,
                "success": result.get("success", False),
            },
        )

        logger.info(
            "Proposal dispatched",
            proposal_id=proposal_id,
            dispatch_id=dispatch_id,
            intent_id=intent_id,
            node_id=proposal.node_id,
            action=proposal.action,
            status=proposal.status,
        )

        return result

    async def resolve_intent_result(
        self,
        intent_id: str,
        dispatch_id: str,
        node_id: str,
        result: dict[str, Any],
        db: aiosqlite.Connection,
    ) -> None:
        """
        Resolve a dispatched intent with the Worker's result.

        Validates the ``intent_id`` / ``dispatch_id`` / ``node_id`` triple
        against a proposal still in APPROVED (dispatched but unresolved)
        state. Updates the proposal and appends an audit entry.

        Args:
            intent_id: The Worker-side intent identifier.
            dispatch_id: The dispatch identifier from the CAS claim.
            node_id: The target node ID.
            result: The result dict from the Worker.
            db: aiosqlite connection (injected, not imported).

        Raises:
            ProposalNotFoundError: no matching proposal found for the triple.
        """
        # ── Validate triple ──────────────────────────────────────────────
        async with db.execute(
            """SELECT id, status, approved_by FROM action_proposals
               WHERE intent_id = ? AND dispatch_id = ? AND node_id = ?
               AND status = 'APPROVED'""",
            (intent_id, dispatch_id, node_id),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise ProposalNotFoundError(
                f"No APPROVED proposal found for "
                f"intent_id={intent_id} dispatch_id={dispatch_id} "
                f"node_id={node_id}",
            )

        proposal_id: str = row["id"]
        approved_by: str | None = row["approved_by"]
        user_id = approved_by or "system"

        # ── Build update ─────────────────────────────────────────────────
        success = result.get("success", False)
        status = "EXECUTED" if success else "FAILED"
        now = time.time()
        result_json = json.dumps(result, separators=(",", ":"), ensure_ascii=False)

        # ── Persist ──────────────────────────────────────────────────────
        async with transaction(db) as tx_db:
            await tx_db.execute(
                """UPDATE action_proposals
                   SET status = ?, updated_at = ?, executed_at = ?,
                       result_json = ?
                   WHERE intent_id = ? AND dispatch_id = ?""",
                (status, now, now, result_json, intent_id, dispatch_id),
            )

        # ── Audit ────────────────────────────────────────────────────────
        await log_action(
            db,
            user_id=user_id,
            action=AuditAction.INTENT_RESULT,
            node_id=node_id,
            details={
                "proposal_id": proposal_id,
                "intent_id": intent_id,
                "dispatch_id": dispatch_id,
                "status": status,
                "success": success,
            },
        )

        logger.info(
            "Intent result resolved",
            proposal_id=proposal_id,
            intent_id=intent_id,
            dispatch_id=dispatch_id,
            node_id=node_id,
            status=status,
        )
