import time
import base64
import json
import hmac
import pytest
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
