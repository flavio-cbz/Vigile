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
import unittest.mock as mock

PASS = "\033[92m\u2713\033[0m"
FAIL = "\033[91m\u2717\033[0m"
results = []

def check(name, condition, detail=""):
    icon = PASS if condition else FAIL
    print(f"  {icon} {name}" + (f" ({detail})" if detail else ""))
    results.append((name, condition))
    return condition

from master.core.llm_client import LLMClient, LLMError


def _make_mock_response(status=200, json_body=None, text=""):
    """Create a minimal mock object that behaves like httpx.Response for tests."""
    class _MockHTTPXResponse:
        def __init__(self):
            self.status_code = status
            self._json_body = json_body or {}
            self.text = text or json.dumps(json_body) if json_body else ""

        def json(self):
            return self._json_body

    return _MockHTTPXResponse()


class _MockStreamResponse:
    """Simulates a streaming httpx response for the stream method."""
    def __init__(self, lines, status=200):
        self.status_code = status
        self._lines = lines
        self.text = "\n".join(lines)

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


async def test_complete_success():
    """LLMClient.complete() returns parsed response on success."""
    body = {"choices": [{"message": {"content": "Hello world"}}]}
    mock_resp = _make_mock_response(200, body)
    original_post = LLMClient._session_post
    async def _fake_post(self, url, headers, json_body):
        return mock_resp
    LLMClient._session_post = _fake_post
    try:
        client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
        result = await client.complete([{"role": "user", "content": "Hi"}])
        check("complete: returns choices", "choices" in result)
        check("complete: has content",
              result["choices"][0]["message"]["content"] == "Hello world")
    finally:
        LLMClient._session_post = original_post


async def test_complete_timeout():
    """LLMClient.complete() raises LLMError on timeout."""
    async def _fake_timeout(self, url, headers, json_body):
        raise __import__("httpx").TimeoutException("timeout")
    client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
    original_post = LLMClient._session_post
    LLMClient._session_post = _fake_timeout
    try:
        await client.complete([{"role": "user", "content": "Hi"}])
        check("complete timeout: no exception raised", False)
    except LLMError as e:
        check("complete timeout: raises LLMError", "timed out" in str(e).lower())
    finally:
        LLMClient._session_post = original_post


async def test_complete_http_error():
    """LLMClient.complete() raises LLMError on HTTP 4xx/5xx."""
    mock_resp = _make_mock_response(401, {"error": "unauthorized"}, text='{"error": "unauthorized"}')
    async def _fake_401(self, url, headers, json_body):
        return mock_resp
    client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
    original_post = LLMClient._session_post
    LLMClient._session_post = _fake_401
    try:
        await client.complete([{"role": "user", "content": "Hi"}])
        check("complete 401: no exception raised", False)
    except LLMError as e:
        check("complete 401: raises LLMError", "401" in str(e))
    finally:
        LLMClient._session_post = original_post


async def test_stream_tokens():
    """LLMClient.stream() yields tokens."""
    chunks = [
        f"data: {json.dumps({'choices': [{'delta': {'content': 'Hello'}}]})}",
        f"data: {json.dumps({'choices': [{'delta': {'content': ' world'}}]})}",
        "data: [DONE]",
    ]

    async def _fake_stream(self, url, headers, json_body):
        return _MockStreamResponse(chunks, 200)

    client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
    original_stream = LLMClient._session_stream
    LLMClient._session_stream = _fake_stream
    try:
        tokens = []
        async for event in client.stream([{"role": "user", "content": "Hi"}]):
            tokens.append(event)
        check("stream: yields tokens", len(tokens) >= 2)
        if len(tokens) >= 2:
            check("stream: first token content",
                  tokens[0]["type"] == "token" and tokens[0]["content"] == "Hello")
    finally:
        LLMClient._session_stream = original_stream


async def test_stream_done():
    """LLMClient.stream() yields done event."""
    async def _fake_stream(self, url, headers, json_body):
        return _MockStreamResponse(["data: [DONE]"], 200)
    client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
    original_stream = LLMClient._session_stream
    LLMClient._session_stream = _fake_stream
    try:
        events = []
        async for event in client.stream([{"role": "user", "content": "Hi"}]):
            events.append(event)
        check("stream: done event", any(e["type"] == "done" for e in events))
    finally:
        LLMClient._session_stream = original_stream


async def test_stream_http_error():
    """LLMClient.stream() yields error event on HTTP error."""
    async def _fake_stream(self, url, headers, json_body):
        return _MockStreamResponse([], 500)
    client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
    original_stream = LLMClient._session_stream
    LLMClient._session_stream = _fake_stream
    try:
        events = []
        async for event in client.stream([{"role": "user", "content": "Hi"}]):
            events.append(event)
        check("stream: error on HTTP 500",
              any(e["type"] == "error" and "500" in e.get("detail", "") for e in events))
    finally:
        LLMClient._session_stream = original_stream


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
