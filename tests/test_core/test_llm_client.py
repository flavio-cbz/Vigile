from __future__ import annotations

import json
import unittest.mock as mock

import httpx
import pytest

from master.core.llm_client import (
    LLMClient,
    LLMClientError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    LLMServerError,
    LLMTimeoutError,
)


class _MockStreamResponse:
    """Simulates a streaming httpx response for the stream method."""

    def __init__(self, lines, status=200):
        self.status_code = status
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line


def _make_client(**kwargs) -> LLMClient:
    """Create an LLMClient with a separate httpx client for testing."""
    timeout = kwargs.get("timeout", 5)
    client = LLMClient(
        base_url=kwargs.get("base_url", "http://test/v1"),
        api_key=kwargs.get("api_key", "k"),
        model=kwargs.get("model", "m"),
        timeout=timeout,
        client=httpx.AsyncClient(timeout=timeout),
        max_retries=kwargs.get("max_retries", 1),
        retry_base_delay=kwargs.get("retry_base_delay", 1.0),
        retry_jitter=kwargs.get("retry_jitter", 0.3),
    )
    return client


def _mock_stream(client: LLMClient, mock_resp) -> mock.AsyncMock:
    """Replace client._client.stream with a mock returning an async context manager."""
    ctx_mock = mock.AsyncMock()
    ctx_mock.__aenter__.return_value = mock_resp
    # Use MagicMock (not AsyncMock) so calling stream() sync-returns ctx_mock
    client._client.stream = mock.MagicMock(return_value=ctx_mock)
    return ctx_mock


# -----------------------------------------------------------------------
# complete() tests
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_success():
    """LLMClient.complete() — mock httpx.AsyncClient.post."""
    mock_resp = mock.AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: {"choices": [{"message": {"content": "Hello world"}}]}

    client = _make_client()
    client._client.post = mock.AsyncMock(return_value=mock_resp)

    result = await client.complete([{"role": "user", "content": "Hi"}])
    assert "choices" in result
    assert result["choices"][0]["message"]["content"] == "Hello world"


@pytest.mark.asyncio
async def test_complete_timeout():
    """LLMClient.complete() raises LLMError on timeout."""
    client = _make_client()
    client._client.post = mock.AsyncMock(
        side_effect=__import__("httpx").TimeoutException("timeout")
    )

    with pytest.raises(LLMError) as exc_info:
        await client.complete([{"role": "user", "content": "Hi"}])
    assert "expiré" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_complete_http_error():
    """LLMClient.complete() raises LLMError on HTTP 4xx/5xx."""
    mock_resp = mock.AsyncMock()
    mock_resp.status_code = 401
    mock_resp.text = json.dumps({"error": "unauthorized"})

    client = _make_client()
    client._client.post = mock.AsyncMock(return_value=mock_resp)

    with pytest.raises(LLMError) as exc_info:
        await client.complete([{"role": "user", "content": "Hi"}])
    assert "401" in str(exc_info.value)


@pytest.mark.asyncio
async def test_complete_connect_error():
    """LLMClient.complete() raises LLMError on connection failure."""
    client = _make_client()
    client._client.post = mock.AsyncMock(
        side_effect=__import__("httpx").ConnectError("connection refused")
    )

    with pytest.raises(LLMError) as exc_info:
        await client.complete([{"role": "user", "content": "Hi"}])
    assert "connexion" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_complete_text_access_exception():
    """LLMClient.complete() handles exception when accessing response text."""
    mock_resp = mock.AsyncMock()
    mock_resp.status_code = 400
    type(mock_resp).text = property(mock.Mock(side_effect=ValueError("Access error")))

    client = _make_client()
    client._client.post = mock.AsyncMock(return_value=mock_resp)

    with pytest.raises(LLMError) as exc_info:
        await client.complete([{"role": "user", "content": "Hi"}])
    assert "HTTP 400" in str(exc_info.value)


# -----------------------------------------------------------------------
# stream() tests
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_tokens():
    """LLMClient.stream() yields tokens."""
    chunks = [
        f"data: {json.dumps({'choices': [{'delta': {'content': 'Hello'}}]})}",
        f"data: {json.dumps({'choices': [{'delta': {'content': ' world'}}]})}",
        "data: [DONE]",
    ]
    mock_resp = _MockStreamResponse(chunks, 200)
    client = _make_client()
    _mock_stream(client, mock_resp)

    tokens = []
    async for event in client.stream([{"role": "user", "content": "Hi"}]):
        tokens.append(event)
    assert len(tokens) >= 2
    assert tokens[0]["type"] == "token"
    assert tokens[0]["content"] == "Hello"


@pytest.mark.asyncio
async def test_stream_done():
    """LLMClient.stream() yields done event."""
    mock_resp = _MockStreamResponse(["data: [DONE]"], 200)
    client = _make_client()
    _mock_stream(client, mock_resp)

    events = []
    async for event in client.stream([{"role": "user", "content": "Hi"}]):
        events.append(event)
    assert any(e["type"] == "done" for e in events)


@pytest.mark.asyncio
async def test_stream_http_error():
    """LLMClient.stream() yields error event on HTTP error."""
    mock_resp = _MockStreamResponse([], 500)
    client = _make_client()
    _mock_stream(client, mock_resp)

    events = []
    async for event in client.stream([{"role": "user", "content": "Hi"}]):
        events.append(event)
    assert any(e["type"] == "error" and "500" in e.get("detail", "") for e in events)


@pytest.mark.asyncio
async def test_stream_timeout_and_connect_errors():
    """LLMClient.stream() handles TimeoutException and ConnectError."""
    client = _make_client()

    # Timeout error
    client._client.stream = mock.MagicMock(
        side_effect=__import__("httpx").TimeoutException("timed out")
    )
    events = []
    async for event in client.stream([{"role": "user", "content": "Hi"}]):
        events.append(event)
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "répondre" in events[0]["detail"].lower()

    # Connect error
    client._client.stream = mock.MagicMock(
        side_effect=__import__("httpx").ConnectError("failed to connect")
    )
    events_conn = []
    async for event in client.stream([{"role": "user", "content": "Hi"}]):
        events_conn.append(event)
    assert len(events_conn) == 1
    assert events_conn[0]["type"] == "error"
    assert "connexion" in events_conn[0]["detail"].lower()


@pytest.mark.asyncio
async def test_stream_text_access_exception():
    """LLMClient.stream() handles exception when accessing response text on error."""
    mock_resp = mock.AsyncMock()
    mock_resp.status_code = 500
    type(mock_resp).text = property(mock.Mock(side_effect=ValueError("Access error")))

    client = _make_client()
    _mock_stream(client, mock_resp)

    events = []
    async for event in client.stream([{"role": "user", "content": "Hi"}]):
        events.append(event)
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "HTTP 500" in events[0]["detail"]


@pytest.mark.asyncio
async def test_stream_various_lines_and_tool_calls():
    """LLMClient.stream() parses non-data lines, decode errors, empty choices, and tool calls."""
    chunks = [
        "not a data line",
        "data: invalid_json{",
        "data: " + json.dumps({"choices": []}),
        "data: "
        + json.dumps({"choices": [{"delta": {"tool_calls": [{"id": "tc1", "type": "function"}]}}]}),
    ]
    mock_resp = _MockStreamResponse(chunks, 200)
    client = _make_client()
    _mock_stream(client, mock_resp)

    events = []
    async for event in client.stream([{"role": "user", "content": "Hi"}]):
        events.append(event)
    assert len(events) == 1
    assert events[0]["type"] == "tool_call"
    assert events[0]["tool_calls"][0]["id"] == "tc1"


@pytest.mark.asyncio
async def test_stream_accumulates_fragmented_tool_calls():
    """LLMClient.stream() accumulates fragmented tool_calls and yields on [DONE]."""
    chunks = [
        f"data: {json.dumps({'choices': [{'delta': {'tool_calls': [{'index': 0, 'id': 'call_abc'}]}}]})}",
        f"data: {json.dumps({'choices': [{'delta': {'tool_calls': [{'index': 0, 'function': {'name': 'list_containers'}}]}}]})}",
        f"data: {json.dumps({'choices': [{'delta': {'tool_calls': [{'index': 0, 'function': {'arguments': '_containers'}}]}}]})}",
        f"data: {json.dumps({'choices': [{'delta': {'tool_calls': [{'index': 0, 'function': {'arguments': '()'}}]}}]})}",
        "data: [DONE]",
    ]
    mock_resp = _MockStreamResponse(chunks, 200)
    client = _make_client()
    _mock_stream(client, mock_resp)

    events = []
    async for event in client.stream([{"role": "user", "content": "Hi"}]):
        events.append(event)

    tool_call_events = [e for e in events if e["type"] == "tool_call"]
    assert len(tool_call_events) == 1
    tc = tool_call_events[0]["tool_calls"][0]
    assert tc["id"] == "call_abc"
    assert tc["function"]["name"] == "list_containers"
    assert tc["function"]["arguments"] == "_containers()"
    assert any(e["type"] == "done" for e in events)


@pytest.mark.asyncio
async def test_stream_accumulates_multiple_tool_calls():
    """LLMClient.stream() accumulates multiple tool_calls across indices."""
    chunks = [
        f"data: {json.dumps({'choices': [{'delta': {'tool_calls': [{'index': 0, 'id': 'call_a'}]}}]})}",
        f"data: {json.dumps({'choices': [{'delta': {'tool_calls': [{'index': 1, 'id': 'call_b'}]}}]})}",
        f"data: {json.dumps({'choices': [{'delta': {'tool_calls': [{'index': 0, 'function': {'name': 'list_containers'}}]}}]})}",
        f"data: {json.dumps({'choices': [{'delta': {'tool_calls': [{'index': 1, 'function': {'name': 'read_logs'}}]}}]})}",
        f"data: {json.dumps({'choices': [{'delta': {'tool_calls': [{'index': 0, 'function': {'arguments': '_containers'}}]}}]})}",
        "data: " + json.dumps({'choices': [{'delta': {'tool_calls': [{'index': 1, 'function': {'arguments': '("/var/log/syslog")'}}]}}]}),
        "data: [DONE]",
    ]
    mock_resp = _MockStreamResponse(chunks, 200)
    client = _make_client()
    _mock_stream(client, mock_resp)

    events = []
    async for event in client.stream([{"role": "user", "content": "Hi"}]):
        events.append(event)

    tool_call_events = [e for e in events if e["type"] == "tool_call"]
    assert len(tool_call_events) == 1
    tcs = tool_call_events[0]["tool_calls"]
    assert len(tcs) == 2
    assert tcs[0]["id"] == "call_a"
    assert tcs[0]["function"]["name"] == "list_containers"
    assert tcs[0]["function"]["arguments"] == "_containers"
    assert tcs[1]["id"] == "call_b"
    assert tcs[1]["function"]["name"] == "read_logs"
    assert tcs[1]["function"]["arguments"] == '("/var/log/syslog")'


@pytest.mark.asyncio
async def test_complete_retries_on_timeout():
    """LLMClient.complete() retries on timeout with exponential backoff."""
    mock_resp = mock.AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: {"choices": [{"message": {"content": "Hello"}}]}

    client = _make_client(max_retries=3, retry_base_delay=0, retry_jitter=0)
    client._client.post = mock.AsyncMock(
        side_effect=[
            httpx.TimeoutException("timeout"),
            httpx.TimeoutException("timeout"),
            mock_resp,
        ]
    )

    result = await client.complete([{"role": "user", "content": "Hi"}])
    assert "choices" in result
    assert result["choices"][0]["message"]["content"] == "Hello"


@pytest.mark.asyncio
async def test_complete_does_not_retry_on_client_error():
    """LLMClient.complete() does NOT retry on HTTP 4xx (except 429)."""
    mock_resp = mock.AsyncMock()
    mock_resp.status_code = 400
    mock_resp.text = json.dumps({"error": "bad request"})

    client = _make_client(max_retries=3, retry_base_delay=0, retry_jitter=0)
    client._client.post = mock.AsyncMock(return_value=mock_resp)

    with pytest.raises(LLMClientError) as exc_info:
        await client.complete([{"role": "user", "content": "Hi"}])
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_complete_retries_on_rate_limit():
    """LLMClient.complete() retries on HTTP 429."""
    mock_resp = mock.AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: {"choices": [{"message": {"content": "OK"}}]}

    rate_limit_resp = mock.AsyncMock()
    rate_limit_resp.status_code = 429
    rate_limit_resp.text = "Too Many Requests"
    rate_limit_resp.headers = {}

    client = _make_client(max_retries=3, retry_base_delay=0, retry_jitter=0)
    client._client.post = mock.AsyncMock(
        side_effect=[rate_limit_resp, mock_resp]
    )

    result = await client.complete([{"role": "user", "content": "Hi"}])
    assert result["choices"][0]["message"]["content"] == "OK"


@pytest.mark.asyncio
async def test_complete_retries_on_server_error():
    """LLMClient.complete() retries on HTTP 5xx."""
    mock_resp = mock.AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: {"choices": [{"message": {"content": "OK"}}]}

    server_error_resp = mock.AsyncMock()
    server_error_resp.status_code = 503
    server_error_resp.text = "Service Unavailable"

    client = _make_client(max_retries=3, retry_base_delay=0, retry_jitter=0)
    client._client.post = mock.AsyncMock(
        side_effect=[server_error_resp, mock_resp]
    )

    result = await client.complete([{"role": "user", "content": "Hi"}])
    assert result["choices"][0]["message"]["content"] == "OK"


@pytest.mark.asyncio
async def test_complete_circuit_breaker_opens():
    """LLMClient.complete() opens circuit breaker after 3 consecutive failures."""
    client = _make_client(max_retries=1)
    client._client.post = mock.AsyncMock(
        side_effect=httpx.ConnectError("connection refused")
    )

    for _ in range(3):
        with pytest.raises(LLMConnectionError):
            await client.complete([{"role": "user", "content": "Hi"}])

    with pytest.raises(LLMError) as exc_info:
        await client.complete([{"role": "user", "content": "Hi"}])
    assert "circuit" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_stream_circuit_breaker_blocks_when_open():
    """LLMClient.stream() yields error event when circuit breaker is open."""
    client = _make_client(max_retries=1)
    client._client.post = mock.AsyncMock(
        side_effect=httpx.ConnectError("connection refused")
    )

    for _ in range(3):
        with pytest.raises(LLMConnectionError):
            await client.complete([{"role": "user", "content": "Hi"}])

    mock_resp = _MockStreamResponse(["data: [DONE]"], 200)
    _mock_stream(client, mock_resp)

    events = []
    async for event in client.stream([{"role": "user", "content": "Hi"}]):
        events.append(event)

    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "circuit" in events[0]["detail"].lower()


def test_get_health_status():
    """LLMClient.get_health_status() returns circuit breaker state and error count."""
    client = _make_client()
    status = client.get_health_status()
    assert status["circuit_state"] == "CLOSED"
    assert status["circuit_failures"] == 0
    assert status["last_success"] is None
    assert status["error_count_5min"] == 0
