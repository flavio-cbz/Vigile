"""
Vigile — Security Manager

The cryptographic core of the Master Node. All token generation,
signature verification, and RBAC enforcement happens here.

Implements (natively, without external pattern libraries):
  - JOIN_TOKEN  : HMAC-SHA256 signed payload, single-use, 30-min TTL
  - Ed25519     : Challenge generation + signature verification
  - WORKER_TOKEN: JWT signed HS256, with rotation and revocation lifecycle
  - JWT/RBAC    : Access tokens for human users via python-jose
  - Password    : bcrypt hashing via passlib
  - Master Key  : Ed25519 keypair persisted on disk for Worker trust

Dependencies (from approved whitelist):
  - python-jose[cryptography] → JWT + Ed25519 via cryptography backend
  - passlib[bcrypt]           → password hashing
  - Python stdlib only        → hmac, hashlib, secrets, base64, json, time
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import uuid
from typing import Any

import aiosqlite
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from jose import JWTError, jwt
from passlib.context import CryptContext


class SecurityError(Exception):
    """Base exception for all security issues."""

    pass


class InvalidTokenError(SecurityError):
    """Raised when a token signature is invalid, format is incorrect, or token type mismatch."""

    pass


class ExpiredTokenError(SecurityError):
    """Raised when a token has expired."""

    pass


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pad_b64(s: str) -> str:
    """Normalize base64url string to have correct padding."""
    remainder = len(s) % 4
    return s + "=" * (4 - remainder) if remainder else s


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROLES_HIERARCHY: dict[str, int] = {
    "viewer": 1,
    "operator": 2,
    "admin": 3,
}

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# SecurityManager
# ---------------------------------------------------------------------------


class SecurityManager:
    """
    Centralizes all cryptographic operations for the Master Node.

    Instantiated once at startup and injected via FastAPI dependency.
    The master Ed25519 keypair must be pre-loaded and passed by the caller (edge layer).
    All TTL values are frozen at construction time — runtime config changes are invisible.
    """

    def __init__(
        self,
        server_secret: str,
        jwt_secret: str,
        jwt_algorithm: str = "HS256",
        join_token_ttl: int = 1800,
        worker_token_ttl: int = 2592000,
        worker_token_rotation: int = 604800,
        jwt_access_token_ttl: int = 3600,
        jwt_refresh_token_ttl: int = 86400,
        master_private_key: Ed25519PrivateKey | None = None,
    ) -> None:
        self._server_secret: bytes = server_secret.encode()
        self._jwt_secret: str = jwt_secret
        self._jwt_algorithm: str = jwt_algorithm
        self._join_token_ttl: int = join_token_ttl
        self._worker_token_ttl: int = worker_token_ttl
        self._worker_token_rotation: int = worker_token_rotation
        self._jwt_access_token_ttl: int = jwt_access_token_ttl
        self._jwt_refresh_token_ttl: int = jwt_refresh_token_ttl

        # Derive isolated JWT secrets for each token class (B7)
        jwt_secret_bytes = jwt_secret.encode()
        self._jwt_access_secret: str = hmac.new(
            jwt_secret_bytes, b"user_access_token", hashlib.sha256
        ).hexdigest()
        self._jwt_refresh_secret: str = hmac.new(
            jwt_secret_bytes, b"user_refresh_token", hashlib.sha256
        ).hexdigest()
        self._jwt_worker_secret: str = hmac.new(
            jwt_secret_bytes, b"worker_token", hashlib.sha256
        ).hexdigest()

        # Keypair: caller provides a pre-loaded Ed25519PrivateKey
        # If None, a fresh keypair is generated (dev mode, NOT for production)
        if master_private_key is None:
            master_private_key = Ed25519PrivateKey.generate()
            logger.warning("No master key provided — generated ephemeral key (dev mode)")
        self._master_private_key: Ed25519PrivateKey = master_private_key
        self._master_public_key: Ed25519PublicKey = self._master_private_key.public_key()

        raw = self._master_public_key.public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
        self._master_public_key_b64: str = base64.urlsafe_b64encode(raw).decode()
        self.audit_compromised: bool = False
        logger.info("SecurityManager initialized.")

    @property
    def master_public_key_b64(self) -> str:
        """Return the master public key as base64url-encoded string (for Workers)."""
        return self._master_public_key_b64

    # -----------------------------------------------------------------------
    # JOIN_TOKEN — HMAC-SHA256, single-use, 30-min TTL
    # -----------------------------------------------------------------------

    def generate_join_token(self, node_id: str, ip_prefix: str = "") -> tuple[str, dict]:
        """
        Generate a signed JOIN_TOKEN.

        Format: <HMAC-hex>.<base64url-payload>

        The payload is NOT encrypted (it's just base64). The HMAC signature
        is what guarantees authenticity and integrity.

        Returns:
            (token_string, payload_dict)
        """
        payload = {
            "node_id": node_id,
            "expires_at": int(time.time()) + self._join_token_ttl,
            "ip_prefix": ip_prefix,
            "single_use": True,
            "jti": str(uuid.uuid4()),
        }
        payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")

        sig = hmac.new(
            self._server_secret,
            payload_b64.encode(),
            "sha256",
        ).hexdigest()

        token = f"{sig}.{payload_b64}"
        return token, payload

    def decode_join_token(self, token: str) -> dict[str, Any]:
        """
        Decode and HMAC-verify a JOIN_TOKEN.

        Returns the payload dict on success.
        Raises ValueError with a specific reason on any failure.
        Does NOT check single_use status (that requires DB — see validate_join_token).
        """
        try:
            sig_hex, payload_b64 = token.split(".", 1)
        except ValueError:
            raise ValueError("Malformed token: missing separator")

        # Constant-time HMAC comparison (prevents timing attacks)
        expected_sig = hmac.new(
            self._server_secret,
            payload_b64.encode(),
            "sha256",
        ).hexdigest()

        if not hmac.compare_digest(sig_hex, expected_sig):
            raise ValueError("Invalid token signature")

        try:
            payload = json.loads(base64.urlsafe_b64decode(_pad_b64(payload_b64)).decode())
        except Exception:
            raise ValueError("Invalid token payload encoding")

        if time.time() > payload.get("expires_at", 0):
            raise ValueError("Token expired")

        return payload

    def join_token_hash(self, token: str) -> str:
        """SHA256 fingerprint of the raw token (for DB storage — never store raw token)."""
        return hashlib.sha256(token.encode()).hexdigest()

    # -----------------------------------------------------------------------
    # Ed25519 — Challenge/Response
    # -----------------------------------------------------------------------

    @staticmethod
    def generate_challenge() -> str:
        """Generate a 32-byte cryptographically random challenge, base64url-encoded."""
        raw = secrets.token_bytes(32)
        return base64.urlsafe_b64encode(raw).decode()

    @staticmethod
    def verify_ed25519_signature(
        public_key_b64: str,
        challenge_b64: str,
        signature_b64: str,
    ) -> bool:
        """
        Verify an Ed25519 signature produced by a Worker.

        Args:
            public_key_b64: Base64url-encoded 32-byte Ed25519 public key
            challenge_b64 : Base64url-encoded challenge sent by Master
            signature_b64 : Base64url-encoded 64-byte signature from Worker

        Returns:
            True if valid, False otherwise. Never raises.
        """
        try:
            pub_bytes = base64.urlsafe_b64decode(_pad_b64(public_key_b64))
            challenge_bytes = base64.urlsafe_b64decode(_pad_b64(challenge_b64))
            sig_bytes = base64.urlsafe_b64decode(_pad_b64(signature_b64))

            public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
            public_key.verify(sig_bytes, challenge_bytes)
            return True
        except InvalidSignature:
            return False
        except Exception as exc:
            logger.warning("Ed25519 verification error: %s", exc)
            return False

    # -----------------------------------------------------------------------
    # WORKER_TOKEN — JWT HS256 with rotation lifecycle
    # -----------------------------------------------------------------------

    def generate_worker_token(self, node_id: str) -> tuple[str, dict[str, float]]:
        """
        Generate a WORKER_TOKEN (JWT) for an enrolled node.

        Returns:
            (token_str, lifecycle_dict) where lifecycle contains:
              - issued_at, rotation_due, expires_at (all Unix timestamps)
        """
        now = time.time()
        lifecycle = {
            "issued_at": now,
            "rotation_due": now + self._worker_token_rotation,
            "expires_at": now + self._worker_token_ttl,
        }
        claims = {
            "sub": node_id,
            "type": "worker",
            "iat": int(now),
            "exp": int(lifecycle["expires_at"]),
            "rotation_due": int(lifecycle["rotation_due"]),
            "jti": str(uuid.uuid4()),
        }
        token = jwt.encode(claims, self._jwt_worker_secret, algorithm=self._jwt_algorithm)
        return token, lifecycle

    def verify_worker_token(self, token: str) -> dict[str, Any]:
        """
        Decode and verify a WORKER_TOKEN JWT.
        Raises ValueError on any failure.
        For DB revocation checking, use verify_worker_token_async().
        """
        try:
            claims = jwt.decode(token, self._jwt_worker_secret, algorithms=[self._jwt_algorithm])
        except JWTError as exc:
            try:
                unverified = jwt.get_unverified_claims(token)
                if unverified.get("type") != "worker":
                    raise ValueError("Token type mismatch: expected 'worker'")
            except JWTError:
                pass
            raise ValueError(f"Invalid worker token: {exc}") from exc

        if claims.get("type") != "worker":
            raise ValueError("Token type mismatch: expected 'worker'")

        return claims

    async def verify_worker_token_async(
        self, token: str, db: "aiosqlite.Connection"
    ) -> dict[str, Any]:
        """
        Verify a WORKER_TOKEN and check revocation in DB.
        """
        claims = self.verify_worker_token(token)
        token_hash = self.worker_token_hash(token)
        async with db.execute(
            "SELECT revoked FROM worker_tokens WHERE token_hash = ?",
            (token_hash,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise ValueError("Worker token not found in database")
        if row["revoked"]:
            raise ValueError("Worker token has been revoked")
        return claims

    def worker_token_hash(self, token: str) -> str:
        """SHA256 fingerprint for DB storage."""
        return hashlib.sha256(token.encode()).hexdigest()

    # -----------------------------------------------------------------------
    # USER JWT — HS256, access + refresh
    # -----------------------------------------------------------------------

    def create_access_token(self, user_id: str, username: str, role: str) -> str:
        """Create a short-lived JWT access token for a human user."""
        now = int(time.time())
        claims = {
            "sub": user_id,
            "username": username,
            "role": role,
            "type": "access",
            "iat": now,
            "exp": now + self._jwt_access_token_ttl,
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(claims, self._jwt_access_secret, algorithm=self._jwt_algorithm)

    @property
    def jwt_access_token_ttl(self) -> int:
        return self._jwt_access_token_ttl

    @property
    def jwt_refresh_token_ttl(self) -> int:
        return self._jwt_refresh_token_ttl

    @staticmethod
    def hash_refresh_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def create_refresh_token(self, user_id: str, family_id: str | None = None) -> tuple[str, str]:
        """Create a long-lived refresh token. Returns (token_str, family_id)."""
        if family_id is None:
            family_id = str(uuid.uuid4())
        now = int(time.time())
        claims = {
            "sub": user_id,
            "type": "refresh",
            "iat": now,
            "exp": now + self._jwt_refresh_token_ttl,
            "jti": str(uuid.uuid4()),
            "family_id": family_id,
        }
        token = jwt.encode(claims, self._jwt_refresh_secret, algorithm=self._jwt_algorithm)
        return token, family_id

    def verify_access_token(self, token: str) -> dict[str, Any]:
        """Decode and verify a user access token. Raises SecurityError on failure."""
        try:
            claims = jwt.decode(token, self._jwt_access_secret, algorithms=[self._jwt_algorithm])
        except jwt.ExpiredSignatureError as exc:
            raise ExpiredTokenError("Token has expired") from exc
        except JWTError as exc:
            try:
                unverified = jwt.get_unverified_claims(token)
                if unverified.get("type") != "access":
                    raise InvalidTokenError("Token type mismatch")
            except JWTError:
                pass
            raise InvalidTokenError("Invalid token") from exc

        if claims.get("type") != "access":
            raise InvalidTokenError("Token type mismatch")
        return claims

    def verify_refresh_token(self, token: str) -> dict[str, Any]:
        """Decode and verify a refresh token. Raises SecurityError on failure."""
        try:
            claims = jwt.decode(token, self._jwt_refresh_secret, algorithms=[self._jwt_algorithm])
        except jwt.ExpiredSignatureError as exc:
            raise ExpiredTokenError("Refresh token has expired") from exc
        except JWTError as exc:
            try:
                unverified = jwt.get_unverified_claims(token)
                if unverified.get("type") != "refresh":
                    raise InvalidTokenError("Token type mismatch")
            except JWTError:
                pass
            raise InvalidTokenError("Invalid refresh token") from exc

        if claims.get("type") != "refresh":
            raise InvalidTokenError("Token type mismatch")
        return claims

    @staticmethod
    def hash_password(plain: str) -> str:
        """Hash a plaintext password with bcrypt."""
        return _pwd_context.hash(plain)

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        """Verify a plaintext password against a bcrypt hash."""
        return _pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# Standalone helper: load/generate master Ed25519 key from disk
# This is an edge function — called from main.py lifespan, not from the class.
# ---------------------------------------------------------------------------


def load_or_generate_master_key(key_path: str) -> Ed25519PrivateKey:
    """Load the persisted master Ed25519 private key, or generate and save it.
    Safe to call multiple times (idempotent read/write).
    Checks file permissions on existing keys to warn if too permissive."""
    if os.path.exists(key_path):
        # Security: verify file permissions (must be 0o600 = owner-only)
        try:
            st_mode = os.stat(key_path).st_mode & 0o777
            if st_mode != 0o600:
                logger.warning(
                    "Master Ed25519 key has insecure permissions: %o (expected 600). "
                    "Fix with: chmod 600 %s",
                    st_mode,
                    key_path,
                )
        except OSError:
            logger.warning("Could not check permissions on %s", key_path)
        with open(key_path, "rb") as f:
            raw = f.read()
        private_key = Ed25519PrivateKey.from_private_bytes(raw)
        logger.info("Master Ed25519 key loaded from %s", key_path)
    else:
        private_key = Ed25519PrivateKey.generate()
        raw = private_key.private_bytes(
            encoding=Encoding.Raw,
            format=PrivateFormat.Raw,
            encryption_algorithm=NoEncryption(),
        )
        os.makedirs(os.path.dirname(os.path.abspath(key_path)), exist_ok=True)
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        logger.warning("New master Ed25519 keypair generated and saved to %s", key_path)
    return private_key


# ---------------------------------------------------------------------------
# Module-level instance (lazily initialized via init_security())
# ---------------------------------------------------------------------------

_security_instance: SecurityManager | None = None


def init_security(
    server_secret: str,
    jwt_secret: str,
    jwt_algorithm: str = "HS256",
    join_token_ttl: int = 1800,
    worker_token_ttl: int = 2592000,
    worker_token_rotation: int = 604800,
    jwt_access_token_ttl: int = 3600,
    jwt_refresh_token_ttl: int = 86400,
    master_private_key: Ed25519PrivateKey | None = None,
) -> SecurityManager:
    """Initialize the SecurityManager singleton with explicit parameters."""
    global _security_instance
    if _security_instance is not None:
        raise RuntimeError("SecurityManager already initialized")
    _security_instance = SecurityManager(
        server_secret=server_secret,
        jwt_secret=jwt_secret,
        jwt_algorithm=jwt_algorithm,
        join_token_ttl=join_token_ttl,
        worker_token_ttl=worker_token_ttl,
        worker_token_rotation=worker_token_rotation,
        jwt_access_token_ttl=jwt_access_token_ttl,
        jwt_refresh_token_ttl=jwt_refresh_token_ttl,
        master_private_key=master_private_key,
    )
    return _security_instance


def get_security_instance() -> SecurityManager:
    """Return the initialized SecurityManager or raise."""
    if _security_instance is None:
        raise RuntimeError("SecurityManager not initialized. Call init_security() first.")
    return _security_instance
