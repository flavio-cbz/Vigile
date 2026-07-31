from __future__ import annotations

import json
import unittest.mock as mock

import pytest
from pydantic import BaseModel

from master.core.llm_client import LLMClient
from master.core.structured_llm import StructuredLLM


class ResponseSchemaModel(BaseModel):
    name: str
    age: int


@pytest.fixture
def structured_llm():
    client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
    return StructuredLLM(client), client


@pytest.mark.asyncio
async def test_structured_success(structured_llm):
    """StructuredLLM returns validated model on first attempt."""
    sllm, client = structured_llm
    raw = json.dumps({"name": "John", "age": 30})
    client.complete = mock.AsyncMock(
        return_value={
            "choices": [{"message": {"content": raw}}],
        }
    )
    result = await sllm.create(ResponseSchemaModel, [{"role": "user", "content": "Extract"}])
    assert isinstance(result, ResponseSchemaModel)
    assert result.name == "John"
    assert result.age == 30


@pytest.mark.asyncio
async def test_structured_retry(structured_llm):
    """StructuredLLM retries on invalid JSON."""
    sllm, client = structured_llm
    calls = 0

    async def mock_complete(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"choices": [{"message": {"content": "not json"}}]}
        return {"choices": [{"message": {"content": json.dumps({"name": "Jane", "age": 25})}}]}

    client.complete = mock_complete
    result = await sllm.create(ResponseSchemaModel, [{"role": "user", "content": "Extract"}])
    assert isinstance(result, ResponseSchemaModel)
    assert calls == 2
    assert result.name == "Jane"


@pytest.mark.asyncio
async def test_structured_fail_after_retries(structured_llm):
    """StructuredLLM raises ValueError after exhausting retries."""
    sllm, client = structured_llm
    client.complete = mock.AsyncMock(
        return_value={
            "choices": [{"message": {"content": "still not json"}}],
        }
    )
    with pytest.raises(ValueError) as exc_info:
        await sllm.create(
            ResponseSchemaModel, [{"role": "user", "content": "Extract"}], max_retries=2
        )
    assert "failed after" in str(exc_info.value)


@pytest.mark.asyncio
async def test_structured_empty_response(structured_llm):
    """StructuredLLM handles empty LLM response."""
    sllm, client = structured_llm
    client.complete = mock.AsyncMock(
        return_value={
            "choices": [{"message": {"content": ""}}],
        }
    )
    with pytest.raises(ValueError) as exc_info:
        await sllm.create(
            ResponseSchemaModel, [{"role": "user", "content": "Extract"}], max_retries=1
        )
    assert "empty" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_structured_empty_response_retry(structured_llm):
    """StructuredLLM retries on empty response and succeeds on next try."""
    sllm, client = structured_llm
    calls = 0

    async def mock_complete(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"choices": [{"message": {"content": ""}}]}
        return {"choices": [{"message": {"content": json.dumps({"name": "Jack", "age": 40})}}]}

    client.complete = mock_complete
    result = await sllm.create(
        ResponseSchemaModel, [{"role": "user", "content": "Extract"}], max_retries=3
    )
    assert isinstance(result, ResponseSchemaModel)
    assert calls == 2
    assert result.name == "Jack"


@pytest.mark.asyncio
async def test_structured_max_retries_zero(structured_llm):
    """StructuredLLM handles max_retries=0 and hits the loop fallthrough."""
    sllm, client = structured_llm
    with pytest.raises(ValueError) as exc_info:
        await sllm.create(
            ResponseSchemaModel, [{"role": "user", "content": "Extract"}], max_retries=0
        )
    assert "loop completed without return or raise" in str(exc_info.value)


@pytest.mark.asyncio
async def test_default_max_retries():
    """StructuredLLM uses default_max_retries when create() omits max_retries."""
    client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
    sllm = StructuredLLM(client, default_max_retries=2)

    calls = 0

    async def always_invalid(*args, **kwargs):
        nonlocal calls
        calls += 1
        return {"choices": [{"message": {"content": "not valid json"}}]}

    client.complete = always_invalid
    with pytest.raises(ValueError) as exc_info:
        await sllm.create(ResponseSchemaModel, [{"role": "user", "content": "Extract"}])
    assert calls == 2
    assert "failed after" in str(exc_info.value)
