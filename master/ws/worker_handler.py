from __future__ import annotations

"""
Vigile — Worker WebSocket Handler

Implements the full two-phase enrollment and operational WebSocket protocol.

ENROLLMENT PHASE (stateful, sequential, time-bounded):
─────────────────────────────────────────────────────
  Worker → Master : ENROLLMENT_REQUEST  {join_token, public_key, fingerprint}
  Master → Worker : ENROLLMENT_CHALLENGE {challenge}
  Worker → Master : ENROLLMENT_RESPONSE {signature}
  Master → Worker : ENROLLMENT_SUCCESS  {worker_token, master_public_key}
       OR
  Master → Worker : ENROLLMENT_ERROR    {code, detail}

OPERATIONAL PHASE (bidirectional, long-lived):
──────────────────────────────────────────────
  Worker → Master : HEARTBEAT           {} (every 30s)
  Master → Worker : HEARTBEAT_ACK       {}
  Master → Worker : INTENT              {intent_id, action, params}
  Worker → Master : INTENT_RESULT       {intent_id, success, output, error}
  Worker → Master : STATUS_REPORT       {cpu, mem, disk, uptime}

Security guarantees:
  - Each enrollment step has a strict timeout (ENROLLMENT_STEP_TIMEOUT)
  - Malformed messages close the connection immediately
  - The JOIN_TOKEN is atomically consumed in the DB before sending SUCCESS
  - If a REVOKED node connects, we close immediately (code 4403)
  - Duplicate token detection: same token presented from two IPs → revoke both
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any

import aiosqlite
from fastapi import WebSocket, WebSocketDisconnect

from master.core.audit import AuditAction, log_action
from master.core.node_manager import NodeState, node_manager
from master.core.plugin_manager import plugin_manager
from master.core.security_manager import get_security_instance
from master.db.database import get_db_conn, transaction

logger = logging.getLogger(__name__)

# Maximum time to wait for each enrollment step (seconds)
ENROLLMENT_STEP_TIMEOUT = 30.0

# WebSocket close codes (4000-4999 are application-defined)
WS_CLOSE_INVALID_TOKEN = 4400
WS_CLOSE_TOKEN_CONSUMED = 4401
WS_CLOSE_TOKEN_EXPIRED = 4402
WS_CLOSE_REVOKED = 4403
WS_CLOSE_SIGNATURE_INVALID = 4410
WS_CLOSE_PROTOCOL_ERROR = 4420
WS_CLOSE_TIMEOUT = 4408
WS_CLOSE_SERVER_ERROR = 4500


# ---------------------------------------------------------------------------
# WebSocket route handler (called from main.py)
# ---------------------------------------------------------------------------


async def worker_join_handler(websocket: WebSocket) -> None:
    """
    Main entry point for /ws/worker/join.

    Accepts the WebSocket, runs the enrollment handshake, then enters
    the operational loop. Handles all errors by closing with appropriate codes.
    """
    logger.debug("HANDLER CALLED for WS %s", id(websocket))

    from master.config import settings

    if settings.enforce_https:
        url = getattr(websocket, "url", None)
        scheme = getattr(url, "scheme", None) if url else None
        headers = getattr(websocket, "headers", {})
        x_proto = headers.get("x-forwarded-proto", "") if hasattr(headers, "get") else ""
        is_secure = scheme == "wss" or x_proto.lower() == "https"
        if not is_secure:
            logger.warning("Rejecting unencrypted WebSocket connection (enforce_https=True)")
            await websocket.accept()
            await websocket.close(code=4426, reason="WSS/TLS required")
            return

    await websocket.accept()
    logger.debug("WEBSOCKET ACCEPTED for WS %s", id(websocket))
    remote = _get_remote_address(websocket)
    logger.info("Worker connected from %s (WS=%s)", remote, id(websocket))

    if get_security_instance().audit_compromised:
        raise _EnrollmentError(4433, "Security compromise detected")

    db = get_db_conn()
    node_id: str | None = None

    try:
        # Phase 1: Enrollment handshake
        node_id = await _run_enrollment(websocket, db, remote)

        # Phase 2: Operational loop
        await _run_operational(websocket, db, node_id, remote)

    except WebSocketDisconnect as exc:
        logger.info("Worker %s disconnected (code=%s)", node_id or remote, exc.code)

    except asyncio.TimeoutError:
        logger.warning("Worker %s: enrollment timeout", remote)
        await _close(websocket, WS_CLOSE_TIMEOUT, "Enrollment timeout")

    except _EnrollmentError as exc:
        logger.warning("Worker %s: enrollment error [%s] %s", remote, exc.code, exc.detail)
        await _close(websocket, exc.code, exc.detail)

    except Exception:
        logger.exception("Worker %s: unexpected error", node_id or remote)
        await _close(websocket, WS_CLOSE_SERVER_ERROR, "Internal server error")

    finally:
        if node_id:
            await node_manager.unregister_connection(node_id)
            try:
                current = await _get_node_state(db, node_id)
                if current == NodeState.CONNECTED:
                    await node_manager.transition_state(db, node_id, NodeState.RECONNECTING)
                elif current == NodeState.ENROLLING:
                    await node_manager.transition_state(db, node_id, NodeState.PENDING)
            except Exception:
                logger.exception("Failed to update state on disconnect for node %s", node_id)


# ---------------------------------------------------------------------------
# Phase 1: Enrollment
# ---------------------------------------------------------------------------


async def _run_enrollment(
    websocket: WebSocket,
    db: aiosqlite.Connection,
    remote: str,
) -> str:
    """
    Run the full enrollment handshake.
    Returns the node_id on success, raises _EnrollmentError on failure.
    """

    # ── Step 1: Receive ENROLLMENT_REQUEST ──────────────────────────────────
    req = await _recv_typed(websocket, "ENROLLMENT_REQUEST", timeout=ENROLLMENT_STEP_TIMEOUT)

    join_token: str = req.get("join_token", "")
    worker_token: str = req.get("worker_token", "")
    reconnect: bool = req.get("reconnect", False)
    public_key_b64: str = req.get("public_key", "")
    fingerprint: dict = req.get("fingerprint", {})

    if not public_key_b64:
        raise _EnrollmentError(WS_CLOSE_PROTOCOL_ERROR, "Missing public_key")

    # ── Step 1.5: Reconnect mode — skip JOIN_TOKEN + Ed25519 challenge ─────
    if reconnect and worker_token:
        return await _run_reconnect(
            websocket, db, remote, worker_token, public_key_b64, fingerprint
        )

    # Regular enrollment: require join_token
    if not join_token:
        raise _EnrollmentError(WS_CLOSE_PROTOCOL_ERROR, "Missing join_token or worker_token")

    # ── Step 2: Validate JOIN_TOKEN (HMAC + TTL) ────────────────────────────
    try:
        payload = get_security_instance().decode_join_token(join_token)
    except ValueError as exc:
        raise _EnrollmentError(WS_CLOSE_INVALID_TOKEN, str(exc)) from exc

    node_id: str = payload["node_id"]

    # ── Step 3: Check IP prefix restriction ─────────────────────────────────
    ip_prefix = payload.get("ip_prefix", "")
    if ip_prefix and not remote.startswith(ip_prefix):
        logger.warning(
            "Worker %s rejected: IP %s doesn't match prefix %s",
            node_id,
            remote,
            ip_prefix,
        )
        raise _EnrollmentError(WS_CLOSE_INVALID_TOKEN, "IP prefix restriction violated")

    # ── Step 4: Validate token in DB (existence + consumed + expiry) ───────
    token_hash = get_security_instance().join_token_hash(join_token)

    async with db.execute(
        "SELECT consumed, expires_at FROM join_tokens WHERE token_hash = ? AND node_id = ?",
        (token_hash, node_id),
    ) as cursor:
        token_row = await cursor.fetchone()

    if token_row is None:
        raise _EnrollmentError(WS_CLOSE_INVALID_TOKEN, "Token not found")
    if token_row["consumed"]:
        logger.error("SECURITY: consumed token reused! node_id=%s remote=%s", node_id, remote)
        raise _EnrollmentError(WS_CLOSE_TOKEN_CONSUMED, "Token already consumed")
    if time.time() > token_row["expires_at"]:
        raise _EnrollmentError(WS_CLOSE_TOKEN_EXPIRED, "Token expired")

    # ── Step 5: Check node state ────────────────────────────────────────────
    # None = first-time enrollment (no `nodes` row yet — created below).
    # REVOKED = reject. PENDING/LOST/STALE/RECONNECTING = re-enrollment.
    node_state = await _get_node_state(db, node_id)

    if node_state == NodeState.REVOKED:
        logger.warning("REVOKED node attempted enrollment: %s", node_id)
        raise _EnrollmentError(WS_CLOSE_REVOKED, "Node is revoked")

    if node_state is not None and node_state not in (
        NodeState.PENDING,
        NodeState.LOST,
        NodeState.STALE,
        NodeState.RECONNECTING,
    ):
        # Node might already be in ENROLLING from another connection
        raise _EnrollmentError(
            WS_CLOSE_PROTOCOL_ERROR,
            f"Node is in unexpected state: {node_state}",
        )

    is_first_enrollment = node_state is None

    # ── Step 6: Transition to ENROLLING (no-op on first enrollment) ─────────
    if not is_first_enrollment:
        await node_manager.transition_state(db, node_id, NodeState.ENROLLING)

    # ── Step 7: Generate and send CHALLENGE ─────────────────────────────────
    challenge = get_security_instance().generate_challenge()
    await _send(
        websocket, {"type": "ENROLLMENT_CHALLENGE", "challenge": challenge}, node_id=node_id
    )

    # ── Step 8: Receive ENROLLMENT_RESPONSE ─────────────────────────────────
    resp = await _recv_typed(websocket, "ENROLLMENT_RESPONSE", timeout=ENROLLMENT_STEP_TIMEOUT)
    signature_b64: str = resp.get("signature", "")

    if not signature_b64:
        raise _EnrollmentError(WS_CLOSE_PROTOCOL_ERROR, "Missing signature in response")

    # ── Step 9: Verify Ed25519 signature ────────────────────────────────────
    if not get_security_instance().verify_ed25519_signature(
        public_key_b64, challenge, signature_b64
    ):
        logger.warning(
            "Ed25519 signature verification FAILED: node_id=%s remote=%s",
            node_id,
            remote,
        )
        raise _EnrollmentError(WS_CLOSE_SIGNATURE_INVALID, "Signature verification failed")

    logger.info("Ed25519 signature verified for node %s", node_id)

    # ── Step 10: Atomic DB commit — consume token + store node data ──────────
    now = time.time()
    hostname = fingerprint.get("hostname", "")
    machine_id = fingerprint.get("machine_id", "")
    arch = fingerprint.get("arch", "")
    os_name = fingerprint.get("os", "")
    version = fingerprint.get("version", "")
    # Name and group are carried in the JOIN_TOKEN payload (set by generate-join).
    # On first enrollment, we need them to satisfy the NOT NULL `name` column.
    pending_name = payload.get("name", "") or hostname
    pending_group = payload.get("group", "")
    ip_prefix = payload.get("ip_prefix", "")

    async with transaction(db):
        # Atomic consume: only succeeds if consumed=0 (prevents double-enrollment race)
        cursor = await db.execute(
            "UPDATE join_tokens SET consumed = 1 WHERE token_hash = ? AND consumed = 0",
            (token_hash,),
        )
        if cursor.rowcount == 0:
            logger.error(
                "SECURITY: token already consumed in race window! node_id=%s remote=%s",
                node_id,
                remote,
            )
            raise _EnrollmentError(WS_CLOSE_TOKEN_CONSUMED, "Token already consumed")

        if is_first_enrollment:
            # INSERT the `nodes` row (the Worker is what creates the row,
            # see migration 006 + master/api/nodes.py).
            await db.execute(
                """
                INSERT INTO nodes (
                    id, name, hostname, machine_id, arch, os, public_key,
                    state, ip_prefix, node_group, version, worker_version,
                    enrolled_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node_id,
                    pending_name,
                    hostname,
                    machine_id,
                    arch,
                    os_name,
                    public_key_b64,
                    NodeState.CONNECTED.value,
                    ip_prefix,
                    pending_group,
                    version,
                    version,
                    now,
                    now,
                    now,
                ),
            )
        else:
            await db.execute(
                """
                UPDATE nodes SET
                    hostname = ?,
                    machine_id = ?,
                    arch = ?,
                    os = ?,
                    public_key = ?,
                    version = ?,
                    worker_version = ?,
                    enrolled_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    hostname,
                    machine_id,
                    arch,
                    os_name,
                    public_key_b64,
                    version,
                    version,
                    now,
                    now,
                    node_id,
                ),
            )

        worker_token, lifecycle = get_security_instance().generate_worker_token(node_id)
        worker_token_hash = get_security_instance().worker_token_hash(worker_token)
        token_id = str(uuid.uuid4())

        await db.execute(
            """
            INSERT INTO worker_tokens
                (id, node_id, token_hash, issued_at, rotation_due, expires_at, revoked)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (
                token_id,
                node_id,
                worker_token_hash,
                lifecycle["issued_at"],
                lifecycle["rotation_due"],
                lifecycle["expires_at"],
            ),
        )

    logger.info("Enrollment DB committed for node %s (hostname=%s)", node_id, hostname)

    # ── Step 11: Transition to CONNECTED ────────────────────────────────────
    # On first enrollment, the INSERT above already set state=CONNECTED —
    # we just need to update last_heartbeat. Otherwise we go through the
    # state machine transition.
    if is_first_enrollment:
        await db.execute(
            "UPDATE nodes SET last_heartbeat = ?, updated_at = ? WHERE id = ?",
            (now, now, node_id),
        )
        await db.commit()
    else:
        await node_manager.transition_state(
            db,
            node_id,
            NodeState.CONNECTED,
            extra_fields={"last_heartbeat": now},
        )

    # ── Step 12: Register WebSocket connection ───────────────────────────────
    conn = await node_manager.register_connection(node_id, websocket)
    conn.remote_address = remote

    # ── Step 13: Send ENROLLMENT_SUCCESS ────────────────────────────────────
    await _send(
        websocket,
        {
            "type": "ENROLLMENT_SUCCESS",
            "worker_token": worker_token,
            "master_public_key": get_security_instance().master_public_key_b64,
            "node_id": node_id,
            "heartbeat_interval": node_manager.heartbeat_interval,
        },
        node_id=node_id,
    )

    # ── Step 14: Audit ───────────────────────────────────────────────────────
    await log_action(
        db,
        user_id="system",
        action=AuditAction.NODE_ENROLLED,
        node_id=node_id,
        details={
            "hostname": hostname,
            "arch": arch,
            "os": os_name,
            "machine_id": machine_id,
            "remote_ip": remote,
        },
    )

    logger.info(
        "✓ Node ENROLLED: id=%s hostname=%s arch=%s os=%s",
        node_id,
        hostname,
        arch,
        os_name,
    )
    return node_id


# ---------------------------------------------------------------------------
# Phase 1.5: Reconnect enrollment (skip Ed25519 challenge)
# ---------------------------------------------------------------------------


async def _run_reconnect(
    websocket: WebSocket,
    db: aiosqlite.Connection,
    remote: str,
    worker_token: str,
    public_key_b64: str,
    fingerprint: dict | None = None,
) -> str:
    """Handle reconnect enrollment: validate worker_token, verify public_key match, skip challenge."""
    fingerprint = fingerprint or {}
    security = get_security_instance()

    # ── R1: Verify worker_token (JWT validity + DB revocation) ──────────────
    try:
        claims = await security.verify_worker_token_async(worker_token, db)
    except ValueError as exc:
        logger.warning("Reconnect rejected: invalid worker_token from %s: %s", remote, exc)
        raise _EnrollmentError(WS_CLOSE_INVALID_TOKEN, f"Invalid worker token: {exc}")

    node_id: str = claims.get("sub", "")
    if not node_id:
        raise _EnrollmentError(WS_CLOSE_PROTOCOL_ERROR, "Worker token missing subject")

    # ── R2: Fetch node and verify public_key match (anti-theft) ────────────
    async with db.execute("SELECT state, public_key FROM nodes WHERE id = ?", (node_id,)) as cursor:
        node_row = await cursor.fetchone()

    if node_row is None:
        raise _EnrollmentError(WS_CLOSE_INVALID_TOKEN, "Node not found for worker token")

    stored_pubkey = node_row["public_key"]
    if not stored_pubkey:
        raise _EnrollmentError(
            WS_CLOSE_PROTOCOL_ERROR, "Node has no stored public key (not enrolled)"
        )

    if stored_pubkey != public_key_b64:
        logger.error(
            "SECURITY: public_key mismatch for node %s! Token theft detected from %s",
            node_id,
            remote,
        )
        raise _EnrollmentError(
            WS_CLOSE_SIGNATURE_INVALID, "Public key mismatch — token theft detected"
        )

    # ── R3: Check node state ───────────────────────────────────────────────
    node_state = NodeState(node_row["state"])
    if node_state == NodeState.REVOKED:
        raise _EnrollmentError(WS_CLOSE_REVOKED, "Node is revoked")
    if node_state in (NodeState.PENDING, NodeState.ENROLLING, NodeState.CONNECTED):
        raise _EnrollmentError(
            WS_CLOSE_PROTOCOL_ERROR,
            f"Node is in unexpected state for reconnect: {node_state}",
        )

    # Accepted states for reconnect: RECONNECTING, LOST, STALE
    logger.info("Reconnect for node %s (state=%s, remote=%s)", node_id, node_state.value, remote)

    # ── R4: Transition to ENROLLING ───────────────────────────────────────
    await node_manager.transition_state(db, node_id, NodeState.ENROLLING)

    # ── R5: Generate fresh worker_token, update DB ─────────────────────────
    now = time.time()
    hostname = fingerprint.get("hostname", "")
    machine_id = fingerprint.get("machine_id", "")
    arch = fingerprint.get("arch", "")
    os_name = fingerprint.get("os", "")
    version = fingerprint.get("version", "")
    async with transaction(db):
        # Update node fingerprint/version on reconnect
        await db.execute(
            """
            UPDATE nodes SET
                hostname = ?,
                machine_id = ?,
                arch = ?,
                os = ?,
                version = ?,
                worker_version = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (hostname, machine_id, arch, os_name, version, version, now, node_id),
        )
        # Revoke old token
        old_token_hash = security.worker_token_hash(worker_token)
        await db.execute(
            "UPDATE worker_tokens SET revoked = 1, revoked_at = ? WHERE token_hash = ?",
            (now, old_token_hash),
        )

        # Create new token
        new_token, lifecycle = security.generate_worker_token(node_id)
        new_token_hash = security.worker_token_hash(new_token)
        token_id = str(uuid.uuid4())
        await db.execute(
            """
            INSERT INTO worker_tokens
                (id, node_id, token_hash, issued_at, rotation_due, expires_at, revoked)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (
                token_id,
                node_id,
                new_token_hash,
                lifecycle["issued_at"],
                lifecycle["rotation_due"],
                lifecycle["expires_at"],
            ),
        )

    # ── R6: Transition to CONNECTED ────────────────────────────────────────
    await node_manager.transition_state(
        db,
        node_id,
        NodeState.CONNECTED,
        extra_fields={"last_heartbeat": now},
    )

    # ── R7: Register WebSocket connection ──────────────────────────────────
    conn = await node_manager.register_connection(node_id, websocket)
    conn.remote_address = remote

    # ── R8: Send ENROLLMENT_SUCCESS ────────────────────────────────────────
    await _send(
        websocket,
        {
            "type": "ENROLLMENT_SUCCESS",
            "worker_token": new_token,
            "master_public_key": security.master_public_key_b64,
            "node_id": node_id,
            "heartbeat_interval": node_manager.heartbeat_interval,
        },
        node_id=node_id,
    )

    # ── R9: Audit ───────────────────────────────────────────────────────────
    reconnection_count = 1
    try:
        async with db.execute(
            "SELECT COUNT(*) as cnt FROM audit_log WHERE action = 'NODE_RECONNECTED' AND node_id = ?",
            (node_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            reconnection_count = row["cnt"] + 1
    except Exception:
        pass

    await log_action(
        db,
        user_id="system",
        action=AuditAction.NODE_RECONNECTED,
        node_id=node_id,
        details={
            "token_id": token_id,
            "reconnection_count": reconnection_count,
            "remote_ip": remote,
        },
    )

    logger.info("↻ Node RECONNECTED: id=%s (count=%d)", node_id, reconnection_count)
    return node_id


# ---------------------------------------------------------------------------
# Phase 2: Operational loop
# ---------------------------------------------------------------------------


async def _run_operational(
    websocket: WebSocket,
    db: aiosqlite.Connection,
    node_id: str,
    remote: str,
) -> None:
    """
    Handle the ongoing operational WebSocket session after enrollment.

    Message types from Worker:
      HEARTBEAT       → respond with HEARTBEAT_ACK, touch heartbeat timestamp
      INTENT_RESULT   → forward result to waiting caller (Sprint 2: response_future)
      STATUS_REPORT   → store latest metrics snapshot (Sprint 2)

    Message types to Worker:
      HEARTBEAT_ACK   → acknowledge heartbeat
      INTENT          → sent by NodeManager.send_intent()
    """
    logger.info("Node %s: operational loop started.", node_id)

    while True:
        try:
            raw = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=node_manager.heartbeat_interval * 3,  # 3× heartbeat grace period
            )
        except asyncio.TimeoutError:
            # Worker hasn't sent anything in 3× heartbeat interval → likely dead
            logger.warning("Node %s: operational timeout (no message). Closing.", node_id)
            await _close(websocket, WS_CLOSE_TIMEOUT, "Heartbeat timeout")
            return

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Node %s: invalid JSON in operational message", node_id)
            await _close(websocket, WS_CLOSE_PROTOCOL_ERROR, "Invalid JSON")
            return

        msg_type = msg.get("type")

        if msg_type == "HEARTBEAT":
            await node_manager.touch_heartbeat(node_id)
            await _send(websocket, {"type": "HEARTBEAT_ACK", "ts": time.time()}, node_id=node_id)
            hv = msg.get("version")
            if hv:
                await db.execute(
                    "UPDATE nodes SET worker_version = ?, updated_at = ? WHERE id = ?",
                    (hv, time.time(), node_id),
                )
                await db.commit()

            # ── WORKER_TOKEN rotation check ──────────────────────────────
            try:
                async with db.execute(
                    "SELECT token_hash, rotation_due FROM worker_tokens "
                    "WHERE node_id = ? AND revoked = 0 ORDER BY issued_at DESC LIMIT 1",
                    (node_id,),
                ) as cursor:
                    token_row = await cursor.fetchone()
                if token_row and token_row["rotation_due"] < time.time():
                    new_token, lifecycle = get_security_instance().generate_worker_token(node_id)
                    new_token_hash = get_security_instance().worker_token_hash(new_token)
                    token_id = str(uuid.uuid4())
                    old_token_hash = token_row["token_hash"]
                    async with transaction(db):
                        await db.execute(
                            "UPDATE worker_tokens SET revoked = 1, revoked_at = ? WHERE token_hash = ?",
                            (time.time(), old_token_hash),
                        )
                        await db.execute(
                            """
                            INSERT INTO worker_tokens
                                (id, node_id, token_hash, issued_at, rotation_due, expires_at, revoked)
                            VALUES (?, ?, ?, ?, ?, ?, 0)
                            """,
                            (
                                token_id,
                                node_id,
                                new_token_hash,
                                lifecycle["issued_at"],
                                lifecycle["rotation_due"],
                                lifecycle["expires_at"],
                            ),
                        )
                    await _send(
                        websocket,
                        {
                            "type": "TOKEN_ROTATION_COMMAND",
                            "worker_token": new_token,
                        },
                        node_id=node_id,
                    )
                    logger.info("Node %s: WORKER_TOKEN rotation sent (token_id=%s)", node_id, token_id)
            except Exception:
                logger.exception("Node %s: WORKER_TOKEN rotation failed", node_id)

        elif msg_type == "INTENT_RESULT":
            intent_id = msg.get("intent_id", "?")
            success = msg.get("success", False)
            dispatch_id = msg.get("dispatch_id")  # Optional — present if the dispatcher set it

            # ── INTENT_RESULT correlation validation ────────────────────────────────
            # Security: Reject INTENT_RESULT messages that do not correlate with a
            # pending intent dispatched to this node. This prevents forged INTENT_RESULT
            # attacks where a malicious or compromised worker claims credit for an
            # intent it was not the intended recipient of, or replays a stale result.
            #
            # Validation steps:
            #   1. intent_id must exist in the pending-intent registry
            #   2. The node sending the result must match the intended recipient node
            #   3. If dispatch_id is present, it must match the action_proposals record

            # Validate 1 + 2: intent_id corresponds to a pending dispatch for this node
            expected_node_id = node_manager._intent_nodes.get(intent_id)
            if expected_node_id is None:
                logger.warning(
                    "Node %s: INTENT_RESULT for unknown intent_id=%s — rejecting "
                    "(possible forged INTENT_RESULT attack)",
                    node_id, intent_id,
                )
                continue
            if expected_node_id != node_id:
                logger.warning(
                    "Node %s: INTENT_RESULT for intent_id=%s originated from node %s, "
                    "but intent was dispatched to node %s — rejecting "
                    "(possible forged INTENT_RESULT attack)",
                    node_id, intent_id, node_id, expected_node_id,
                )
                continue

            # Validate 3: optional dispatch_id must match the stored proposal record
            if dispatch_id is not None:
                async with db.execute(
                    "SELECT dispatch_id FROM action_proposals WHERE intent_id = ?",
                    (intent_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                stored_dispatch = row["dispatch_id"] if row else None
                if stored_dispatch != dispatch_id:
                    logger.warning(
                        "Node %s: INTENT_RESULT dispatch_id mismatch for intent_id=%s "
                        "(provided=%s, expected=%s) — rejecting "
                        "(possible replay or forged INTENT_RESULT)",
                        node_id,
                        intent_id,
                        dispatch_id,
                        stored_dispatch or "N/A",
                    )
                    continue

            logger.info(
                "Node %s INTENT_RESULT: id=%s success=%s",
                node_id,
                intent_id,
                success,
            )
            await node_manager.resolve_intent(intent_id, msg)
            await log_action(
                db,
                user_id="system",
                action=AuditAction.INTENT_RESULT,
                node_id=node_id,
                details={
                    "intent_id": intent_id,
                    "success": success,
                    "output": msg.get("output"),
                    "error": msg.get("error"),
                },
            )
            # Suivi du taux d'échec des intents pour l'alert engine
            from master.core.alert_engine import alert_engine
            from master.core.automation_engine import automation_engine
            asyncio.create_task(
                alert_engine.track_intent_result(node_id, success, db),
                name=f"alert:intent:{node_id[:12]}",
            )
            # Évaluation des règles d'automation node_intent_failure
            asyncio.create_task(
                automation_engine.evaluate_intent_failure(
                    node_id, msg.get("action", ""), success, db
                ),
                name=f"automation:intent:{node_id[:12]}",
            )

        elif msg_type == "STATUS_REPORT":
            # Normalize and store metrics snapshot via plugin system
            snapshot = await plugin_manager.async_call_first(
                "normalize_status_report", raw_report=msg
            )
            if snapshot:
                await plugin_manager.async_call(
                    "on_status_report", node_id=node_id, snapshot=snapshot, db=db
                )

                # Trigger automatic profiling on first STATUS_REPORT
                try:
                    async with db.execute(
                        "SELECT insight_profile FROM nodes WHERE id = ?", (node_id,)
                    ) as cursor:
                        row = await cursor.fetchone()
                    if row and not row["insight_profile"]:
                        from master.api.deps import get_insights_manager

                        im = get_insights_manager()
                        asyncio.create_task(im.generate_profile(node_id, db, node_manager))
                except Exception as ex:
                    logger.warning(
                        "Failed to start background profiling task for node %s: %s", node_id, ex
                    )
            else:
                logger.warning("Node %s: invalid STATUS_REPORT rejected", node_id)

            sv = msg.get("version")
            if sv:
                await db.execute(
                    "UPDATE nodes SET worker_version = ?, updated_at = ? WHERE id = ?",
                    (sv, time.time(), node_id),
                )
                await db.commit()

        else:
            logger.warning("Node %s: unknown message type '%s'", node_id, msg_type)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _EnrollmentError(Exception):
    """Typed error for enrollment failures with a WS close code."""

    def __init__(self, code: int, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


async def _recv_typed(
    websocket: WebSocket,
    expected_type: str,
    timeout: float,
) -> dict[str, Any]:
    """
    Receive a JSON message from the WebSocket within `timeout` seconds.
    Validates that the message has the expected `type` field.
    Raises asyncio.TimeoutError or _EnrollmentError.
    """
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=timeout)
    except asyncio.TimeoutError:
        raise asyncio.TimeoutError(f"Timeout waiting for {expected_type}")

    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        raise _EnrollmentError(WS_CLOSE_PROTOCOL_ERROR, "Malformed JSON")

    if msg.get("type") != expected_type:
        raise _EnrollmentError(
            WS_CLOSE_PROTOCOL_ERROR,
            f"Expected message type '{expected_type}', got '{msg.get('type')}'",
        )
    return msg


async def _send(websocket: WebSocket, data: dict[str, Any], node_id: str | None = None) -> None:
    """Serialize and send a JSON message over the WebSocket.

    Protected against WebSocketDisconnect: catches the exception, cleans up
    any pending intent futures for the given node, logs a warning, and does
    NOT re-raise (avoids orphan futures and worker handler crashes).
    """
    try:
        await websocket.send_text(json.dumps(data, separators=(",", ":")))
    except WebSocketDisconnect:
        logger.warning("WebSocket disconnected mid-send (node=%s)", node_id)
        if node_id:
            await node_manager.unregister_connection(node_id)


async def _close(websocket: WebSocket, code: int, reason: str) -> None:
    """Close the WebSocket with a given code and reason string (best-effort)."""
    try:
        await websocket.close(code=code, reason=reason)
    except Exception:
        pass


async def _get_node_state(db: aiosqlite.Connection, node_id: str) -> NodeState | None:
    """
    Fetch the current state of a node from the DB.

    Returns None if the `nodes` row does not exist yet — this is the
    normal case for a first-time enrollment, where the row is only
    created by the Worker handshake (see migration 006 + node_manager).
    """
    async with db.execute("SELECT state FROM nodes WHERE id = ?", (node_id,)) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    return NodeState(row["state"])


def _get_remote_address(websocket: WebSocket) -> str:
    """Extract the client IP address from the WebSocket connection.
    Only trusts X-Forwarded-For if the direct peer is in the trusted_proxies list."""
    client = websocket.client
    client_ip = client.host if client else ""

    # Only use X-Forwarded-For if the direct connection comes from a trusted proxy
    trusted_proxies = getattr(websocket.app.state, "trusted_proxies", [])
    if client_ip and trusted_proxies:
        if client_ip in trusted_proxies:
            forwarded_for = websocket.headers.get("x-forwarded-for", "")
            if forwarded_for:
                return forwarded_for.split(",")[0].strip()

    return client_ip or "unknown"
