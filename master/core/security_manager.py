"""
YouCloud AI Admin — Security Manager

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
from datetime import datetime, timezone
from functools import wraps
from typing import Annotated, Any

import aiosqlite
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
from cryptography.exceptions import InvalidSignature
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from master.config import settings

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

bearer_scheme = HTTPBearer(auto_error=False)
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# SecurityManager
# ---------------------------------------------------------------------------


class SecurityManager:
    """
    Centralizes all cryptographic operations for the Master Node.

    Instantiated once at startup and injected via FastAPI dependency.
    The master Ed25519 keypair is loaded/generated at construction time.
    """

    def __init__(self) -> None:
        self._server_secret: bytes = settings.server_secret_key.encode()
        self._jwt_secret: str = settings.jwt_secret_key
        self._master_private_key: Ed25519PrivateKey = self._load_or_generate_master_key()
        self._master_public_key: Ed25519PublicKey = self._master_private_key.public_key()
        # Cache the base64 public key (computed once)
        raw = self._master_public_key.public_bytes(
            encoding=Encoding.Raw, format=PublicFormat.Raw
        )
        self._master_public_key_b64: str = base64.urlsafe_b64encode(raw).decode()
        logger.info("SecurityManager initialized. Master public key: %s", self._master_public_key_b64)

    # -----------------------------------------------------------------------
    # Master Ed25519 keypair
    # -----------------------------------------------------------------------

    def _load_or_generate_master_key(self) -> Ed25519PrivateKey:
        """Load the persisted master Ed25519 private key, or generate and save it."""
        key_path = settings.master_key_path

        if os.path.exists(key_path):
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
            # Write with restrictive permissions (owner read-only)
            os.makedirs(os.path.dirname(os.path.abspath(key_path)), exist_ok=True)
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
            logger.warning("New master Ed25519 keypair generated and saved to %s", key_path)

        return private_key

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
            "expires_at": int(time.time()) + settings.join_token_ttl,
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

        # TTL check
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
            "rotation_due": now + settings.worker_token_rotation,
            "expires_at": now + settings.worker_token_ttl,
        }
        claims = {
            "sub": node_id,
            "type": "worker",
            "iat": int(now),
            "exp": int(lifecycle["expires_at"]),
            "rotation_due": int(lifecycle["rotation_due"]),
            "jti": str(uuid.uuid4()),
        }
        token = jwt.encode(claims, self._jwt_secret, algorithm=settings.jwt_algorithm)
        return token, lifecycle

    def verify_worker_token(self, token: str) -> dict[str, Any]:
        """
        Decode and verify a WORKER_TOKEN JWT.
        Raises ValueError on any failure.
        For DB revocation checking, use verify_worker_token_async().
        """
        try:
            claims = jwt.decode(token, self._jwt_secret, algorithms=[settings.jwt_algorithm])
        except JWTError as exc:
            raise ValueError(f"Invalid worker token: {exc}") from exc

        if claims.get("type") != "worker":
            raise ValueError("Token type mismatch: expected 'worker'")

        return claims

    async def verify_worker_token_async(
        self, token: str, db: "aiosqlite.Connection"
    ) -> dict[str, Any]:
        """
        Verify a WORKER_TOKEN and check revocation status in the database.
        Raises ValueError on any failure.
        """
        claims = jwt.decode(token, self._jwt_secret, algorithms=[settings.jwt_algorithm])
        if claims.get("type") != "worker":
            raise ValueError("Token type mismatch: expected 'worker'")
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

    async def verify_worker_token_async(
        self, token: str, db: "aiosqlite.Connection"
    ) -> dict[str, Any]:
        """
        Async version of verify_worker_token that also checks DB revocation.
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
            "exp": now + settings.jwt_access_token_ttl,
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(claims, self._jwt_secret, algorithm=settings.jwt_algorithm)

    def create_refresh_token(self, user_id: str) -> str:
        """Create a long-lived refresh token (opaque — just a JWT with limited claims)."""
        now = int(time.time())
        claims = {
            "sub": user_id,
            "type": "refresh",
            "iat": now,
            "exp": now + settings.jwt_refresh_token_ttl,
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(claims, self._jwt_secret, algorithm=settings.jwt_algorithm)

    def verify_access_token(self, token: str) -> dict[str, Any]:
        """Decode and verify a user access token. Raises HTTPException on failure."""
        try:
            claims = jwt.decode(token, self._jwt_secret, algorithms=[settings.jwt_algorithm])
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if claims.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token type mismatch",
            )
        return claims

    def verify_refresh_token(self, token: str) -> dict[str, Any]:
        """Decode and verify a refresh token."""
        try:
            claims = jwt.decode(token, self._jwt_secret, algorithms=[settings.jwt_algorithm])
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )
        if claims.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token type mismatch",
            )
        return claims

    # -----------------------------------------------------------------------
    # Password hashing
    # -----------------------------------------------------------------------

    @staticmethod
    def hash_password(plain: str) -> str:
        """Hash a plaintext password with bcrypt."""
        return _pwd_context.hash(plain)

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        """Verify a plaintext password against a bcrypt hash."""
        return _pwd_context.verify(plain, hashed)

    # -----------------------------------------------------------------------
    # RBAC FastAPI dependencies
    # -----------------------------------------------------------------------

    def get_current_user_claims(
        self,
        credentials: Annotated[
            HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
        ],
    ) -> dict[str, Any]:
        """
        FastAPI dependency: Extract and verify the JWT from the Authorization header.
        Returns the full claims dict on success.
        """
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return self.verify_access_token(credentials.credentials)

    def require_role(self, *required_roles: str):
        """
        FastAPI dependency factory: Require the caller to have one of the given roles.

        Usage in a router:
            @router.post("/secret", dependencies=[Depends(security.require_role("admin"))])

        Or with injection:
            @router.get("/data")
            async def get_data(claims=Depends(security.require_role("operator", "admin"))):
                ...
        """
        def _dependency(
            credentials: Annotated[
                HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
            ],
        ) -> dict[str, Any]:
            if credentials is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            claims = self.verify_access_token(credentials.credentials)
            user_role = claims.get("role", "viewer")

            # Check if the user's role satisfies ANY of the required roles
            user_level = ROLES_HIERARCHY.get(user_role, 0)
            required_level = min(
                ROLES_HIERARCHY.get(r, 99) for r in required_roles
            )
            if user_level < required_level:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Required: {required_roles}",
                )
            return claims

        return _dependency


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

security = SecurityManager()
