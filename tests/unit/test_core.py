#!/usr/bin/env python3
"""
Vigile — Sprint 1 Smoke Test Suite
Validates all core modules without requiring a running server.
"""

import asyncio
import os
import sys
import tempfile
import time

# Make sure we can import from the master package
import pathlib
PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent.parent)
sys.path.insert(0, PROJECT_ROOT)

# Point DB and key to temp files
tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_PATH"] = os.path.join(tmpdir, "test.db")
os.environ["MASTER_KEY_PATH"] = os.path.join(tmpdir, "master.key")
os.environ["SERVER_SECRET_KEY"] = "test_secret_key_for_smoke_tests_only"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_for_smoke_tests_only"

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
results = []


def check(name: str, condition: bool, detail: str = ""):
    icon = PASS if condition else FAIL
    print(f"  {icon} {name}" + (f" ({detail})" if detail else ""))
    results.append((name, condition))
    return condition


# ─── 1. SecurityManager ──────────────────────────────────────────────────────
print("\n🔐 SecurityManager")

from master.core.security_manager import SecurityManager
sec = SecurityManager()

# JOIN_TOKEN round-trip (now returns tuple)
token, payload = sec.generate_join_token("node-123", "10.0.0.")
payload = sec.decode_join_token(token)
check("JOIN_TOKEN generation", payload["node_id"] == "node-123")
check("JOIN_TOKEN ip_prefix", payload["ip_prefix"] == "10.0.0.")
check("JOIN_TOKEN single_use", payload["single_use"] is True)
check("JOIN_TOKEN expires_at TTL", payload["expires_at"] > time.time() + 1700)

# HMAC tamper detection
tampered = token[:-5] + "XXXXX"
try:
    sec.decode_join_token(tampered)
    check("HMAC tamper detection", False, "should have raised")
except ValueError as e:
    check("HMAC tamper detection", "signature" in str(e).lower() or "invalid" in str(e).lower(), str(e))

# Expired token
old_payload = {"node_id": "x", "expires_at": int(time.time()) - 10, "ip_prefix": "", "single_use": True, "jti": "abc"}
import base64, json, hmac, hashlib
payload_b64 = base64.urlsafe_b64encode(json.dumps(old_payload, sort_keys=True).encode()).decode().rstrip("=")
sig = hmac.new(sec._server_secret, payload_b64.encode(), "sha256").hexdigest()
expired_token = f"{sig}.{payload_b64}"
try:
    sec.decode_join_token(expired_token)
    check("Expired token rejected", False, "should have raised")
except ValueError as e:
    check("Expired token rejected", "expired" in str(e).lower(), str(e))

# Ed25519 challenge/response
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

worker_priv = Ed25519PrivateKey.generate()
worker_pub_bytes = worker_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
worker_pub_b64 = base64.urlsafe_b64encode(worker_pub_bytes).decode()

challenge = sec.generate_challenge()
check("Challenge is 32 bytes", len(base64.urlsafe_b64decode(challenge + "==")) == 32)
challenge_bytes = base64.urlsafe_b64decode(challenge + "==")
sig_bytes = worker_priv.sign(challenge_bytes)
sig_b64 = base64.urlsafe_b64encode(sig_bytes).decode()

check("Ed25519 valid signature accepted", sec.verify_ed25519_signature(worker_pub_b64, challenge, sig_b64))

# Corrupt signature
bad_sig = sig_b64[:-4] + "XXXX"
check("Ed25519 invalid signature rejected", not sec.verify_ed25519_signature(worker_pub_b64, challenge, bad_sig))

# WORKER_TOKEN
wt, lifecycle = sec.generate_worker_token("node-456")
wt_claims = sec.verify_worker_token(wt)
check("WORKER_TOKEN subject", wt_claims["sub"] == "node-456")
check("WORKER_TOKEN type", wt_claims["type"] == "worker")
check("WORKER_TOKEN lifecycle", lifecycle["expires_at"] > lifecycle["rotation_due"] > lifecycle["issued_at"])

# JWT access token
at = sec.create_access_token("user-1", "admin_user", "admin")
at_claims = sec.verify_access_token(at)
check("JWT access token sub", at_claims["sub"] == "user-1")
check("JWT access token role", at_claims["role"] == "admin")

# Password hashing
h = sec.hash_password("mysecret")
check("Password hash verify", sec.verify_password("mysecret", h))
check("Password hash wrong rejected", not sec.verify_password("wrong", h))

# Master public key
mpk = sec.master_public_key_b64
check("Master public key is 44 chars (32 bytes b64)", len(mpk) == 44)


# ─── 2. PluginManager ────────────────────────────────────────────────────────
print("\n🔌 PluginManager")

from master.core.plugin_manager import PluginManager
pm = PluginManager()

results_list = []
pm.register("test_hook", lambda x: x * 2, plugin_name="double")
pm.register("test_hook", lambda x: x + 10, plugin_name="adder")

out = pm.call("test_hook", x=5)
check("Hook dispatch (2 impls)", sorted(out) == [10, 15], str(out))
check("call_first returns first non-None", pm.call_first("test_hook", x=3) in [6, 13])
check("Empty hook returns []", pm.call("nonexistent_hook") == [])
check("has_hook True", pm.has_hook("test_hook"))
check("has_hook False for unknown", not pm.has_hook("nonexistent_hook"))

# Async hook
async def async_double(x):
    return x * 3

pm.register("async_hook", async_double, plugin_name="async_triple")

async def test_async_pm():
    out = await pm.async_call("async_hook", x=4)
    check("Async hook dispatch", out == [12], str(out))

asyncio.run(test_async_pm())

# Plugin load from dir (create a temp plugin file)
with tempfile.TemporaryDirectory() as plugin_dir:
    plugin_code = '''
def register(pm):
    pm.register("file_hook", lambda: "from_file", plugin_name="file_plugin")
'''
    with open(os.path.join(plugin_dir, "test_plugin.py"), "w") as f:
        f.write(plugin_code)
    pm2 = PluginManager()
    loaded = pm2.load_plugins_from_dir(plugin_dir)
    check("Plugin loaded from dir", "test_plugin" in loaded, str(loaded))
    check("Plugin hook registered", pm2.call("file_hook") == ["from_file"])


# ─── 3. Database + Migrations ────────────────────────────────────────────────
print("\n🗄️  Database + Migrations")

async def test_db():
    from master.db.database import init_db, close_db, transaction
    from master.db.migrations import run_migrations

    db = await init_db()
    check("DB connection opened", db is not None)

    await run_migrations(db)
    check("Migrations ran without error", True)

    # Check all tables exist
    for table in ["nodes", "join_tokens", "worker_tokens", "users", "audit_log"]:
        async with db.execute(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
        ) as cur:
            row = await cur.fetchone()
        check(f"Table '{table}' exists", row is not None)

    # Check admin user was seeded
    async with db.execute("SELECT username, role FROM users WHERE username='admin'") as cur:
        user = await cur.fetchone()
    check("Admin user seeded", user is not None)
    check("Admin role is 'admin'", user["role"] == "admin")

    # Check audit genesis entry
    async with db.execute("SELECT sequence, action, previous_hash FROM audit_log ORDER BY sequence") as cur:
        first = await cur.fetchone()
    check("Genesis audit entry exists", first is not None)
    check("Genesis sequence=1", first["sequence"] == 1)
    check("Genesis previous_hash is zeros", first["previous_hash"] == "0" * 64)

    await close_db()
    check("DB closed cleanly", True)

asyncio.run(test_db())


# ─── 4. Audit Trail ──────────────────────────────────────────────────────────
print("\n📋 Audit Trail")

async def test_audit():
    from master.db.database import init_db, close_db
    from master.db.migrations import run_migrations
    from master.core.audit import log_action, verify_chain, get_recent_entries, compute_entry_hash

    # Fresh DB
    tmp_path = os.path.join(tempfile.mkdtemp(), "test_audit.db")
    os.environ["DATABASE_PATH"] = tmp_path
    from master.db.database import reset_db as _reset_db
    await _reset_db()
    from master.config import settings
    settings.database_path = tmp_path

    db = await init_db()
    await run_migrations(db)

    # Log several actions
    e1 = await log_action(db, user_id="user-1", action="TEST_ACTION_A", node_id="node-1", details={"k": "v1"})
    e2 = await log_action(db, user_id="user-2", action="TEST_ACTION_B", node_id="node-2", details={"k": "v2"})
    e3 = await log_action(db, user_id="user-1", action="TEST_ACTION_C", details={"k": "v3"})

    check("log_action returns entry_id", all(isinstance(e, str) and len(e) == 36 for e in [e1, e2, e3]))

    # Verify chain
    report = await verify_chain(db)
    check("Audit chain valid after appends", report["valid"], str(report.get("error")))
    check("Audit chain has entries", report["total_entries"] >= 4)

    # Tamper with an entry and verify detection
    async with db.execute("SELECT id, entry_hash FROM audit_log ORDER BY sequence DESC LIMIT 1") as cur:
        last = await cur.fetchone()

    await db.execute("UPDATE audit_log SET details_json='{\"tampered\":true}' WHERE id=?", (last["id"],))
    await db.commit()

    tampered_report = await verify_chain(db)
    check("Tampered entry detected", not tampered_report["valid"], "chain should be broken")
    check("Tamper at correct sequence", tampered_report["first_broken_sequence"] is not None)

    # Recent entries
    entries = await get_recent_entries(db, limit=5)
    check("get_recent_entries returns list", isinstance(entries, list))
    check("Entries have entry_hash field", all("entry_hash" in e for e in entries))

    await close_db()
    await _reset_db()
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)

asyncio.run(test_audit())


# ─── 5. NodeManager ──────────────────────────────────────────────────────────
print("\n🖥️  NodeManager")

async def test_node_manager():
    from master.db.database import init_db, close_db
    from master.db.migrations import run_migrations
    from master.core.node_manager import NodeManager, NodeState

    tmp_path = os.path.join(tempfile.mkdtemp(), "test_nm.db")
    os.environ["DATABASE_PATH"] = tmp_path
    from master.db.database import reset_db as _reset_db
    await _reset_db()
    from master.config import settings
    settings.database_path = tmp_path

    db = await init_db()
    await run_migrations(db)

    nm = NodeManager()

    # Create a node
    node_id = await nm.create_node(db, name="test-node-01", ip_prefix="10.0.")
    check("create_node returns UUID", len(node_id) == 36)

    # Fetch it
    node = await nm.get_node(db, node_id)
    check("get_node returns dict", node is not None)
    check("Node initial state is PENDING", node["state"] == "PENDING")
    check("Node name set", node["name"] == "test-node-01")

    # Valid transition PENDING → ENROLLING
    await nm.transition_state(db, node_id, NodeState.ENROLLING)
    node = await nm.get_node(db, node_id)
    check("PENDING → ENROLLING transition OK", node["state"] == "ENROLLING")

    # Invalid transition ENROLLING → LOST (not allowed directly)
    try:
        await nm.transition_state(db, node_id, NodeState.LOST)
        check("Invalid transition rejected", False, "should have raised")
    except ValueError:
        check("Invalid transition rejected", True)

    # Valid: ENROLLING → CONNECTED
    await nm.transition_state(db, node_id, NodeState.CONNECTED)
    node = await nm.get_node(db, node_id)
    check("ENROLLING → CONNECTED transition OK", node["state"] == "CONNECTED")

    # Test RECONNECTING → CONNECTED (reconnection path)
    await nm.transition_state(db, node_id, NodeState.RECONNECTING)
    await nm.transition_state(db, node_id, NodeState.CONNECTED)
    node = await nm.get_node(db, node_id)
    check("RECONNECTING → CONNECTED transition OK", node["state"] == "CONNECTED")

    # list_nodes
    nodes = await nm.list_nodes(db)
    check("list_nodes returns list", isinstance(nodes, list) and len(nodes) >= 1)

    # list_nodes with state filter
    pending_nodes = await nm.list_nodes(db, state="PENDING")
    check("list_nodes filtered by state", all(n["state"] == "PENDING" for n in pending_nodes))

    # is_connected (no real WS)
    check("is_connected False without WS", not await nm.is_connected(node_id))

    # Test invalid field in extra_fields
    try:
        await nm.transition_state(db, node_id, NodeState.LOST, extra_fields={"invalid_field": "x"})
        check("transition_state rejects invalid field", False, "should have raised")
    except ValueError:
        check("transition_state rejects invalid field", True)

    await close_db()
    await _reset_db()
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)

asyncio.run(test_node_manager())


# ─── Summary ─────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
total = len(results)
print(f"Results: {passed}/{total} passed", end="")
if failed:
    print(f"  ({failed} FAILED)")
    print("\nFailed tests:")
    for name, ok in results:
        if not ok:
            print(f"  {FAIL} {name}")
    sys.exit(1)
else:
    print(" 🎉")

import shutil
shutil.rmtree(tmpdir, ignore_errors=True)
