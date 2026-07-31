from __future__ import annotations

"""
Vigile — LLM Client

Native OpenAI-compatible HTTP client using httpx.
Zero dependencies beyond the project whitelist.

Supports:
  - complete()     : full response (non-streaming)
  - stream()       : SSE streaming with token-by-token yield
  - Tool calling   : parses tool_calls from OpenAI-format responses
  - Any provider   : OpenAI, NVIDIA NIM, Ollama, OpenRouter, vLLM, etc.

Usage:
    client = LLMClient(base_url="...", api_key="...", model="...")
    reply = await client.complete([{"role": "user", "content": "Hello"}])
    async for token in client.stream([{"role": "user", "content": "Hi"}]):
        print(token)
"""

import json
import logging
import time
from collections import deque
from typing import Any, AsyncIterator

import httpx

from master.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from master.core.llm_http_pool import get_shared_client
from master.core.llm_retry import with_retry
from master.core.secret_loader import load_secret

DEFAULT_TIMEOUT: float = 30.0

logger = logging.getLogger(__name__)


# User-facing error messages (French, no raw exception leakage).
# Internal operators still get the raw exception via WARNING logs below.
LLM_ERROR_MESSAGES = {
    "request_timeout": (
        "La requête au service IA a expiré après {timeout} secondes. "
        "Réessayez ou réduisez la complexité de votre demande."
    ),
    "stream_timeout": (
        "Le service IA a mis trop de temps à répondre. "
        "Réessayez ou réduisez la complexité de votre demande."
    ),
    "connection_failed": (
        "Connexion au service IA impossible. "
        "Vérifiez la configuration LLM dans Paramètres → Configuration Master."
    ),
    "http_error": (
        "Le service IA a renvoyé une erreur (HTTP {status_code}). "
        "Contactez l'administrateur si le problème persiste."
    ),
    "circuit_open": (
        "Le service IA est temporairement indisponible (circuit ouvert). "
        "Réessayez dans quelques secondes."
    ),
}


class LLMError(Exception):
    """Base exception for all LLM client errors."""
    pass


class LLMTimeoutError(LLMError):
    """Raised on request timeout — retryable."""
    pass


class LLMConnectionError(LLMError):
    """Raised on connection failure — retryable."""
    pass


class LLMRateLimitError(LLMError):
    """Raised on HTTP 429 — retryable."""
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMServerError(LLMError):
    """Raised on HTTP 5xx — retryable."""
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMClientError(LLMError):
    """Raised on HTTP 4xx (except 429) — NOT retryable."""
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


#: Exception types that are safe to retry (transient failures).
_RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    LLMTimeoutError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMServerError,
)


class LLMClient:
    """
    OpenAI-compatible LLM client.

    The constructor takes all configuration explicitly (no settings coupling).
    Works with any provider exposing an OpenAI-compatible /v1/chat/completions.

    Includes:
      - Native retry with exponential backoff (transient failures only)
      - Circuit breaker for fail-fast on persistent failures
      - Shared httpx connection pool (singleton)
      - Tool-call delta reassembly in streaming mode
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        model: str = "nvidia/nemotron-3-ultra-550b-a55b",
        timeout: float | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        client: httpx.AsyncClient | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        retry_jitter: float = 0.3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or load_secret("LLM_API_KEY")
        self.model = model
        self.timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._retry_jitter = retry_jitter
        # Use shared singleton client unless a custom one is injected (e.g. tests)
        self._client: httpx.AsyncClient = client if client is not None else get_shared_client(timeout=self.timeout)
        self._cb = CircuitBreaker(
            name=f"llm:{model}",
            failure_threshold=3,
            timeout=120.0,
        )
        # Health tracking
        self._last_success_time: float = 0.0
        self._error_timestamps: deque[float] = deque()

    async def complete(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Send a chat completion request and return the full response.

        Returns the response JSON dict (OpenAI format).
        Raises LLMError (or subclass) on failure.

        Retry policy:
          - Retries on: Timeout, ConnectionError, HTTP 429, HTTP 5xx
          - Does NOT retry on: HTTP 4xx (except 429) — config/prompt errors

        Circuit breaker:
          - Opens after 3 consecutive failures
          - Stays open for 120s before transitioning to HALF_OPEN
        """
        body = self._build_body(messages, stream=False, **kwargs)
        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()

        async def _do_request() -> dict[str, Any]:
            try:
                resp = await self._client.post(url, headers=headers, json=body, timeout=self.timeout)
            except httpx.TimeoutException as exc:
                logger.warning("LLM request timed out after %ss: %s", self.timeout, exc)
                raise LLMTimeoutError(
                    LLM_ERROR_MESSAGES["request_timeout"].format(timeout=self.timeout)
                ) from exc
            except httpx.ConnectError as exc:
                logger.warning("LLM connection failed: %s", exc)
                raise LLMConnectionError(LLM_ERROR_MESSAGES["connection_failed"]) from exc

            if resp.status_code == 429:
                retry_after: float | None = None
                try:
                    retry_after = float(resp.headers.get("retry-after", ""))
                except (TypeError, ValueError):
                    pass
                logger.warning("LLM rate limited (429)")
                raise LLMRateLimitError(
                    LLM_ERROR_MESSAGES["http_error"].format(status_code=429),
                    retry_after=retry_after,
                )
            elif resp.status_code >= 500:
                try:
                    error_text = resp.text[:200]
                except Exception:
                    error_text = "<unreadable response>"
                logger.warning("LLM returned HTTP %s: %s", resp.status_code, error_text)
                raise LLMServerError(
                    LLM_ERROR_MESSAGES["http_error"].format(status_code=resp.status_code),
                    status_code=resp.status_code,
                )
            elif resp.status_code >= 400:
                try:
                    error_text = resp.text[:200]
                except Exception:
                    error_text = "<unreadable response>"
                logger.warning("LLM returned HTTP %s: %s", resp.status_code, error_text)
                raise LLMClientError(
                    LLM_ERROR_MESSAGES["http_error"].format(status_code=resp.status_code),
                    status_code=resp.status_code,
                )

            self._last_success_time = time.monotonic()
            return resp.json()

        # Check circuit breaker before attempting
        try:
            await self._cb.check()
        except CircuitBreakerOpenError as exc:
            logger.warning("LLM circuit breaker is open: %s", exc)
            self._record_error()
            raise LLMError(LLM_ERROR_MESSAGES["circuit_open"]) from exc

        # Execute with retry — circuit breaker records failures for retryable errors
        try:
            result = await with_retry(
                _do_request,
                max_attempts=self._max_retries,
                base_delay=self._retry_base_delay,
                jitter=self._retry_jitter,
            )
            await self._cb.record_success()
            return result
        except _RETRYABLE_ERRORS:
            await self._cb.record_failure()
            self._record_error()
            raise
        except LLMClientError:
            # Don't trip circuit breaker for client errors (4xx)
            self._record_error()
            raise

    async def stream(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream a chat completion via SSE.

        Yields dicts with keys:
          - "type": "token" | "tool_call" | "done" | "error"
          - "content": str (for token type)
          - "tool_calls": [...] (for tool_call type)
          - "detail": str (for error type)

        Tool calls are accumulated across streaming deltas and yielded
        as a complete list when the stream ends ([DONE] or natural end).
        This prevents consumers from receiving fragmented tool_call data.
        """
        body = self._build_body(messages, stream=True, **kwargs)
        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()

        _tc_accumulator: dict[int, dict] = {}

        # Check circuit breaker before starting stream
        try:
            await self._cb.check()
        except CircuitBreakerOpenError as exc:
            logger.warning("LLM circuit breaker is open: %s", exc)
            self._record_error()
            yield {"type": "error", "detail": LLM_ERROR_MESSAGES["circuit_open"]}
            return

        try:
            async with self._client.stream(
                "POST",
                url,
                headers=headers,
                json=body,
                timeout=httpx.Timeout(self.timeout, read=120),
            ) as resp:
                if resp.status_code >= 400:
                    try:
                        error_text = resp.text[:200]
                    except Exception:
                        error_text = "<unreadable response>"
                    logger.warning("LLM returned HTTP %s: %s", resp.status_code, error_text)
                    await self._cb.record_failure()
                    self._record_error()
                    yield {
                        "type": "error",
                        "detail": LLM_ERROR_MESSAGES["http_error"].format(
                            status_code=resp.status_code
                        ),
                    }
                    return

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]

                    if payload.strip() == "[DONE]":
                        # Yield accumulated tool_calls before done
                        if _tc_accumulator:
                            yield {"type": "tool_call", "tool_calls": list(_tc_accumulator.values())}
                            _tc_accumulator.clear()
                        yield {"type": "done"}
                        await self._cb.record_success()
                        self._last_success_time = time.monotonic()
                        return

                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})

                    content = delta.get("content")
                    if content:
                        yield {"type": "token", "content": content}

                    tool_calls = delta.get("tool_calls")
                    if tool_calls:
                        for tc_delta in tool_calls:
                            idx = tc_delta.get("index", 0)
                            if idx not in _tc_accumulator:
                                _tc_accumulator[idx] = {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                }
                            acc = _tc_accumulator[idx]
                            if "id" in tc_delta:
                                acc["id"] += tc_delta["id"]
                            if "type" in tc_delta:
                                acc["type"] = tc_delta["type"]
                            if "function" in tc_delta:
                                fn = tc_delta["function"]
                                if "name" in fn:
                                    acc["function"]["name"] += fn["name"]
                                if "arguments" in fn:
                                    acc["function"]["arguments"] += fn["arguments"]

                # Stream ended without [DONE] — yield any remaining accumulated tool_calls
                if _tc_accumulator:
                    yield {"type": "tool_call", "tool_calls": list(_tc_accumulator.values())}
                    _tc_accumulator.clear()
                await self._cb.record_success()
                self._last_success_time = time.monotonic()

        except httpx.TimeoutException as exc:
            logger.warning("LLM stream timed out: %s", exc)
            await self._cb.record_failure()
            self._record_error()
            yield {"type": "error", "detail": LLM_ERROR_MESSAGES["stream_timeout"]}
            return
        except httpx.ConnectError as exc:
            logger.warning("LLM connection failed: %s", exc)
            await self._cb.record_failure()
            self._record_error()
            yield {"type": "error", "detail": LLM_ERROR_MESSAGES["connection_failed"]}
            return

    async def close(self) -> None:
        """Close the HTTP client.

        For shared clients, this closes the pool — subsequent get_shared_client()
        calls will create a fresh one. For injected clients (tests), only that
        instance is closed.
        """
        await self._client.aclose()

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _build_body(
        self,
        messages: list[dict[str, Any]],
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }
        body.update(kwargs)
        return body

    # ------------------------------------------------------------------
    # Health monitoring
    # ------------------------------------------------------------------

    def _record_error(self) -> None:
        """Record an error timestamp for health monitoring (5-min sliding window)."""
        now = time.monotonic()
        self._error_timestamps.append(now)
        # Prune errors older than 5 minutes
        cutoff = now - 300
        while self._error_timestamps and self._error_timestamps[0] < cutoff:
            self._error_timestamps.popleft()

    def get_health_status(self) -> dict[str, Any]:
        """Return LLM health status for the /health endpoint.

        Returns:
            Dict with circuit breaker state, failure count, last success time,
            and error count over a 5-minute sliding window.
        """
        return {
            "circuit_state": self._cb.state.value,
            "circuit_failures": self._cb.failure_count,
            "last_success": self._last_success_time if self._last_success_time else None,
            "error_count_5min": len(self._error_timestamps),
        }
