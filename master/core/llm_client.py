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
from typing import Any, AsyncIterator

import httpx

from master.core.secret_loader import load_secret

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
}


class LLMError(Exception):
    pass


class LLMClient:
    """
    OpenAI-compatible LLM client.

    The constructor takes all configuration explicitly (no settings coupling).
    Works with any provider exposing an OpenAI-compatible /v1/chat/completions.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        model: str = "gpt-4o-mini",
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or load_secret("LLM_API_KEY")
        self.model = model
        self.timeout = timeout
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
            ),
        )

    async def complete(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Send a chat completion request and return the full response.

        Returns the response JSON dict (OpenAI format).
        Raises LLMError on HTTP errors or timeouts.
        """
        body = self._build_body(messages, stream=False, **kwargs)
        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()
        try:
            resp = await self._client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            logger.warning("LLM request timed out after %ss: %s", self.timeout, exc)
            raise LLMError(
                LLM_ERROR_MESSAGES["request_timeout"].format(timeout=self.timeout)
            ) from exc
        except httpx.ConnectError as exc:
            logger.warning("LLM connection failed: %s", exc)
            raise LLMError(LLM_ERROR_MESSAGES["connection_failed"]) from exc

        if resp.status_code >= 400:
            try:
                error_text = resp.text[:200]
            except Exception:
                error_text = "<unreadable response>"
            logger.warning("LLM returned HTTP %s: %s", resp.status_code, error_text)
            detail = LLM_ERROR_MESSAGES["http_error"].format(status_code=resp.status_code)
            raise LLMError(detail)

        return resp.json()

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
        """
        body = self._build_body(messages, stream=True, **kwargs)
        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()

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
                        yield {"type": "done"}
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
                        yield {"type": "tool_call", "tool_calls": tool_calls}
        except httpx.TimeoutException as exc:
            logger.warning("LLM stream timed out: %s", exc)
            yield {"type": "error", "detail": LLM_ERROR_MESSAGES["stream_timeout"]}
            return
        except httpx.ConnectError as exc:
            logger.warning("LLM connection failed: %s", exc)
            yield {"type": "error", "detail": LLM_ERROR_MESSAGES["connection_failed"]}
            return

    async def close(self) -> None:
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
