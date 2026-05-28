"""
Vigile — Authentication API

Endpoints:
  POST /api/auth/login           → username + password → access_token + refresh_token
  POST /api/auth/refresh         → refresh_token → new access_token + rotated refresh_token
  POST /api/auth/logout          → invalidate refresh token
  POST /api/auth/change-password → change user password (and reset must_change_password)
  GET  /api/auth/me              → current user profile (requires valid JWT)
"""

import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from master.api.deps import CurrentUser, DB, get_security
from master.api.demo_data import DEMO_USERNAME, DEMO_PASSWORD, DEMO_USER_ID, is_demo
from master.core.security_manager import SecurityManager, SecurityError
from master.core.rate_limiter import rate_limiter
from master.core.audit import log_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=256)


class UserProfile(BaseModel):
    user_id: str
    username: str
    role: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and obtain JWT tokens",
    responses={
        401: {"description": "Invalid credentials"},
        403: {"description": "Account deactivated"},
        429: {"description": "Too many requests"},
    },
    dependencies=[Depends(rate_limiter.dependency(10))],
)
async def login(
    body: LoginRequest,
    db: DB,
    sec: SecurityManager = Depends(get_security),
) -> TokenResponse:
    """
    Authenticate a human user with username + password.

    Returns:
      - access_token  : short-lived JWT (default 1h) for API calls
      - refresh_token : long-lived token (default 24h) for token renewal
    """
    # Demo user shortcut — no DB access
    if body.username == DEMO_USERNAME and body.password == DEMO_PASSWORD:
        access_token = sec.create_access_token(
            user_id=DEMO_USER_ID,
            username=DEMO_USERNAME,
            role="admin",
        )
        refresh_token, _ = sec.create_refresh_token(user_id=DEMO_USER_ID)
        logger.info("Demo user '%s' logged in (no DB).", DEMO_USERNAME)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=sec.jwt_access_token_ttl,
        )

    # Fetch user from DB
    async with db.execute(
        "SELECT id, username, password_hash, role, is_active FROM users WHERE username = ?",
        (body.username,),
    ) as cursor:
        user = await cursor.fetchone()

    # Constant-time failure path (mitigate user enumeration)
    if user is None:
        try:
            sec.verify_password("dummy", sec.hash_password("dummy"))
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not sec.verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deactivated",
        )

    # Issue tokens
    access_token = sec.create_access_token(
        user_id=user["id"],
        username=user["username"],
        role=user["role"],
    )
    refresh_token, family_id = sec.create_refresh_token(user_id=user["id"])

    # Store refresh token in DB
    token_id = str(uuid.uuid4())
    token_hash = sec.hash_refresh_token(refresh_token)
    now = time.time()
    expires_at = now + sec.jwt_refresh_token_ttl

    await db.execute(
        """
        INSERT INTO refresh_tokens (id, user_id, token_hash, family_id, issued_at, expires_at, revoked)
        VALUES (?, ?, ?, ?, ?, ?, 0)
        """,
        (token_id, user["id"], token_hash, family_id, now, expires_at),
    )

    # Update last_login
    await db.execute(
        "UPDATE users SET last_login = ? WHERE id = ?",
        (time.time(), user["id"]),
    )

    await log_action(
        db,
        user_id=user["id"],
        action="USER_LOGIN",
        details={"username": user["username"]},
    )
    await db.commit()

    logger.info("User '%s' (role=%s) logged in.", user["username"], user["role"])

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=sec.jwt_access_token_ttl,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh an expired access token",
)
async def refresh_token(
    body: RefreshRequest,
    db: DB,
    sec: SecurityManager = Depends(get_security),
) -> TokenResponse:
    """
    Exchange a valid refresh token for a new access token and rotated refresh token.
    Implements token rotation and family-based theft detection.
    """
    try:
        claims = sec.verify_refresh_token(body.refresh_token)
    except SecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from exc

    # Demo user shortcut — no DB access (refresh token claims only have "sub")
    if claims.get("sub") == DEMO_USER_ID:
        access_token = sec.create_access_token(
            user_id=DEMO_USER_ID,
            username=DEMO_USERNAME,
            role="admin",
        )
        new_refresh_token, _ = sec.create_refresh_token(user_id=DEMO_USER_ID)
        logger.info("Demo user refresh token rotated (no DB).")
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_in=sec.jwt_access_token_ttl,
        )

    user_id = claims["sub"]
    token_hash = sec.hash_refresh_token(body.refresh_token)

    # Look up token in DB
    async with db.execute(
        "SELECT id, user_id, family_id, revoked, expires_at FROM refresh_tokens WHERE token_hash = ?",
        (token_hash,),
    ) as cursor:
        db_token = await cursor.fetchone()

    if db_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Theft detection
    if db_token["revoked"]:
        # Token has been reused! Revoke all tokens in family
        now = time.time()
        await db.execute(
            "UPDATE refresh_tokens SET revoked = 1, revoked_at = ? WHERE family_id = ?",
            (now, db_token["family_id"]),
        )
        await log_action(
            db,
            user_id=user_id,
            action="REFRESH_THEFT_DETECTED",
            details={"family_id": db_token["family_id"], "attempted_token_hash": token_hash},
        )
        await db.commit()
        logger.warning(
            "⚠️ Refresh token reuse detected! Revoking all tokens in family %s.",
            db_token["family_id"],
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token reuse detected",
        )

    if time.time() > db_token["expires_at"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    # Fetch user
    async with db.execute(
        "SELECT id, username, role, is_active FROM users WHERE id = ?",
        (user_id,),
    ) as cursor:
        user = await cursor.fetchone()

    if user is None or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    # Mark old token as revoked
    now = time.time()
    await db.execute(
        "UPDATE refresh_tokens SET revoked = 1, revoked_at = ? WHERE id = ?",
        (now, db_token["id"]),
    )

    # Create new tokens (using same family_id)
    access_token = sec.create_access_token(
        user_id=user["id"],
        username=user["username"],
        role=user["role"],
    )
    new_refresh_token, _ = sec.create_refresh_token(user_id=user["id"], family_id=db_token["family_id"])

    # Store new refresh token in DB
    new_token_id = str(uuid.uuid4())
    new_token_hash = sec.hash_refresh_token(new_refresh_token)
    expires_at = now + sec.jwt_refresh_token_ttl

    await db.execute(
        """
        INSERT INTO refresh_tokens (id, user_id, token_hash, family_id, issued_at, expires_at, revoked)
        VALUES (?, ?, ?, ?, ?, ?, 0)
        """,
        (new_token_id, user["id"], new_token_hash, db_token["family_id"], now, expires_at),
    )
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=sec.jwt_access_token_ttl,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Invalidate refresh token and log out",
)
async def logout(
    body: RefreshRequest,
    db: DB,
    sec: SecurityManager = Depends(get_security),
):
    """Log out by revoking the provided refresh token."""
    token_hash = sec.hash_refresh_token(body.refresh_token)

    try:
        claims = sec.verify_refresh_token(body.refresh_token)
        user_id = claims["sub"]
    except Exception:
        user_id = "unknown"

    now = time.time()
    await db.execute(
        "UPDATE refresh_tokens SET revoked = 1, revoked_at = ? WHERE token_hash = ?",
        (now, token_hash),
    )

    await log_action(
        db,
        user_id=user_id,
        action="USER_LOGOUT",
        details={"token_hash_prefix": token_hash[:8]},
    )
    await db.commit()


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change user password and reset must_change_password flag",
)
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser,
    db: DB,
    sec: SecurityManager = Depends(get_security),
):
    """Change the password for the current authenticated user and reset their must_change_password flag."""
    # Block demo user
    if is_demo(current_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password change not allowed in demo mode",
        )

    user_id = current_user["sub"]

    # Fetch user password hash
    async with db.execute(
        "SELECT password_hash, username FROM users WHERE id = ?",
        (user_id,),
    ) as cursor:
        user = await cursor.fetchone()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Verify old password
    if not sec.verify_password(body.old_password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid old password",
        )

    # Hash new password and update user
    new_hash = sec.hash_password(body.new_password)
    await db.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = ? WHERE id = ?",
        (new_hash, time.time(), user_id),
    )

    # Revoke all refresh tokens for this user
    await db.execute(
        "UPDATE refresh_tokens SET revoked = 1, revoked_at = ? WHERE user_id = ?",
        (time.time(), user_id),
    )

    # Log action in audit trail
    await log_action(
        db,
        user_id=user_id,
        action="USER_CHANGE_PASSWORD",
        details={"username": user["username"]},
    )
    await db.commit()
    logger.info("User '%s' changed their password. All refresh tokens revoked.", user["username"])


@router.get(
    "/me",
    response_model=UserProfile,
    summary="Get the current authenticated user's profile",
)
async def get_me(current_user: CurrentUser) -> UserProfile:
    """Return the profile of the currently authenticated user."""
    return UserProfile(
        user_id=current_user["sub"],
        username=current_user["username"],
        role=current_user["role"],
    )
