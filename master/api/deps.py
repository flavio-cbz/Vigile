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
from fastapi import Depends

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


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    sec: Annotated[SecurityManager, Depends(get_security)],
) -> dict[str, Any]:
    """
    Dependency: Extracts and verifies the JWT from Authorization header.
    Returns the full claims dict. Raises HTTP 401 on failure.
    """
    from fastapi import HTTPException, status
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return sec.verify_access_token(credentials.credentials)


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
# Type aliases for cleaner router signatures
# ---------------------------------------------------------------------------

CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
DB = Annotated[aiosqlite.Connection, Depends(get_db)]
