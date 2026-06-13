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
            raise LLMError(f"LLM request timed out after {self.timeout}s") from exc
        except httpx.ConnectError as exc:
            raise LLMError(f"LLM connection failed: {exc}") from exc

        if resp.status_code >= 400:
            detail = f"LLM returned HTTP {resp.status_code}"
            try:
                detail += f": {resp.text[:200]}"
            except Exception:
                pass
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
                    detail = f"LLM returned HTTP {resp.status_code}"
                    try:
                        detail += f": {resp.text[:200]}"
                    except Exception:
                        pass
                    yield {"type": "error", "detail": detail}
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
        except httpx.TimeoutException:
            yield {"type": "error", "detail": "LLM stream timed out"}
            return
        except httpx.ConnectError as exc:
            yield {"type": "error", "detail": f"LLM connection failed: {exc}"}
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
