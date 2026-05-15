#!/usr/bin/env python3
"""
Vigile — WebSocket Handler Tests
Tests the full enrollment handshake and operational loop.
"""

import asyncio
import base64
import json
import os
import sys
import tempfile
import time
import types
import uuid

import pathlib
PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent.parent)
sys.path.insert(0, PROJECT_ROOT)

# Point DB and key to temp files
tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_PATH"] = os.path.join(tmpdir, "test_ws.db")
os.environ["MASTER_KEY_PATH"] = os.path.join(tmpdir, "master_ws.key")
os.environ["SERVER_SECRET_KEY"] = "test_secret_ws"
os.environ["JWT_SECRET_KEY"] = "test_jwt_ws"

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
results = []


def check(name: str, condition: bool, detail: str = ""):
    icon = PASS if condition else FAIL
    print(f"  {icon} {name}" + (f" ({detail})" if detail else ""))
    results.append((name, condition))
    return condition


# ── Mock WebSocket ──────────────────────────────────────────────────

class MockWebSocket:
    """Simulates a FastAPI WebSocket for testing."""

    def __init__(self, messages: list[dict] | None = None):
        self._sent: list[dict] = []
        self._to_receive: list[str] = []
        self._closed = False
        self.close_code: int | None = None
        self.close_reason: str = ""
        self.client = types.SimpleNamespace(host="127.0.0.1", port=8000)
        self.headers: dict[str, str] = {}

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


# ── Test Setup ──────────────────────────────────────────────────────

from master.db.database import reset_db, init_db, close_db
from master.db.migrations import run_migrations
from master.core.security_manager import init_security, get_security_instance
from master.core.node_manager import node_manager, NodeState
from master.ws import worker_handler as ws_handler
from master.ws.worker_handler import worker_join_handler

# Pre-create a node + generate a JOIN_TOKEN
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

worker_priv = Ed25519PrivateKey.generate()
worker_pub_bytes = worker_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
worker_pub_b64 = base64.urlsafe_b64encode(worker_pub_bytes).decode()

# Initialize SecurityManager singleton for test
init_security(
    server_secret=os.environ["SERVER_SECRET_KEY"],
    jwt_secret=os.environ["JWT_SECRET_KEY"],
    master_private_key=Ed25519PrivateKey.generate(),
)
security = get_security_instance()


async def setup_token(name: str = "test-node") -> tuple[str, str, str]:
    """Create a PENDING node and return (node_id, join_token, token_hash)."""
    db = None
    try:
        db = await init_db()
        await run_migrations(db)
        from master.api.deps import get_db
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
    finally:
        if db:
            await close_db()
            await reset_db()


async def setup_db():
    """Initialize a fresh DB with migrations."""
    db = await init_db()
    await run_migrations(db)
    return db


def make_fingerprint(hostname: str = "test-host") -> dict:
    return {
        "hostname": hostname,
        "machine_id": "a" * 64,
        "arch": "x86_64",
        "os": "linux",
    }


# ─── Tests ──────────────────────────────────────────────────────────

print("\n🔌 WebSocket Handler — Enrollment")

async def test_enrollment_success():
    """Full enrollment handshake: success path."""
    await reset_db()
    node_id, join_token, _ = await setup_token("ws-success")
    db = await setup_db()

    # Build the enrollment response: worker signs the challenge
    sent_msgs: list[dict] = []

    class EnrollWS(MockWebSocket):
        async def send_text(self, data: str):
            msg = json.loads(data)
            sent_msgs.append(msg)
            if msg.get("type") == "ENROLLMENT_CHALLENGE":
                challenge = msg["challenge"]
                sig = worker_priv.sign(base64.urlsafe_b64decode(challenge + "=="))
                self._to_receive.append(json.dumps({
                    "type": "ENROLLMENT_RESPONSE",
                    "signature": base64.urlsafe_b64encode(sig).decode(),
                }))

    ws = EnrollWS([
        {"type": "ENROLLMENT_REQUEST", "join_token": join_token,
         "public_key": worker_pub_b64, "fingerprint": make_fingerprint()},
    ])

    await worker_join_handler(ws)
    check("Enrollment success: ENROLLMENT_SUCCESS sent",
          any(m.get("type") == "ENROLLMENT_SUCCESS" for m in sent_msgs))
    check("Enrollment success: node_id returned",
          any(m.get("node_id") == node_id for m in sent_msgs if m.get("type") == "ENROLLMENT_SUCCESS"))
    check("Enrollment success: worker_token present",
          any(m.get("worker_token") for m in sent_msgs if m.get("type") == "ENROLLMENT_SUCCESS"))

    # Verify the node left PENDING (successful enrollment, final state may be RECONNECTING)
    async with db.execute("SELECT state FROM nodes WHERE id = ?", (node_id,)) as cur:
        row = await cur.fetchone()
    state = row["state"] if row else "?"
    check("Enrollment success: state != PENDING", state != "PENDING", f"actual={state}")
    check("Enrollment success: valid final state", state in ("CONNECTED", "RECONNECTING"), f"actual={state}")

    await close_db()
    await reset_db()


async def test_enrollment_invalid_token():
    """Invalid HMAC signature → close with WS_CLOSE_INVALID_TOKEN."""
    await reset_db()
    _, join_token, _ = await setup_token("ws-invalid")
    db = await setup_db()

    # Tamper with token
    tampered = join_token[:-5] + "XXXXX"
    ws = MockWebSocket([
        {"type": "ENROLLMENT_REQUEST", "join_token": tampered,
         "public_key": worker_pub_b64, "fingerprint": make_fingerprint()},
    ])
    await worker_join_handler(ws)
    check("Invalid token → close code 4400", ws.close_code == ws_handler.WS_CLOSE_INVALID_TOKEN)

    await close_db()
    await reset_db()


async def test_enrollment_expired_token():
    """Expired token → close with WS_CLOSE_TOKEN_EXPIRED."""
    await reset_db()
    node_id, join_token, _ = await setup_token("ws-expired")
    db = await setup_db()

    # Manually expire the token in DB
    await db.execute("UPDATE join_tokens SET expires_at = ? WHERE node_id = ?",
                     (time.time() - 10, node_id))
    await db.commit()

    ws = MockWebSocket([
        {"type": "ENROLLMENT_REQUEST", "join_token": join_token,
         "public_key": worker_pub_b64, "fingerprint": make_fingerprint()},
    ])
    await worker_join_handler(ws)
    check("Expired token → close code 4402", ws.close_code == ws_handler.WS_CLOSE_TOKEN_EXPIRED)

    await close_db()
    await reset_db()


async def test_enrollment_consumed_token():
    """Already consumed token → close with WS_CLOSE_TOKEN_CONSUMED."""
    await reset_db()
    node_id, join_token, token_hash = await setup_token("ws-consumed")
    db = await setup_db()

    await db.execute("UPDATE join_tokens SET consumed = 1 WHERE token_hash = ?", (token_hash,))
    await db.commit()

    ws = MockWebSocket([
        {"type": "ENROLLMENT_REQUEST", "join_token": join_token,
         "public_key": worker_pub_b64, "fingerprint": make_fingerprint()},
    ])
    await worker_join_handler(ws)
    check("Consumed token → close code 4401", ws.close_code == ws_handler.WS_CLOSE_TOKEN_CONSUMED)

    await close_db()
    await reset_db()


async def test_enrollment_revoked_node():
    """REVOKED node → close with WS_CLOSE_REVOKED."""
    await reset_db()
    node_id, join_token, _ = await setup_token("ws-revoked")
    db = await setup_db()

    await db.execute("UPDATE nodes SET state = ? WHERE id = ?",
                     (NodeState.REVOKED.value, node_id))
    await db.commit()

    ws = MockWebSocket([
        {"type": "ENROLLMENT_REQUEST", "join_token": join_token,
         "public_key": worker_pub_b64, "fingerprint": make_fingerprint()},
    ])
    await worker_join_handler(ws)
    check("Revoked node → close code 4403", ws.close_code == ws_handler.WS_CLOSE_REVOKED)

    await close_db()
    await reset_db()


async def test_enrollment_bad_message_type():
    """Wrong message type during enrollment → close with protocol error."""
    await reset_db()
    _, join_token, _ = await setup_token("ws-badtype")
    db = await setup_db()

    ws = MockWebSocket([
        {"type": "WRONG_TYPE", "join_token": join_token,
         "public_key": worker_pub_b64, "fingerprint": make_fingerprint()},
    ])
    await worker_join_handler(ws)
    check("Wrong enrollment message type → close code 4420", ws.close_code == ws_handler.WS_CLOSE_PROTOCOL_ERROR)

    await close_db()
    await reset_db()


async def test_enrollment_bad_signature():
    """Invalid Ed25519 signature → close with WS_CLOSE_SIGNATURE_INVALID."""
    await reset_db()
    _, join_token, _ = await setup_token("ws-badsig")
    db = await setup_db()

    class BadSigWS(MockWebSocket):
        async def send_text(self, data: str):
            msg = json.loads(data)
            if msg.get("type") == "ENROLLMENT_CHALLENGE":
                self._to_receive.append(json.dumps({
                    "type": "ENROLLMENT_RESPONSE",
                    "signature": base64.urlsafe_b64encode(b"x" * 64).decode(),
                }))

    ws = BadSigWS([
        {"type": "ENROLLMENT_REQUEST", "join_token": join_token,
         "public_key": worker_pub_b64, "fingerprint": make_fingerprint()},
    ])
    await worker_join_handler(ws)
    check("Bad signature → close code 4410", ws.close_code == ws_handler.WS_CLOSE_SIGNATURE_INVALID)

    await close_db()
    await reset_db()


print("\n🔌 WebSocket Handler — Enrollment Tests")
asyncio.run(test_enrollment_success())
asyncio.run(test_enrollment_invalid_token())
asyncio.run(test_enrollment_expired_token())
asyncio.run(test_enrollment_consumed_token())
asyncio.run(test_enrollment_revoked_node())
asyncio.run(test_enrollment_bad_message_type())
asyncio.run(test_enrollment_bad_signature())

print("\n🔌 WebSocket Handler — Operational Phase")

async def _run_operational_direct():
    """Test _run_operational message dispatch directly."""
    from master.ws.worker_handler import _run_operational
    db = await setup_db()
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
    check("_run_operational: HEARTBEAT → HEARTBEAT_ACK", len(hb_acks) >= 1, str(len(hb_acks)))
    check("_run_operational: unknown msg type ignored",
          all(m.get("type") in ("HEARTBEAT_ACK",) for m in sent))

    await close_db()
    await reset_db()


async def test_operational_heartbeat():
    """HEARTBEAT → HEARTBEAT_ACK via full enrollment + operational."""
    await reset_db()
    node_id, join_token, _ = await setup_token("ws-hb")
    db = await setup_db()

    sent: list[dict] = []

    class HBWS(MockWebSocket):
        async def send_text(self, data: str):
            msg = json.loads(data)
            sent.append(msg)
            if msg.get("type") == "ENROLLMENT_CHALLENGE":
                sig = worker_priv.sign(base64.urlsafe_b64decode(msg["challenge"] + "=="))
                self._to_receive.append(json.dumps({
                    "type": "ENROLLMENT_RESPONSE",
                    "signature": base64.urlsafe_b64encode(sig).decode(),
                }))
            if msg.get("type") == "ENROLLMENT_SUCCESS":
                self._to_receive.append(json.dumps({"type": "HEARTBEAT"}))

    ws = HBWS([
        {"type": "ENROLLMENT_REQUEST", "join_token": join_token,
         "public_key": worker_pub_b64, "fingerprint": make_fingerprint()},
    ])

    await worker_join_handler(ws)

    hb_acks = [m for m in sent if m.get("type") == "HEARTBEAT_ACK"]
    check("Full flow: HEARTBEAT → HEARTBEAT_ACK", len(hb_acks) >= 1, str(len(hb_acks)))

    await close_db()
    await reset_db()


async def test_operational_intent_result():
    """INTENT_RESULT is routed through resolve_intent."""
    await reset_db()
    node_id, join_token, _ = await setup_token("ws-intent")
    db = await setup_db()

    intent_id = "test-intent-001"
    future = asyncio.get_running_loop().create_future()
    node_manager._pending_intents[intent_id] = future

    class IntentWS(MockWebSocket):
        async def send_text(self, data: str):
            msg = json.loads(data)
            if msg.get("type") == "ENROLLMENT_CHALLENGE":
                sig = worker_priv.sign(base64.urlsafe_b64decode(msg["challenge"] + "=="))
                self._to_receive.append(json.dumps({
                    "type": "ENROLLMENT_RESPONSE",
                    "signature": base64.urlsafe_b64encode(sig).decode(),
                }))
            if msg.get("type") == "ENROLLMENT_SUCCESS":
                self._to_receive.append(json.dumps({
                    "type": "INTENT_RESULT",
                    "intent_id": intent_id,
                    "success": True,
                    "output": "ok",
                }))

    ws = IntentWS([
        {"type": "ENROLLMENT_REQUEST", "join_token": join_token,
         "public_key": worker_pub_b64, "fingerprint": make_fingerprint()},
    ])

    await worker_join_handler(ws)

    try:
        result = await asyncio.wait_for(future, timeout=0.5)
        check("Full flow: INTENT_RESULT resolves pending future",
              result.get("intent_id") == intent_id and result.get("success"))
    except asyncio.TimeoutError:
        check("Full flow: INTENT_RESULT resolves pending future", False, "future not resolved")

    await close_db()
    await reset_db()


asyncio.run(_run_operational_direct())


asyncio.run(test_operational_heartbeat())
asyncio.run(test_operational_intent_result())

# ── Summary ─────────────────────────────────────────────────────────
print("\n" + "=" * 60)
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
total = len(results)
print(f"Results: {passed}/{total} passed", end="")
if failed:
    print(f"  ({failed} FAILED)")
    for name, ok in results:
        if not ok:
            print(f"  {FAIL} {name}")
    sys.exit(1)
else:
    print(" 🎉")

import shutil
shutil.rmtree(tmpdir, ignore_errors=True)
