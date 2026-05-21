import json
import pytest
import unittest.mock as mock
from master.core.llm_client import LLMClient, LLMError


class _MockStreamResponse:
    """Simulates a streaming httpx response for the stream method."""
    def __init__(self, lines, status=200):
        self.status_code = status
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line


@pytest.mark.asyncio
async def test_complete_success():
    """LLMClient.complete() — mock httpx.AsyncClient.post."""
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
        assert "choices" in result
        assert result["choices"][0]["message"]["content"] == "Hello world"


@pytest.mark.asyncio
async def test_complete_timeout():
    """LLMClient.complete() raises LLMError on timeout."""
    with mock.patch("httpx.AsyncClient") as MockClient:
        inst = mock.AsyncMock()
        MockClient.return_value = inst
        inst.__aenter__.return_value = inst
        inst.post.side_effect = __import__("httpx").TimeoutException("timeout")

        client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
        with pytest.raises(LLMError) as exc_info:
            await client.complete([{"role": "user", "content": "Hi"}])
        assert "timed out" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_complete_http_error():
    """LLMClient.complete() raises LLMError on HTTP 4xx/5xx."""
    mock_resp = mock.AsyncMock()
    mock_resp.status_code = 401
    mock_resp.text = json.dumps({"error": "unauthorized"})

    with mock.patch("httpx.AsyncClient") as MockClient:
        inst = mock.AsyncMock()
        MockClient.return_value = inst
        inst.__aenter__.return_value = inst
        inst.post.return_value = mock_resp

        client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
        with pytest.raises(LLMError) as exc_info:
            await client.complete([{"role": "user", "content": "Hi"}])
        assert "401" in str(exc_info.value)


@pytest.mark.asyncio
async def test_stream_tokens():
    """LLMClient.stream() yields tokens."""
    chunks = [
        f"data: {json.dumps({'choices': [{'delta': {'content': 'Hello'}}]})}",
        f"data: {json.dumps({'choices': [{'delta': {'content': ' world'}}]})}",
        "data: [DONE]",
    ]

    with mock.patch("httpx.AsyncClient") as MockClient:
        inst = mock.AsyncMock()
        MockClient.return_value = inst
        inst.__aenter__.return_value = inst
        inst.send.return_value = _MockStreamResponse(chunks, 200)

        client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
        tokens = []
        async for event in client.stream([{"role": "user", "content": "Hi"}]):
            tokens.append(event)
        assert len(tokens) >= 2
        assert tokens[0]["type"] == "token"
        assert tokens[0]["content"] == "Hello"


@pytest.mark.asyncio
async def test_stream_done():
    """LLMClient.stream() yields done event."""
    with mock.patch("httpx.AsyncClient") as MockClient:
        inst = mock.AsyncMock()
        MockClient.return_value = inst
        inst.__aenter__.return_value = inst
        inst.send.return_value = _MockStreamResponse(["data: [DONE]"], 200)

        client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
        events = []
        async for event in client.stream([{"role": "user", "content": "Hi"}]):
            events.append(event)
        assert any(e["type"] == "done" for e in events)


@pytest.mark.asyncio
async def test_stream_http_error():
    """LLMClient.stream() yields error event on HTTP error."""
    with mock.patch("httpx.AsyncClient") as MockClient:
        inst = mock.AsyncMock()
        MockClient.return_value = inst
        inst.__aenter__.return_value = inst
        inst.send.return_value = _MockStreamResponse([], 500)

        client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
        events = []
        async for event in client.stream([{"role": "user", "content": "Hi"}]):
            events.append(event)
        assert any(e["type"] == "error" and "500" in e.get("detail", "") for e in events)
