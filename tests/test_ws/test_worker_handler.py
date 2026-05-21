import pytest
import asyncio
import base64
import json
import uuid
import time
import types
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from master.core.security_manager import SecurityManager
from master.core.node_manager import NodeManager, NodeState, node_manager
from master.ws import worker_handler as ws_handler
from master.ws.worker_handler import worker_join_handler, _run_operational

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
        self.headers: dict[str, str] = {}
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


async def setup_token(db, security: SecurityManager, name: str = "test-node") -> tuple[str, str, str]:
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
                self._to_receive.append(json.dumps({
                    "type": "ENROLLMENT_RESPONSE",
                    "signature": base64.urlsafe_b64encode(sig).decode(),
                }))

    ws = EnrollWS([
        {"type": "ENROLLMENT_REQUEST", "join_token": join_token,
         "public_key": worker_pub_b64, "fingerprint": make_fingerprint()},
    ])

    await worker_join_handler(ws)
    assert any(m.get("type") == "ENROLLMENT_SUCCESS" for m in sent_msgs)
    assert any(m.get("node_id") == node_id for m in sent_msgs if m.get("type") == "ENROLLMENT_SUCCESS")
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
    ws = MockWebSocket([
        {"type": "ENROLLMENT_REQUEST", "join_token": tampered,
         "public_key": worker_pub_b64, "fingerprint": make_fingerprint()},
    ])
    await worker_join_handler(ws)
    assert ws.close_code == ws_handler.WS_CLOSE_INVALID_TOKEN


@pytest.mark.asyncio
async def test_enrollment_expired_token(db, security, worker_keys):
    """Expired token → close with WS_CLOSE_TOKEN_EXPIRED."""
    _, worker_pub_b64 = worker_keys
    node_id, join_token, _ = await setup_token(db, security, "ws-expired")

    await db.execute("UPDATE join_tokens SET expires_at = ? WHERE node_id = ?",
                     (time.time() - 10, node_id))
    await db.commit()

    ws = MockWebSocket([
        {"type": "ENROLLMENT_REQUEST", "join_token": join_token,
         "public_key": worker_pub_b64, "fingerprint": make_fingerprint()},
    ])
    await worker_join_handler(ws)
    assert ws.close_code == ws_handler.WS_CLOSE_TOKEN_EXPIRED


@pytest.mark.asyncio
async def test_enrollment_consumed_token(db, security, worker_keys):
    """Already consumed token → close with WS_CLOSE_TOKEN_CONSUMED."""
    _, worker_pub_b64 = worker_keys
    node_id, join_token, token_hash = await setup_token(db, security, "ws-consumed")

    await db.execute("UPDATE join_tokens SET consumed = 1 WHERE token_hash = ?", (token_hash,))
    await db.commit()

    ws = MockWebSocket([
        {"type": "ENROLLMENT_REQUEST", "join_token": join_token,
         "public_key": worker_pub_b64, "fingerprint": make_fingerprint()},
    ])
    await worker_join_handler(ws)
    assert ws.close_code == ws_handler.WS_CLOSE_TOKEN_CONSUMED


@pytest.mark.asyncio
async def test_enrollment_revoked_node(db, security, worker_keys):
    """REVOKED node → close with WS_CLOSE_REVOKED."""
    _, worker_pub_b64 = worker_keys
    node_id, join_token, _ = await setup_token(db, security, "ws-revoked")

    await db.execute("UPDATE nodes SET state = ? WHERE id = ?",
                     (NodeState.REVOKED.value, node_id))
    await db.commit()

    ws = MockWebSocket([
        {"type": "ENROLLMENT_REQUEST", "join_token": join_token,
         "public_key": worker_pub_b64, "fingerprint": make_fingerprint()},
    ])
    await worker_join_handler(ws)
    assert ws.close_code == ws_handler.WS_CLOSE_REVOKED


@pytest.mark.asyncio
async def test_enrollment_bad_message_type(db, security, worker_keys):
    """Wrong message type during enrollment → close with protocol error."""
    _, worker_pub_b64 = worker_keys
    _, join_token, _ = await setup_token(db, security, "ws-badtype")

    ws = MockWebSocket([
        {"type": "WRONG_TYPE", "join_token": join_token,
         "public_key": worker_pub_b64, "fingerprint": make_fingerprint()},
    ])
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
                self._to_receive.append(json.dumps({
                    "type": "ENROLLMENT_RESPONSE",
                    "signature": base64.urlsafe_b64encode(b"x" * 64).decode(),
                }))

    ws = BadSigWS([
        {"type": "ENROLLMENT_REQUEST", "join_token": join_token,
         "public_key": worker_pub_b64, "fingerprint": make_fingerprint()},
    ])
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
    assert len(hb_acks) >= 1


@pytest.mark.asyncio
async def test_operational_intent_result(db, security, worker_keys):
    """INTENT_RESULT is routed through resolve_intent."""
    worker_priv, worker_pub_b64 = worker_keys
    node_id, join_token, _ = await setup_token(db, security, "ws-intent")

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
        assert result.get("intent_id") == intent_id and result.get("success")
    except asyncio.TimeoutError:
        pytest.fail("future not resolved")
