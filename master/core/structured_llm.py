"""
Vigile — Structured LLM

Forces an LLM to return structured JSON output validated against a Pydantic model.
Inspired by Instructor, implemented natively (zero dependencies).

Pattern:
  1. Generate JSON schema from the Pydantic model
  2. Build a system prompt with the schema
  3. Call LLMClient.complete()
  4. Validate the response with model_validate_json()
  5. On failure: retry up to max_retries, showing the error to the LLM
"""

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel

from master.core.llm_client import LLMClient

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class StructuredLLM:
    """
    Wraps an LLMClient to produce structured outputs.

    Usage:
        llm = LLMClient(...)
        sllm = StructuredLLM(llm)

        class MyModel(BaseModel):
            name: str
            age: int

        result = await sllm.create(MyModel, [
            {"role": "user", "content": "Extract: John is 30"}
        ])
        # result.name == "John", result.age == 30
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._client = llm_client

    async def create(
        self,
        response_model: type[T],
        messages: list[dict[str, Any]],
        max_retries: int = 3,
        **kwargs: Any,
    ) -> T:
        """
        Request a structured response from the LLM.

        Args:
            response_model: Pydantic model to validate against.
            messages: Chat messages (will have system prompt prepended).
            max_retries: Number of attempts before giving up.
            **kwargs: Additional kwargs passed to LLMClient.complete().

        Returns:
            An instance of response_model.

        Raises:
            ValueError: If the LLM fails to produce valid output after all retries.
            LLMError: If the LLM provider returns an error.
        """
        schema = response_model.model_json_schema()
        from master.core.prompts import load_prompt

        system_prompt = load_prompt("structured_output", schema=json.dumps(schema, indent=2))

        full_messages = [{"role": "system", "content": system_prompt}, *messages]

        for attempt in range(max_retries):
            response = await self._client.complete(
                full_messages,
                **{k: v for k, v in kwargs.items() if k != "stream"},
            )

            raw = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not raw:
                if attempt == max_retries - 1:
                    raise ValueError(f"LLM returned empty content after {max_retries} attempts")
                full_messages.append(
                    {
                        "role": "assistant",
                        "content": "(empty response)",
                    }
                )
                full_messages.append(
                    {
                        "role": "user",
                        "content": "You returned empty content. Output valid JSON only.",
                    }
                )
                continue

            try:
                # Strip <think> reasoning blocks (Nemotron, DeepSeek, etc.)
                # before JSON validation to avoid parse failures
                cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
                return response_model.model_validate_json(cleaned)
            except Exception as exc:
                logger.warning(
                    "StructuredLLM attempt %d/%d failed: %s",
                    attempt + 1,
                    max_retries,
                    exc,
                )
                if attempt == max_retries - 1:
                    raise ValueError(
                        f"Structured output failed after {max_retries} attempts. "
                        f"Last error: {exc}"
                    ) from exc
                full_messages.append({"role": "assistant", "content": raw})
                full_messages.append(
                    {
                        "role": "user",
                        "content": f"Validation error: {exc}. Fix the JSON to match the schema exactly.",
                    }
                )

        raise ValueError("Unexpected: loop completed without return or raise")
