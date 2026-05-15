"""
Vigile — Authentication API

Endpoints:
  POST /api/auth/login    → username + password → access_token + refresh_token
  POST /api/auth/refresh  → refresh_token → new access_token
  GET  /api/auth/me       → current user profile (requires valid JWT)
"""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from master.api.deps import CurrentUser, DB, get_security
from master.config import settings
from master.core.security_manager import SecurityManager
from master.core.rate_limiter import rate_limiter

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
    refresh_token = sec.create_refresh_token(user_id=user["id"])

    # Update last_login
    await db.execute(
        "UPDATE users SET last_login = ? WHERE id = ?",
        (time.time(), user["id"]),
    )
    await db.commit()

    logger.info("User '%s' (role=%s) logged in.", user["username"], user["role"])

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_ttl,
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
    Exchange a valid refresh token for a new access token.
    The refresh token itself is NOT rotated in Sprint 1.
    (Refresh token rotation is a Sprint 5 hardening task.)
    """
    claims = sec.verify_refresh_token(body.refresh_token)
    user_id = claims["sub"]

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

    access_token = sec.create_access_token(
        user_id=user["id"],
        username=user["username"],
        role=user["role"],
    )
    # Issue a fresh refresh token (simple rotation)
    new_refresh_token = sec.create_refresh_token(user_id=user["id"])

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.jwt_access_token_ttl,
    )


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
