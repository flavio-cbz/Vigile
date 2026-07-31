from __future__ import annotations

"""
Vigile — LLM Retry with Exponential Backoff

Native retry helper (no tenacity dependency) for LLMClient operations.
Retries on transient failures only: timeouts, connection errors, HTTP 429,
and HTTP 5xx. Does NOT retry on HTTP 4xx (client/config errors).

Usage:
    from master.core.llm_retry import with_retry
    result = await with_retry(my_llm_call, max_attempts=3, base_delay=1.0)
"""

import asyncio
import logging
import random
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def with_retry(
    fn: Callable[..., Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    jitter: float = 0.3,
) -> T:
    """Execute *fn* with exponential backoff retry on transient LLM failures.

    Retries on: LLMTimeoutError, LLMConnectionError, LLMRateLimitError, LLMServerError.
    Does NOT retry on: LLMClientError (HTTP 4xx except 429) — config/prompt errors.

    Args:
        fn: Async callable to execute.
        max_attempts: Maximum number of attempts (including the first).
        base_delay: Base delay in seconds for exponential backoff.
        jitter: Maximum random jitter in seconds added to each delay.

    Returns:
        Result of *fn* on success.

    Raises:
        Last exception if all attempts fail.
    """
    # Lazy import to avoid circular dependency (llm_client imports this module)
    from master.core.llm_client import (
        LLMConnectionError,
        LLMRateLimitError,
        LLMServerError,
        LLMTimeoutError,
    )

    _RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
        LLMTimeoutError,
        LLMConnectionError,
        LLMRateLimitError,
        LLMServerError,
    )

    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await fn()
        except _RETRYABLE_ERRORS as exc:
            last_exc = exc
            if attempt == max_attempts - 1:
                logger.warning(
                    "LLM request failed after %d attempts: %s", max_attempts, exc
                )
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, jitter)
            logger.info(
                "LLM request attempt %d/%d failed (%s), retrying in %.2fs",
                attempt + 1,
                max_attempts,
                type(exc).__name__,
                delay,
            )
            await asyncio.sleep(delay)

    # Should never reach here, but satisfy type checkers
    if last_exc:
        raise last_exc
    raise RuntimeError("with_retry: unreachable code reached")
