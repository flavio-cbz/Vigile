"""
Vigile — Shared FastAPI Dependencies

Provides reusable dependency-injected objects:
  - get_db()           : active aiosqlite connection
  - get_security()     : SecurityManager singleton
  - get_node_manager() : NodeManager singleton
  - CurrentUser        : type alias for the authenticated user's claims dict
"""

from typing import Annotated, Any

import aiosqlite
from fastapi import Depends, Request

from master.db.database import get_db_conn
from master.core.security_manager import SecurityManager, get_security_instance, bearer_scheme
from master.core.node_manager import NodeManager, node_manager
from fastapi.security import HTTPAuthorizationCredentials


# ---------------------------------------------------------------------------
# Database dependency
# ---------------------------------------------------------------------------


async def get_db() -> aiosqlite.Connection:
    """
    Yield the active aiosqlite connection.
    FastAPI will call this for every request that declares it as a dependency.
    The connection is managed by the lifespan (opened at startup, closed at shutdown).
    """
    return get_db_conn()


# ---------------------------------------------------------------------------
# Singleton dependencies
# ---------------------------------------------------------------------------


def get_security() -> SecurityManager:
    """Return the SecurityManager singleton (must be initialized first)."""
    return get_security_instance()


def get_node_manager() -> NodeManager:
    """Return the module-level NodeManager singleton."""
    return node_manager


# ---------------------------------------------------------------------------
# Auth dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    sec: Annotated[SecurityManager, Depends(get_security)],
    db: Annotated[aiosqlite.Connection, Depends(get_db)],
) -> dict[str, Any]:
    """
    Dependency: Extracts and verifies the JWT from Authorization header.
    Also checks if the user is required to change their password.
    Returns the full claims dict. Raises HTTP 401 on authentication failure,
    HTTP 403 (MUST_CHANGE_PASSWORD) if password change is required.
    """
    from fastapi import HTTPException, status
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = sec.verify_access_token(credentials.credentials)
    user_id = claims["sub"]

    # Check must_change_password in DB
    async with db.execute(
        "SELECT must_change_password FROM users WHERE id = ?",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()

    if row is not None and row["must_change_password"]:
        path = request.url.path.rstrip("/")
        if path not in ["/api/auth/change-password", "/api/auth/logout", "/api/auth/login"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "detail": "Password change required",
                    "code": "MUST_CHANGE_PASSWORD"
                }
            )

    return claims


def require_role(*roles: str):
    """
    Dependency factory: Require one of the specified roles.
    SecurityManager is resolved lazily at request time (not at import time).

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(claims=Depends(require_role("admin"))):
            ...
    """
    def _dependency(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
        ],
    ) -> dict[str, Any]:
        return get_security_instance().require_role(*roles)(credentials)
    return _dependency


# ---------------------------------------------------------------------------
# LLM Dependencies (lazy — initialized on first call)
# ---------------------------------------------------------------------------

_llm_client: "LLMClient | None" = None
_structured_llm: "StructuredLLM | None" = None


def get_llm_client() -> "LLMClient":
    """Return the LLMClient singleton, initializing it on first call."""
    global _llm_client
    if _llm_client is None:
        from master.config import settings
        from master.core.llm_client import LLMClient
        if not settings.llm_base_url:
            raise RuntimeError(
                "LLM not configured. Set LLM_BASE_URL environment variable."
            )
        _llm_client = LLMClient(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )
    return _llm_client


def get_structured_llm() -> "StructuredLLM":
    """Return the StructuredLLM singleton, initializing it on first call."""
    global _structured_llm
    if _structured_llm is None:
        from master.core.structured_llm import StructuredLLM
        _structured_llm = StructuredLLM(llm_client=get_llm_client())
    return _structured_llm


# ---------------------------------------------------------------------------
# Type aliases for cleaner router signatures
# ---------------------------------------------------------------------------

CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
DB = Annotated[aiosqlite.Connection, Depends(get_db)]
