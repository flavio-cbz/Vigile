import json
import pytest
import unittest.mock as mock
from pydantic import BaseModel
from master.core.llm_client import LLMClient
from master.core.structured_llm import StructuredLLM


class TestModel(BaseModel):
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
    client.complete = mock.AsyncMock(return_value={
        "choices": [{"message": {"content": raw}}],
    })
    result = await sllm.create(TestModel, [{"role": "user", "content": "Extract"}])
    assert isinstance(result, TestModel)
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
    result = await sllm.create(TestModel, [{"role": "user", "content": "Extract"}])
    assert isinstance(result, TestModel)
    assert calls == 2
    assert result.name == "Jane"


@pytest.mark.asyncio
async def test_structured_fail_after_retries(structured_llm):
    """StructuredLLM raises ValueError after exhausting retries."""
    sllm, client = structured_llm
    client.complete = mock.AsyncMock(return_value={
        "choices": [{"message": {"content": "still not json"}}],
    })
    with pytest.raises(ValueError) as exc_info:
        await sllm.create(TestModel, [{"role": "user", "content": "Extract"}], max_retries=2)
    assert "failed after" in str(exc_info.value)


@pytest.mark.asyncio
async def test_structured_empty_response(structured_llm):
    """StructuredLLM handles empty LLM response."""
    sllm, client = structured_llm
    client.complete = mock.AsyncMock(return_value={
        "choices": [{"message": {"content": ""}}],
    })
    with pytest.raises(ValueError) as exc_info:
        await sllm.create(TestModel, [{"role": "user", "content": "Extract"}], max_retries=1)
    assert "empty" in str(exc_info.value).lower()
