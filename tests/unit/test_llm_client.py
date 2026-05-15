#!/usr/bin/env python3
"""
Vigile — LLM Client Unit Tests
Tests LLMClient.complete(), stream(), and error handling.
"""
import asyncio
import json
import os
import sys

import pathlib
PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent.parent)
sys.path.insert(0, PROJECT_ROOT)

# Mock httpx before any imports that use it
PASS = "\033[92m\u2713\033[0m"
FAIL = "\033[91m\u2717\033[0m"
results = []

def check(name, condition, detail=""):
    icon = PASS if condition else FAIL
    print(f"  {icon} {name}" + (f" ({detail})" if detail else ""))
    results.append((name, condition))
    return condition

from master.core.llm_client import LLMClient, LLMError


class _MockStreamResponse:
    """Simulates a streaming httpx response for the stream method."""
    def __init__(self, lines, status=200):
        self.status_code = status
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line


async def test_complete_success():
    """LLMClient.complete() — mock httpx.AsyncClient.post."""
    import unittest.mock as mock
    mock_resp = mock.AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: {"choices": [{"message": {"content": "Hello world"}}]}

    with mock.patch("httpx.AsyncClient") as MockClient:
        inst = mock.AsyncMock()
        MockClient.return_value = inst
        inst.__aenter__.return_value = inst
        inst.post.return_value = mock_resp

        client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
        result = await client.complete([{"role": "user", "content": "Hi"}])
        check("complete: returns choices", "choices" in result)
        check("complete: has content",
              result["choices"][0]["message"]["content"] == "Hello world")


async def test_complete_timeout():
    """LLMClient.complete() raises LLMError on timeout."""
    import unittest.mock as mock
    with mock.patch("httpx.AsyncClient") as MockClient:
        inst = mock.AsyncMock()
        MockClient.return_value = inst
        inst.__aenter__.return_value = inst
        inst.post.side_effect = __import__("httpx").TimeoutException("timeout")

        client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
        try:
            await client.complete([{"role": "user", "content": "Hi"}])
            check("complete timeout: no exception raised", False)
        except LLMError as e:
            check("complete timeout: raises LLMError", "timed out" in str(e).lower())


async def test_complete_http_error():
    """LLMClient.complete() raises LLMError on HTTP 4xx/5xx."""
    import unittest.mock as mock
    mock_resp = mock.AsyncMock()
    mock_resp.status_code = 401
    mock_resp.text = json.dumps({"error": "unauthorized"})

    with mock.patch("httpx.AsyncClient") as MockClient:
        inst = mock.AsyncMock()
        MockClient.return_value = inst
        inst.__aenter__.return_value = inst
        inst.post.return_value = mock_resp

        client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
        try:
            await client.complete([{"role": "user", "content": "Hi"}])
            check("complete 401: no exception raised", False)
        except LLMError as e:
            check("complete 401: raises LLMError", "401" in str(e))


async def test_stream_tokens():
    """LLMClient.stream() yields tokens."""
    chunks = [
        f"data: {json.dumps({'choices': [{'delta': {'content': 'Hello'}}]})}",
        f"data: {json.dumps({'choices': [{'delta': {'content': ' world'}}]})}",
        "data: [DONE]",
    ]
    import unittest.mock as mock

    with mock.patch("httpx.AsyncClient") as MockClient:
        inst = mock.AsyncMock()
        MockClient.return_value = inst
        inst.__aenter__.return_value = inst
        inst.send.return_value = _MockStreamResponse(chunks, 200)

        client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
        tokens = []
        async for event in client.stream([{"role": "user", "content": "Hi"}]):
            tokens.append(event)
        check("stream: yields tokens", len(tokens) >= 2)
        if len(tokens) >= 2:
            check("stream: first token content",
                  tokens[0]["type"] == "token" and tokens[0]["content"] == "Hello")


async def test_stream_done():
    """LLMClient.stream() yields done event."""
    import unittest.mock as mock
    with mock.patch("httpx.AsyncClient") as MockClient:
        inst = mock.AsyncMock()
        MockClient.return_value = inst
        inst.__aenter__.return_value = inst
        inst.send.return_value = _MockStreamResponse(["data: [DONE]"], 200)

        client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
        events = []
        async for event in client.stream([{"role": "user", "content": "Hi"}]):
            events.append(event)
        check("stream: done event", any(e["type"] == "done" for e in events))


async def test_stream_http_error():
    """LLMClient.stream() yields error event on HTTP error."""
    import unittest.mock as mock
    with mock.patch("httpx.AsyncClient") as MockClient:
        inst = mock.AsyncMock()
        MockClient.return_value = inst
        inst.__aenter__.return_value = inst
        inst.send.return_value = _MockStreamResponse([], 500)

        client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
        events = []
        async for event in client.stream([{"role": "user", "content": "Hi"}]):
            events.append(event)
        check("stream: error on HTTP 500",
              any(e["type"] == "error" and "500" in e.get("detail", "") for e in events))


print("\n\U0001f916 LLMClient Tests")
asyncio.run(test_complete_success())
asyncio.run(test_complete_timeout())
asyncio.run(test_complete_http_error())
asyncio.run(test_stream_tokens())
asyncio.run(test_stream_done())
asyncio.run(test_stream_http_error())

print("\n" + "=" * 60)
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
total = len(results)
print(f"Results: {passed}/{total} passed", end="")
if failed:
    print(f"  ({failed} FAILED)")
    for name, ok in results:
        if not ok:
            print(f"  {FAIL} {name}")
    sys.exit(1)
else:
    print(" \U0001f389")
