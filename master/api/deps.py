"""
Vigile — Shared FastAPI Dependencies

Provides reusable dependency-injected objects:
  - get_db()           : active aiosqlite connection
  - get_security()     : SecurityManager singleton
  - get_node_manager() : NodeManager singleton
  - CurrentUser        : type alias for the authenticated user's claims dict
"""

import threading
from typing import TYPE_CHECKING, Annotated, Any, AsyncGenerator

import aiosqlite
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from master.core.node_manager import NodeManager, node_manager
from master.core.security_manager import (
    ROLES_HIERARCHY,
    ExpiredTokenError,
    SecurityError,
    SecurityManager,
    get_security_instance,
)
from master.db.database import database_session

if TYPE_CHECKING:
    from master.core.llm_client import LLMClient
    from master.core.structured_llm import StructuredLLM

bearer_scheme = HTTPBearer(auto_error=False)
ACCESS_TOKEN_COOKIE = "vigile_access_token"


# ---------------------------------------------------------------------------
# Database dependency
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    Yield the active aiosqlite connection from the pool.
    FastAPI will call this for every request that declares it as a dependency.
    """
    async with database_session() as conn:
        yield conn


# ---------------------------------------------------------------------------
# Singleton dependencies
# ---------------------------------------------------------------------------


def get_security() -> SecurityManager:
    """Return the SecurityManager singleton (must be initialized first)."""
    return get_security_instance()


def get_node_manager() -> NodeManager:
    return node_manager


def get_bus() -> Any:
    """Return the EventBus singleton."""
    from master.core.event_bus import get_event_bus

    return get_event_bus()


def get_settings() -> Any:
    """Return the settings singleton (lazy import to prevent module-level coupling)."""
    import master.config

    return master.config.settings


# ---------------------------------------------------------------------------
# Auth dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    sec: Annotated[SecurityManager, Depends(get_security)],
    db: Annotated[aiosqlite.Connection, Depends(get_db)],
) -> dict[str, Any]:
    """
    Dependency: Extracts and verifies the JWT from Authorization header.
    Also checks if the user is required to change their password.
    Returns the full claims dict. Raises HTTP 401 on authentication failure,
    HTTP 403 (MUST_CHANGE_PASSWORD) if password change is required.
    """
    token = (
        credentials.credentials
        if credentials is not None
        else request.cookies.get(ACCESS_TOKEN_COOKIE)
    )
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = sec.verify_access_token(token)
    except ExpiredTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except SecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if sec.audit_compromised:
        user_role = claims.get("role", "viewer")
        is_operator = user_role in ("operator", "admin")
        is_write = request.method in ("POST", "PUT", "DELETE", "PATCH")
        if is_operator or is_write:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="System Locked: Security Compromised",
            )

    user_id = claims["sub"]

    # Bypass DB check for volatile demo user
    if user_id == "demo-user" or claims.get("username") == "guest":
        row: dict[str, int] | aiosqlite.Row | None = {"is_active": 1, "must_change_password": 0}
    else:
        # Check active state and must_change_password in DB
        async with db.execute(
            "SELECT is_active, must_change_password FROM users WHERE id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None or not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    if row["must_change_password"]:
        path = request.url.path.rstrip("/")
        if path not in ["/api/auth/change-password", "/api/auth/logout", "/api/auth/login"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"detail": "Password change required", "code": "MUST_CHANGE_PASSWORD"},
            )

    return claims


def require_role(*roles: str) -> Any:
    """
    Dependency factory: Require one of the specified roles.
    SecurityManager is resolved lazily at request time (not at import time).

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(claims=Depends(require_role("admin"))):
            ...
    """

    async def _dependency(
        current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    ) -> dict[str, Any]:
        user_role = current_user.get("role", "viewer")

        # Check if the user's role satisfies ANY of the required roles
        user_level = ROLES_HIERARCHY.get(user_role, 0)
        required_level = min(ROLES_HIERARCHY.get(r, 99) for r in roles)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {roles}",
            )
        return current_user

    return _dependency


_init_lock = threading.RLock()
_llm_client: "LLMClient | None" = None  # noqa: F821
_structured_llm: "StructuredLLM | None" = None  # noqa: F821
_insights_manager: Any = None


def get_llm_client() -> "LLMClient":  # noqa: F821
    global _llm_client
    with _init_lock:
        if _llm_client is None:
            import master.config
            from master.core.llm_client import LLMClient

            settings = master.config.settings
            if not settings.llm_base_url:
                raise RuntimeError("LLM not configured. Set LLM_BASE_URL environment variable.")
            _llm_client = LLMClient(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                timeout=settings.llm_timeout,
                max_tokens=settings.llm_max_tokens,
                temperature=settings.llm_temperature,
            )
        return _llm_client


def get_structured_llm() -> "StructuredLLM":  # noqa: F821
    global _structured_llm
    with _init_lock:
        if _structured_llm is None:
            from master.core.structured_llm import StructuredLLM

            _structured_llm = StructuredLLM(llm_client=get_llm_client())
        return _structured_llm


def get_insights_manager() -> Any:
    global _insights_manager
    with _init_lock:
        if _insights_manager is None:
            from master.core.insights import InsightsManager
            from master.core.plugin_manager import plugin_manager

            llm_client = None
            try:
                llm_client = get_llm_client()
            except RuntimeError:
                pass
            _insights_manager = InsightsManager(llm_client=llm_client, plugin_manager=plugin_manager)
        return _insights_manager


def reset_llm_clients() -> None:
    """Reset the LLM clients to force re-instantiation with new settings."""
    global _llm_client, _structured_llm, _insights_manager
    with _init_lock:
        _llm_client = None
        _structured_llm = None
        _insights_manager = None


def get_locale(accept_language: Annotated[str | None, Header()] = None) -> str:
    """Parse Accept-Language header to determine the client's locale ('fr' or 'en')."""
    # Always return French to keep console locale homogeneous
    return "fr"


# ---------------------------------------------------------------------------
# Type aliases for cleaner router signatures
# ---------------------------------------------------------------------------

CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
DB = Annotated[aiosqlite.Connection, Depends(get_db)]
Insights = Annotated[Any, Depends(get_insights_manager)]
