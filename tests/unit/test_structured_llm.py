#!/usr/bin/env python3
"""
Vigile — StructuredLLM Unit Tests
Tests structured output generation with retry logic.
"""
import asyncio
import json
import os
import sys
import unittest.mock as mock

import pathlib
PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent.parent)
sys.path.insert(0, PROJECT_ROOT)

PASS = "\033[92m\u2713\033[0m"
FAIL = "\033[91m\u2717\033[0m"
results = []

def check(name, condition, detail=""):
    icon = PASS if condition else FAIL
    print(f"  {icon} {name}" + (f" ({detail})" if detail else ""))
    results.append((name, condition))
    return condition

from pydantic import BaseModel
from master.core.llm_client import LLMClient, LLMError
from master.core.structured_llm import StructuredLLM


class TestModel(BaseModel):
    name: str
    age: int


client = LLMClient(base_url="http://test/v1", api_key="k", model="m", timeout=5)
sllm = StructuredLLM(client)


async def test_structured_success():
    """StructuredLLM returns validated model on first attempt."""
    raw = json.dumps({"name": "John", "age": 30})
    client.complete = mock.AsyncMock(return_value={
        "choices": [{"message": {"content": raw}}],
    })
    result = await sllm.create(TestModel, [{"role": "user", "content": "Extract"}])
    check("structured: returns TestModel", isinstance(result, TestModel))
    check("structured: name matches", result.name == "John")
    check("structured: age matches", result.age == 30)


async def test_structured_retry():
    """StructuredLLM retries on invalid JSON."""
    calls = 0
    async def mock_complete(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"choices": [{"message": {"content": "not json"}}]}
        return {"choices": [{"message": {"content": json.dumps({"name": "Jane", "age": 25})}}]}
    client.complete = mock_complete
    result = await sllm.create(TestModel, [{"role": "user", "content": "Extract"}])
    check("structured retry: returns model", isinstance(result, TestModel))
    check("structured retry: used 2 attempts", calls == 2)
    check("structured retry: name matches", result.name == "Jane")


async def test_structured_fail_after_retries():
    """StructuredLLM raises ValueError after exhausting retries."""
    client.complete = mock.AsyncMock(return_value={
        "choices": [{"message": {"content": "still not json"}}],
    })
    try:
        await sllm.create(TestModel, [{"role": "user", "content": "Extract"}], max_retries=2)
        check("structured fail: no exception", False)
    except ValueError as e:
        check("structured fail: raises ValueError", "failed after" in str(e))


async def test_structured_empty_response():
    """StructuredLLM handles empty LLM response."""
    client.complete = mock.AsyncMock(return_value={
        "choices": [{"message": {"content": ""}}],
    })
    try:
        await sllm.create(TestModel, [{"role": "user", "content": "Extract"}], max_retries=1)
        check("structured empty: no exception", False)
    except ValueError as e:
        check("structured empty: raises ValueError", "empty" in str(e).lower())


print("\n\U0001f9e0 StructuredLLM Tests")
asyncio.run(test_structured_success())
asyncio.run(test_structured_retry())
asyncio.run(test_structured_fail_after_retries())
asyncio.run(test_structured_empty_response())

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
