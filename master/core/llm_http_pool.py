from __future__ import annotations

"""
Vigile — Shared HTTP Client Pool

Module-level singleton httpx.AsyncClient for LLMClient instances.
Prevents connection pool exhaustion when multiple LLMClient instances
are created (e.g., during settings reloads via reset_llm_clients()).

The pool is closed during application shutdown in lifespan.py.
"""

import httpx

_shared_client: httpx.AsyncClient | None = None


def get_shared_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """Return the shared httpx.AsyncClient singleton.

    Creates a new client on first call or if the existing one is closed.
    The client is configured with connection pooling suitable for
    concurrent LLM requests.

    Args:
        timeout: Default request timeout in seconds. Individual requests
            can override this with their own timeout parameter.

    Returns:
        A shared httpx.AsyncClient instance.
    """
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
            ),
        )
    return _shared_client


async def close_shared_client() -> None:
    """Close the shared httpx.AsyncClient if it exists.

    Called during application shutdown to release connection pool resources.
    """
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
    _shared_client = None
