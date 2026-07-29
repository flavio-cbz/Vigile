from __future__ import annotations

import asyncio
import base64
import json
import time
import types
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import WebSocketDisconnect

from master.core.node_manager import NodeManager, NodeState, node_manager
from master.core.security_manager import SecurityManager
from master.ws import worker_handler as ws_handler
from master.ws.worker_handler import _run_operational, _send, worker_join_handler


# Autouse fixture to setup node_manager settings for testing
@pytest.fixture(autouse=True)
def setup_node_manager():
    node_manager.heartbeat_interval = 30
    yield
    # Cleanup pending intents after each test
    node_manager._pending_intents.clear()


# Reuse MockWebSocket definition
class MockWebSocket:
    """Simulates a FastAPI WebSocket for testing."""

    def __init__(self, messages: list[dict] | None = None, app=None):
        self._sent: list[dict] = []
        self._to_receive: list[str] = []
        self._closed = False
        self.close_code: int | None = None
        self.close_reason: str = ""
        self.client = types.SimpleNamespace(host="127.0.0.1", port=8000)
        self.headers: dict[str, str] = {"x-forwarded-proto": "https"}
        self.url = types.SimpleNamespace(scheme="wss")
        self.app = app or types.SimpleNamespace(state=types.SimpleNamespace(trusted_proxies=[]))

        if messages:
            for m in messages:
                self._to_receive.append(json.dumps(m, separators=(",", ":")))

    async def accept(self):
        pass

    async def send_text(self, data: str):
        self._sent.append(json.loads(data))

    async def send_json(self, data: dict):
        self._sent.append(data)

    async def receive_text(self) -> str:
        await asyncio.sleep(0)  # Yield control to prevent "never awaited" warnings
        if self._closed:
            raise Exception("WebSocket closed")
        if not self._to_receive:
            raise asyncio.TimeoutError("No more messages in queue")
        return self._to_receive.pop(0)

    async def close(self, code: int = 1000, reason: str = ""):
        self._closed = True
        self.close_code = code
        self.close_reason = reason

    @property
    def host(self):
        return self.client.host

    def last_sent(self) -> dict | None:
        return self._sent[-1] if self._sent else None

    def sent_of_type(self, msg_type: str) -> list[dict]:
        return [m for m in self._sent if m.get("type") == msg_type]


def make_fingerprint(hostname: str = "test-host") -> dict:
    return {
        "hostname": hostname,
        "machine_id": "a" * 64,
        "arch": "x86_64",
        "os": "linux",
    }


async def setup_token(
    db, security: SecurityManager, name: str = "test-node"
) -> tuple[str, str, str]:
    """Create a PENDING node and return (node_id, join_token, token_hash)."""
    node_id = await node_manager.create_node(db, name=name)
    token, payload = security.generate_join_token(node_id)
    token_hash = security.join_token_hash(token)
    token_id = str(uuid.uuid4())
    now = time.time()
    await db.execute(
        """INSERT INTO join_tokens (id, node_id, token_hash, payload_b64, consumed, expires_at, created_at)
           VALUES (?, ?, ?, ?, 0, ?, ?)""",
        (token_id, node_id, token_hash, token.split(".", 1)[1], payload["expires_at"], now),
    )
    await db.commit()
    return node_id, token, token_hash


@pytest.fixture
def worker_keys():
    worker_priv = Ed25519PrivateKey.generate()
    worker_pub_bytes = worker_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    worker_pub_b64 = base64.urlsafe_b64encode(worker_pub_bytes).decode()
    return worker_priv, worker_pub_b64


@pytest.mark.asyncio
async def test_enrollment_success(db, security, worker_keys):
    """Full enrollment handshake: success path."""
    worker_priv, worker_pub_b64 = worker_keys
    node_id, join_token, _ = await setup_token(db, security, "ws-success")

    sent_msgs: list[dict] = []

    class EnrollWS(MockWebSocket):
        async def send_text(self, data: str):
            msg = json.loads(data)
            sent_msgs.append(msg)
            if msg.get("type") == "ENROLLMENT_CHALLENGE":
                challenge = msg["challenge"]
                sig = worker_priv.sign(base64.urlsafe_b64decode(challenge + "=="))
                self._to_receive.append(
                    json.dumps(
                        {
                            "type": "ENROLLMENT_RESPONSE",
                            "signature": base64.urlsafe_b64encode(sig).decode(),
                        }
                    )
                )

    ws = EnrollWS(
        [
            {
                "type": "ENROLLMENT_REQUEST",
                "join_token": join_token,
                "public_key": worker_pub_b64,
                "fingerprint": make_fingerprint(),
            },
        ]
    )

    await worker_join_handler(ws)
    assert any(m.get("type") == "ENROLLMENT_SUCCESS" for m in sent_msgs)
    assert any(
        m.get("node_id") == node_id for m in sent_msgs if m.get("type") == "ENROLLMENT_SUCCESS"
    )
    assert any(m.get("worker_token") for m in sent_msgs if m.get("type") == "ENROLLMENT_SUCCESS")

    async with db.execute("SELECT state FROM nodes WHERE id = ?", (node_id,)) as cur:
        row = await cur.fetchone()
    state = row["state"] if row else "?"
    assert state != "PENDING"
    assert state in ("CONNECTED", "RECONNECTING")


@pytest.mark.asyncio
async def test_enrollment_invalid_token(db, security, worker_keys):
    """Invalid HMAC signature → close with WS_CLOSE_INVALID_TOKEN."""
    _, worker_pub_b64 = worker_keys
    _, join_token, _ = await setup_token(db, security, "ws-invalid")

    tampered = join_token[:-5] + "XXXXX"
    ws = MockWebSocket(
        [
            {
                "type": "ENROLLMENT_REQUEST",
                "join_token": tampered,
                "public_key": worker_pub_b64,
                "fingerprint": make_fingerprint(),
            },
        ]
    )
    await worker_join_handler(ws)
    assert ws.close_code == ws_handler.WS_CLOSE_INVALID_TOKEN


@pytest.mark.asyncio
async def test_enrollment_expired_token(db, security, worker_keys):
    """Expired token → close with WS_CLOSE_TOKEN_EXPIRED."""
    _, worker_pub_b64 = worker_keys
    node_id, join_token, _ = await setup_token(db, security, "ws-expired")

    await db.execute(
        "UPDATE join_tokens SET expires_at = ? WHERE node_id = ?", (time.time() - 10, node_id)
    )
    await db.commit()

    ws = MockWebSocket(
        [
            {
                "type": "ENROLLMENT_REQUEST",
                "join_token": join_token,
                "public_key": worker_pub_b64,
                "fingerprint": make_fingerprint(),
            },
        ]
    )
    await worker_join_handler(ws)
    assert ws.close_code == ws_handler.WS_CLOSE_TOKEN_EXPIRED


@pytest.mark.asyncio
async def test_enrollment_consumed_token(db, security, worker_keys):
    """Already consumed token → close with WS_CLOSE_TOKEN_CONSUMED."""
    _, worker_pub_b64 = worker_keys
    node_id, join_token, token_hash = await setup_token(db, security, "ws-consumed")

    await db.execute("UPDATE join_tokens SET consumed = 1 WHERE token_hash = ?", (token_hash,))
    await db.commit()

    ws = MockWebSocket(
        [
            {
                "type": "ENROLLMENT_REQUEST",
                "join_token": join_token,
                "public_key": worker_pub_b64,
                "fingerprint": make_fingerprint(),
            },
        ]
    )
    await worker_join_handler(ws)
    assert ws.close_code == ws_handler.WS_CLOSE_TOKEN_CONSUMED


@pytest.mark.asyncio
async def test_enrollment_revoked_node(db, security, worker_keys):
    """Legacy REVOKED row → close with WS_CLOSE_REVOKED (back-compat path)."""
    _, worker_pub_b64 = worker_keys
    node_id, join_token, _ = await setup_token(db, security, "ws-revoked")

    await db.execute("UPDATE nodes SET state = ? WHERE id = ?", (NodeState.REVOKED.value, node_id))
    await db.commit()

    ws = MockWebSocket(
        [
            {
                "type": "ENROLLMENT_REQUEST",
                "join_token": join_token,
                "public_key": worker_pub_b64,
                "fingerprint": make_fingerprint(),
            },
        ]
    )
    await worker_join_handler(ws)
    assert ws.close_code == ws_handler.WS_CLOSE_REVOKED


@pytest.mark.asyncio
async def test_enrollment_deleted_node(db, security, worker_keys):
    """A deleted node row no longer blocks enrollment (anti-phantom).
    The handler no longer rejects with WS_CLOSE_INVALID_TOKEN 'Node not found'."""
    _, worker_pub_b64 = worker_keys
    node_id, join_token, _ = await setup_token(db, security, "ws-deleted")

    await db.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
    await db.commit()

    ws = MockWebSocket(
        [
            {
                "type": "ENROLLMENT_REQUEST",
                "join_token": join_token,
                "public_key": worker_pub_b64,
                "fingerprint": make_fingerprint(),
            },
        ]
    )
    await worker_join_handler(ws)
    assert ws.close_code != ws_handler.WS_CLOSE_INVALID_TOKEN


@pytest.mark.asyncio
async def test_enrollment_bad_message_type(db, security, worker_keys):
    """Wrong message type during enrollment → close with protocol error."""
    _, worker_pub_b64 = worker_keys
    _, join_token, _ = await setup_token(db, security, "ws-badtype")

    ws = MockWebSocket(
        [
            {
                "type": "WRONG_TYPE",
                "join_token": join_token,
                "public_key": worker_pub_b64,
                "fingerprint": make_fingerprint(),
            },
        ]
    )
    await worker_join_handler(ws)
    assert ws.close_code == ws_handler.WS_CLOSE_PROTOCOL_ERROR


@pytest.mark.asyncio
async def test_enrollment_bad_signature(db, security, worker_keys):
    """Invalid Ed25519 signature → close with WS_CLOSE_SIGNATURE_INVALID."""
    _, worker_pub_b64 = worker_keys
    _, join_token, _ = await setup_token(db, security, "ws-badsig")

    class BadSigWS(MockWebSocket):
        async def send_text(self, data: str):
            msg = json.loads(data)
            if msg.get("type") == "ENROLLMENT_CHALLENGE":
                self._to_receive.append(
                    json.dumps(
                        {
                            "type": "ENROLLMENT_RESPONSE",
                            "signature": base64.urlsafe_b64encode(b"x" * 64).decode(),
                        }
                    )
                )

    ws = BadSigWS(
        [
            {
                "type": "ENROLLMENT_REQUEST",
                "join_token": join_token,
                "public_key": worker_pub_b64,
                "fingerprint": make_fingerprint(),
            },
        ]
    )
    await worker_join_handler(ws)
    assert ws.close_code == ws_handler.WS_CLOSE_SIGNATURE_INVALID


@pytest.mark.asyncio
async def test_run_operational_direct(db):
    """Test _run_operational message dispatch directly."""
    node_id = "op-test-0000"
    sent: list[dict] = []

    class OpWS(MockWebSocket):
        async def send_text(self, data: str):
            msg = json.loads(data)
            sent.append(msg)

    ws = OpWS()
    # Pre-fill with test messages
    ws._to_receive = [
        json.dumps({"type": "HEARTBEAT"}),
        json.dumps({"type": "INTENT_RESULT", "intent_id": "i-1", "success": True}),
    ]

    await _run_operational(ws, db, node_id, "127.0.0.1")

    hb_acks = [m for m in sent if m.get("type") == "HEARTBEAT_ACK"]
    assert len(hb_acks) >= 1
    assert all(m.get("type") in ("HEARTBEAT_ACK",) for m in sent)


@pytest.mark.asyncio
async def test_operational_heartbeat(db, security, worker_keys):
    """HEARTBEAT → HEARTBEAT_ACK via full enrollment + operational."""
    worker_priv, worker_pub_b64 = worker_keys
    node_id, join_token, _ = await setup_token(db, security, "ws-hb")

    sent: list[dict] = []

    class HBWS(MockWebSocket):
        async def send_text(self, data: str):
            msg = json.loads(data)
            sent.append(msg)
            if msg.get("type") == "ENROLLMENT_CHALLENGE":
                sig = worker_priv.sign(base64.urlsafe_b64decode(msg["challenge"] + "=="))
                self._to_receive.append(
                    json.dumps(
                        {
                            "type": "ENROLLMENT_RESPONSE",
                            "signature": base64.urlsafe_b64encode(sig).decode(),
                        }
                    )
                )
            if msg.get("type") == "ENROLLMENT_SUCCESS":
                self._to_receive.append(json.dumps({"type": "HEARTBEAT"}))

    ws = HBWS(
        [
            {
                "type": "ENROLLMENT_REQUEST",
                "join_token": join_token,
                "public_key": worker_pub_b64,
                "fingerprint": make_fingerprint(),
            },
        ]
    )

    await worker_join_handler(ws)

    hb_acks = [m for m in sent if m.get("type") == "HEARTBEAT_ACK"]
    assert len(hb_acks) >= 1


@pytest.mark.asyncio
async def test_operational_intent_result(db, security, worker_keys):
    """INTENT_RESULT is routed through resolve_intent."""
    worker_priv, worker_pub_b64 = worker_keys
    node_id, join_token, _ = await setup_token(db, security, "ws-intent")

    intent_id = "test-intent-001"
    future = asyncio.get_running_loop().create_future()
    node_manager._pending_intents[intent_id] = future
    node_manager._intent_nodes[intent_id] = node_id

    class IntentWS(MockWebSocket):
        async def send_text(self, data: str):
            msg = json.loads(data)
            if msg.get("type") == "ENROLLMENT_CHALLENGE":
                sig = worker_priv.sign(base64.urlsafe_b64decode(msg["challenge"] + "=="))
                self._to_receive.append(
                    json.dumps(
                        {
                            "type": "ENROLLMENT_RESPONSE",
                            "signature": base64.urlsafe_b64encode(sig).decode(),
                        }
                    )
                )
            if msg.get("type") == "ENROLLMENT_SUCCESS":
                self._to_receive.append(
                    json.dumps(
                        {
                            "type": "INTENT_RESULT",
                            "intent_id": intent_id,
                            "success": True,
                            "output": "ok",
                        }
                    )
                )

    ws = IntentWS(
        [
            {
                "type": "ENROLLMENT_REQUEST",
                "join_token": join_token,
                "public_key": worker_pub_b64,
                "fingerprint": make_fingerprint(),
            },
        ]
    )

    await worker_join_handler(ws)

    try:
        result = await asyncio.wait_for(future, timeout=0.5)
        assert result.get("intent_id") == intent_id and result.get("success")
    except asyncio.TimeoutError:
        pytest.fail("future not resolved")


@pytest.mark.asyncio
async def test_send_disconnect_cleanup():
    """H1: _send() catches WebSocketDisconnect and cleans up pending intents."""
    node_id = "send-disconnect-node"
    intent_id = "test-intent-disconnect"

    # Setup: register a pending intent for this node
    future = asyncio.get_running_loop().create_future()
    node_manager._pending_intents[intent_id] = future
    node_manager._intent_nodes[intent_id] = node_id

    class DisconnectWS(MockWebSocket):
        async def send_text(self, data: str):
            raise WebSocketDisconnect(code=1000)

    ws = DisconnectWS()

    # _send must NOT raise — catches WebSocketDisconnect internally
    await _send(ws, {"type": "TEST"}, node_id=node_id)

    # Verify the pending intent was cleaned up (cancelled)
    assert (
        intent_id not in node_manager._pending_intents
    ), "pending intent must be removed on disconnect"
    assert future.done(), "future must be resolved (cancelled) on disconnect"

    # Cleanup test artifacts
    node_manager._pending_intents.pop(intent_id, None)
    node_manager._intent_nodes.pop(intent_id, None)


@pytest.mark.asyncio
async def test_send_disconnect_no_node_id():
    """H1: _send() handles WebSocketDisconnect gracefully without node_id."""

    class DisconnectWS(MockWebSocket):
        async def send_text(self, data: str):
            raise WebSocketDisconnect(code=1000)

    ws = DisconnectWS()

    # Must not raise even without node_id (graceful fallback)
    await _send(ws, {"type": "TEST"})


async def _setup_enrolled_node(db, security, name: str, worker_pub_b64: str) -> tuple[str, str]:
    """Helper: create a node, enroll it, and return (node_id, worker_token)."""
    node_id = await node_manager.create_node(db, name=name)
    token, payload = security.generate_join_token(node_id)
    token_hash = security.join_token_hash(token)
    now = time.time()
    await db.execute(
        """INSERT INTO join_tokens (id, node_id, token_hash, payload_b64, consumed, expires_at, created_at)
           VALUES (?, ?, ?, ?, 0, ?, ?)""",
        (
            str(uuid.uuid4()),
            node_id,
            token_hash,
            token.split(".", 1)[1],
            payload["expires_at"],
            now,
        ),
    )
    # Pre-set public_key and put node in LOST state (simulating previous enrollment)
    await db.execute(
        "UPDATE nodes SET public_key = ?, state = ?, enrolled_at = ? WHERE id = ?",
        (worker_pub_b64, NodeState.LOST.value, now, node_id),
    )
    await db.commit()
    # Generate a worker token and insert into DB
    worker_token, lifecycle = security.generate_worker_token(node_id)
    wt_hash = security.worker_token_hash(worker_token)
    await db.execute(
        """INSERT INTO worker_tokens (id, node_id, token_hash, issued_at, rotation_due, expires_at, revoked)
           VALUES (?, ?, ?, ?, ?, ?, 0)""",
        (
            str(uuid.uuid4()),
            node_id,
            wt_hash,
            lifecycle["issued_at"],
            lifecycle["rotation_due"],
            lifecycle["expires_at"],
        ),
    )
    await db.commit()
    return node_id, worker_token


@pytest.mark.asyncio
async def test_enrollment_reconnect_success(db, security, worker_keys):
    """Reconnect with valid worker_token → success, skip challenge, ENROLLMENT_SUCCESS."""
    worker_priv, worker_pub_b64 = worker_keys
    node_id, worker_token = await _setup_enrolled_node(db, security, "ws-reconnect", worker_pub_b64)

    sent_msgs: list[dict] = []

    class ReconnectWS(MockWebSocket):
        async def send_text(self, data: str):
            msg = json.loads(data)
            sent_msgs.append(msg)

    ws = ReconnectWS()
    # Call _run_reconnect directly (not full worker_join_handler) to test only the enrollment phase
    result_node_id = await ws_handler._run_reconnect(
        ws, db, "127.0.0.1", worker_token, worker_pub_b64
    )

    assert result_node_id == node_id, "Should return the correct node_id"

    # Verify ENROLLMENT_SUCCESS sent
    success_msgs = [m for m in sent_msgs if m.get("type") == "ENROLLMENT_SUCCESS"]
    assert len(success_msgs) >= 1, "Should receive ENROLLMENT_SUCCESS"
    assert success_msgs[0].get("node_id") == node_id
    assert success_msgs[0].get("worker_token"), "Should receive fresh worker_token"

    # Verify no challenge was sent (Ed25519 skipped)
    challenge_msgs = [m for m in sent_msgs if m.get("type") == "ENROLLMENT_CHALLENGE"]
    assert len(challenge_msgs) == 0, "Ed25519 challenge should be skipped on reconnect"

    # Verify old worker token is revoked
    old_hash = security.worker_token_hash(worker_token)
    async with db.execute(
        "SELECT revoked FROM worker_tokens WHERE token_hash = ?", (old_hash,)
    ) as cur:
        row = await cur.fetchone()
    assert row is not None
    assert row["revoked"] == 1

    # Verify NODE_RECONNECTED audit entry
    async with db.execute(
        "SELECT action, details_json FROM audit_log WHERE node_id = ? AND action = 'NODE_RECONNECTED'",
        (node_id,),
    ) as cur:
        row = await cur.fetchone()
    assert row is not None, "NODE_RECONNECTED audit entry must exist"
    details = json.loads(row["details_json"])
    assert "token_id" in details
    assert details["reconnection_count"] >= 1


@pytest.mark.asyncio
async def test_enrollment_reconnect_public_key_mismatch(db, security, worker_keys):
    """Reconnect with wrong public_key → anti-theft protection, close with error."""
    _, worker_pub_b64 = worker_keys
    node_id, worker_token = await _setup_enrolled_node(
        db, security, "ws-reconnect-pk", worker_pub_b64
    )

    # Use a DIFFERENT public key for the reconnect request (simulating token theft)
    wrong_key = base64.urlsafe_b64encode(b"x" * 32).decode()

    ws = MockWebSocket(
        [
            {
                "type": "ENROLLMENT_REQUEST",
                "join_token": "",
                "worker_token": worker_token,
                "reconnect": True,
                "public_key": wrong_key,
                "fingerprint": make_fingerprint(),
            },
        ]
    )

    await worker_join_handler(ws)

    # Should close with signature invalid (anti-theft code)
    assert (
        ws.close_code == ws_handler.WS_CLOSE_SIGNATURE_INVALID
    ), "Should reject reconnect with wrong public key"


@pytest.mark.asyncio
async def test_enrollment_reconnect_revoked_node(db, security, worker_keys):
    """Reconnect with legacy REVOKED row → close with WS_CLOSE_REVOKED (back-compat)."""
    _, worker_pub_b64 = worker_keys
    node_id, worker_token = await _setup_enrolled_node(
        db, security, "ws-reconnect-rev", worker_pub_b64
    )

    # Set node to REVOKED state
    await db.execute("UPDATE nodes SET state = ? WHERE id = ?", (NodeState.REVOKED.value, node_id))
    await db.commit()

    ws = MockWebSocket(
        [
            {
                "type": "ENROLLMENT_REQUEST",
                "join_token": "",
                "worker_token": worker_token,
                "reconnect": True,
                "public_key": worker_pub_b64,
                "fingerprint": make_fingerprint(),
            },
        ]
    )

    await worker_join_handler(ws)
    assert ws.close_code == ws_handler.WS_CLOSE_REVOKED


@pytest.mark.asyncio
async def test_enrollment_reconnect_deleted_node(db, security, worker_keys):
    """Reconnect with a hard-deleted node → close with WS_CLOSE_INVALID_TOKEN."""
    _, worker_pub_b64 = worker_keys
    node_id, worker_token = await _setup_enrolled_node(
        db, security, "ws-reconnect-del", worker_pub_b64
    )

    await db.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
    await db.commit()

    ws = MockWebSocket(
        [
            {
                "type": "ENROLLMENT_REQUEST",
                "join_token": "",
                "worker_token": worker_token,
                "reconnect": True,
                "public_key": worker_pub_b64,
                "fingerprint": make_fingerprint(),
            },
        ]
    )

    await worker_join_handler(ws)
    assert ws.close_code == ws_handler.WS_CLOSE_INVALID_TOKEN


@pytest.mark.asyncio
async def test_enrollment_reconnect_revoked_token(db, security, worker_keys):
    """Reconnect with revoked worker_token → close with WS_CLOSE_INVALID_TOKEN."""
    _, worker_pub_b64 = worker_keys
    node_id, worker_token = await _setup_enrolled_node(
        db, security, "ws-reconnect-wtrev", worker_pub_b64
    )

    # Revoke the worker token
    wt_hash = security.worker_token_hash(worker_token)
    await db.execute("UPDATE worker_tokens SET revoked = 1 WHERE token_hash = ?", (wt_hash,))
    await db.commit()

    ws = MockWebSocket(
        [
            {
                "type": "ENROLLMENT_REQUEST",
                "join_token": "",
                "worker_token": worker_token,
                "reconnect": True,
                "public_key": worker_pub_b64,
                "fingerprint": make_fingerprint(),
            },
        ]
    )

    await worker_join_handler(ws)
    assert ws.close_code == ws_handler.WS_CLOSE_INVALID_TOKEN


@pytest.mark.asyncio
async def test_enrollment_reconnect_expired_token(db, security, worker_keys):
    """Reconnect with expired worker_token → close with WS_CLOSE_INVALID_TOKEN."""
    _, worker_pub_b64 = worker_keys
    node_id, worker_token = await _setup_enrolled_node(
        db, security, "ws-reconnect-exp", worker_pub_b64
    )

    # Revoke the token to simulate expired/unusable token
    wt_hash = security.worker_token_hash(worker_token)
    await db.execute("UPDATE worker_tokens SET revoked = 1 WHERE token_hash = ?", (wt_hash,))
    await db.commit()

    ws = MockWebSocket(
        [
            {
                "type": "ENROLLMENT_REQUEST",
                "join_token": "",
                "worker_token": worker_token,
                "reconnect": True,
                "public_key": worker_pub_b64,
                "fingerprint": make_fingerprint(),
            },
        ]
    )

    await worker_join_handler(ws)
    assert ws.close_code == ws_handler.WS_CLOSE_INVALID_TOKEN
