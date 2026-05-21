import time
import base64
import json
import hmac
import hashlib
import pytest
from fastapi import HTTPException
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from master.core.security_manager import SecurityManager



def test_join_token_round_trip(security: SecurityManager):
    token, payload = security.generate_join_token("node-123", "10.0.0.")
    decoded = security.decode_join_token(token)
    assert decoded["node_id"] == "node-123"
    assert decoded["ip_prefix"] == "10.0.0."
    assert decoded["single_use"] is True
    assert decoded["expires_at"] > time.time() + 1700


def test_hmac_tamper_detection(security: SecurityManager):
    token, _ = security.generate_join_token("node-123", "10.0.0.")
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(ValueError) as excinfo:
        security.decode_join_token(tampered)
    assert "signature" in str(excinfo.value).lower() or "invalid" in str(excinfo.value).lower()


def test_expired_token_rejected(security: SecurityManager):
    old_payload = {
        "node_id": "x",
        "expires_at": int(time.time()) - 10,
        "ip_prefix": "",
        "single_use": True,
        "jti": "abc",
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(old_payload, sort_keys=True).encode()).decode().rstrip("=")
    sig = hmac.new(security._server_secret, payload_b64.encode(), "sha256").hexdigest()
    expired_token = f"{sig}.{payload_b64}"
    with pytest.raises(ValueError) as excinfo:
        security.decode_join_token(expired_token)
    assert "expired" in str(excinfo.value).lower()


def test_ed25519_challenge_response(security: SecurityManager):
    worker_priv = Ed25519PrivateKey.generate()
    worker_pub_bytes = worker_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    worker_pub_b64 = base64.urlsafe_b64encode(worker_pub_bytes).decode()

    challenge = security.generate_challenge()
    assert len(base64.urlsafe_b64decode(challenge + "==")) == 32

    challenge_bytes = base64.urlsafe_b64decode(challenge + "==")
    sig_bytes = worker_priv.sign(challenge_bytes)
    sig_b64 = base64.urlsafe_b64encode(sig_bytes).decode()

    assert security.verify_ed25519_signature(worker_pub_b64, challenge, sig_b64)

    # Corrupt signature
    bad_sig = sig_b64[:-4] + "XXXX"
    assert not security.verify_ed25519_signature(worker_pub_b64, challenge, bad_sig)


def test_worker_token(security: SecurityManager):
    wt, lifecycle = security.generate_worker_token("node-456")
    wt_claims = security.verify_worker_token(wt)
    assert wt_claims["sub"] == "node-456"
    assert wt_claims["type"] == "worker"
    assert lifecycle["expires_at"] > lifecycle["rotation_due"] > lifecycle["issued_at"]


def test_jwt_access_token(security: SecurityManager):
    at = security.create_access_token("user-1", "admin_user", "admin")
    at_claims = security.verify_access_token(at)
    assert at_claims["sub"] == "user-1"
    assert at_claims["role"] == "admin"


def test_password_hashing(security: SecurityManager):
    h = security.hash_password("mysecret")
    assert security.verify_password("mysecret", h)
    assert not security.verify_password("wrong", h)


def test_master_public_key(security: SecurityManager):
    mpk = security.master_public_key_b64
    assert len(mpk) == 44


def test_refresh_token_lifecycle(security: SecurityManager):
    token, family_id = security.create_refresh_token("user-1")
    assert family_id is not None
    assert len(family_id) > 0

    claims = security.verify_refresh_token(token)
    assert claims["sub"] == "user-1"
    assert claims["type"] == "refresh"
    assert claims["family_id"] == family_id

    # Test reuse of family_id
    token2, family_id2 = security.create_refresh_token("user-1", family_id=family_id)
    assert family_id2 == family_id

    claims2 = security.verify_refresh_token(token2)
    assert claims2["family_id"] == family_id

    # Test invalid token
    from master.core.security_manager import SecurityError
    with pytest.raises(SecurityError) as excinfo:
        security.verify_refresh_token("invalid-token")
    assert "invalid" in str(excinfo.value).lower()

    # Test wrong token type
    access_token = security.create_access_token("user-1", "user", "viewer")
    with pytest.raises(SecurityError) as excinfo:
        security.verify_refresh_token(access_token)
    assert "type mismatch" in str(excinfo.value).lower()


async def test_verify_worker_token_async(security: SecurityManager, db):
    # Insert node first since worker_tokens has a foreign key to nodes
    await db.execute(
        "INSERT INTO nodes (id, name, state, created_at, updated_at) "
        "VALUES ('node-123', 'Test Node', 'PENDING', 123.0, 123.0)"
    )
    await db.commit()

    token, lifecycle = security.generate_worker_token("node-123")
    token_hash = security.worker_token_hash(token)

    # 1. Verification fails if token is not in DB
    with pytest.raises(ValueError) as excinfo:
        await security.verify_worker_token_async(token, db)
    assert "not found in database" in str(excinfo.value).lower()

    # 2. Insert into DB (unrevoked)
    await db.execute(
        "INSERT INTO worker_tokens (id, node_id, token_hash, issued_at, rotation_due, expires_at, revoked) "
        "VALUES ('tok-1', 'node-123', ?, ?, ?, ?, 0)",
        (token_hash, lifecycle["issued_at"], lifecycle["rotation_due"], lifecycle["expires_at"])
    )
    await db.commit()

    claims = await security.verify_worker_token_async(token, db)
    assert claims["sub"] == "node-123"

    # 3. Revoke token
    await db.execute(
        "UPDATE worker_tokens SET revoked = 1 WHERE token_hash = ?",
        (token_hash,)
    )
    await db.commit()

    with pytest.raises(ValueError) as excinfo:
        await security.verify_worker_token_async(token, db)
    assert "revoked" in str(excinfo.value).lower()


def test_require_role(security: SecurityManager):
    from master.api.deps import require_role
    dependency = require_role("operator", "admin")

    # 1. No credentials
    with pytest.raises(HTTPException) as excinfo:
        dependency(None)
    assert excinfo.value.status_code == 401

    # 2. Viewer role (insufficient)
    viewer_token = security.create_access_token("user-1", "viewer_user", "viewer")
    from fastapi.security import HTTPAuthorizationCredentials
    viewer_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=viewer_token)
    with pytest.raises(HTTPException) as excinfo:
        dependency(viewer_creds)
    assert excinfo.value.status_code == 403
    assert "insufficient permissions" in excinfo.value.detail.lower()

    # 3. Operator role (sufficient)
    op_token = security.create_access_token("user-2", "op_user", "operator")
    op_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=op_token)
    claims = dependency(op_creds)
    assert claims["sub"] == "user-2"
    assert claims["role"] == "operator"

    # 4. Admin role (sufficient)
    admin_token = security.create_access_token("user-3", "admin_user", "admin")
    admin_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=admin_token)
    claims = dependency(admin_creds)
    assert claims["sub"] == "user-3"
    assert claims["role"] == "admin"


def test_token_hashing_utilities(security: SecurityManager):
    test_token = "some-random-token-string"
    expected_hash = hashlib.sha256(test_token.encode()).hexdigest()

    assert security.join_token_hash(test_token) == expected_hash
    assert security.worker_token_hash(test_token) == expected_hash
    assert security.hash_refresh_token(test_token) == expected_hash


def test_load_or_generate_master_key(temp_dir):
    import os
    from cryptography.hazmat.primitives.serialization import PrivateFormat, NoEncryption
    from master.core.security_manager import load_or_generate_master_key

    key_path = os.path.join(temp_dir, "master.key")

    # 1. Generates if not exists
    key1 = load_or_generate_master_key(key_path)
    assert os.path.exists(key_path)

    # 2. Loads if exists
    key2 = load_or_generate_master_key(key_path)

    # Verify keys are identical
    raw1 = key1.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    raw2 = key2.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    assert raw1 == raw2


def test_security_manager_ephemeral_key():
    sm = SecurityManager(
        server_secret="server_secret",
        jwt_secret="jwt_secret",
        master_private_key=None
    )
    assert sm.master_public_key_b64 is not None


def test_security_manager_already_initialized():
    import master.core.security_manager as sm
    with pytest.raises(RuntimeError) as excinfo:
        sm.init_security("sec", "jwt")
    assert "already initialized" in str(excinfo.value)


def test_security_manager_not_initialized():
    import master.core.security_manager as sm
    # Temporarily clear _security_instance
    orig = sm._security_instance
    sm._security_instance = None
    try:
        with pytest.raises(RuntimeError) as excinfo:
            sm.get_security_instance()
        assert "not initialized" in str(excinfo.value)
    finally:
        sm._security_instance = orig


def test_decode_join_token_malformed(security: SecurityManager):
    with pytest.raises(ValueError) as excinfo:
        security.decode_join_token("no_separator")
    assert "missing separator" in str(excinfo.value)

    # To test invalid base64 encoding, we must provide a signature that is valid
    # for the invalid base64 payload.
    import hmac
    payload_b64 = "invalid_b64_!!!"
    sig = hmac.new(security._server_secret, payload_b64.encode(), "sha256").hexdigest()
    token = f"{sig}.{payload_b64}"

    with pytest.raises(ValueError) as excinfo:
        security.decode_join_token(token)
    assert "payload encoding" in str(excinfo.value).lower()


def test_verify_ed25519_signature_exception(security: SecurityManager):
    assert not security.verify_ed25519_signature("!!!", "challenge", "sig")


def test_verify_access_token_type_mismatch(security: SecurityManager):
    from master.core.security_manager import SecurityError
    rt, _ = security.create_refresh_token("user-1")
    with pytest.raises(SecurityError) as excinfo:
        security.verify_access_token(rt)
    assert "type mismatch" in str(excinfo.value).lower()

    # Cover JWTError
    with pytest.raises(SecurityError) as excinfo:
        security.verify_access_token("invalid_token_string")
    assert "invalid" in str(excinfo.value).lower()


def test_verify_worker_token_errors(security: SecurityManager):
    with pytest.raises(ValueError) as excinfo:
        security.verify_worker_token("invalid_token")
    assert "invalid worker token" in str(excinfo.value).lower()

    at = security.create_access_token("u", "u", "viewer")
    with pytest.raises(ValueError) as excinfo:
        security.verify_worker_token(at)
    assert "type mismatch" in str(excinfo.value).lower()


def test_jwt_token_isolation(security: SecurityManager):
    from master.core.security_manager import SecurityError
    # Create access token, try decoding it as refresh or worker token
    at = security.create_access_token("user-1", "user", "viewer")
    
    # Should fail decoding as refresh token
    with pytest.raises(SecurityError):
        security.verify_refresh_token(at)
        
    # Should fail decoding as worker token
    with pytest.raises(ValueError):
        security.verify_worker_token(at)

    # Create refresh token
    rt, _ = security.create_refresh_token("user-1")
    
    # Should fail decoding as access token
    with pytest.raises(SecurityError):
        security.verify_access_token(rt)
        
    # Should fail decoding as worker token
    with pytest.raises(ValueError):
        security.verify_worker_token(rt)

    # Create worker token
    wt, _ = security.generate_worker_token("node-123")
    
    # Should fail decoding as access token
    with pytest.raises(SecurityError):
        security.verify_access_token(wt)
        
    # Should fail decoding as refresh token
    with pytest.raises(SecurityError):
        security.verify_refresh_token(wt)

