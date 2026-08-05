from __future__ import annotations

"""
Vigile — Structured LLM

Forces an LLM to return structured JSON output validated against a Pydantic model.
Inspired by Instructor, implemented natively (zero dependencies).

Pattern:
  1. Generate JSON schema from the Pydantic model
  2. Build a system prompt with the schema
  3. Call LLMClient.complete()
  4. Validate the response with model_validate_json()
  5. On failure: retry up to max_attempts, showing the error to the LLM
"""

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel

from master.core.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Cap on the retry feedback pairs (2 messages each) appended to full_messages.
# Guards against unbounded LLM context growth when max_attempts is configured
# high: once exceeded, the OLDEST feedback pair is trimmed on every append.
MAX_RETRY_FEEDBACK_PAIRS = 5


def _append_feedback_pair(
    full_messages: list[dict[str, Any]],
    feedback_start: int,
    assistant_msg: dict[str, Any],
    user_msg: dict[str, Any],
) -> None:
    """Append one retry feedback pair, trimming the oldest pair when the
    feedback region would exceed ``2 * MAX_RETRY_FEEDBACK_PAIRS`` messages.

    The ``feedback_start`` index delimits the region of full_messages that
    holds retry feedback; trimming only ever removes the oldest pair inside
    that region, never the system prompt or the caller's messages.
    """
    full_messages.append(assistant_msg)
    full_messages.append(user_msg)
    if len(full_messages) - feedback_start > 2 * MAX_RETRY_FEEDBACK_PAIRS:
        del full_messages[feedback_start : feedback_start + 2]

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

    def __init__(self, llm_client: LLMClient, default_max_attempts: int = 2) -> None:
        self._client = llm_client
        self._default_max_attempts = default_max_attempts

    async def create(
        self,
        response_model: type[T],
        messages: list[dict[str, Any]],
        max_attempts: int | None = None,
        **kwargs: Any,
    ) -> T:
        """
        Request a structured response from the LLM.

        Args:
            response_model: Pydantic model to validate against.
            messages: Chat messages (will have system prompt prepended).
            max_attempts: Number of attempts before giving up. When ``None``
                (the default), uses the instance-level ``default_max_attempts``
                set at construction time.
            **kwargs: Additional kwargs passed to LLMClient.complete().

        Returns:
            An instance of response_model.

        Raises:
            ValueError: If the LLM fails to produce valid output after all attempts.
            LLMError: If the LLM provider returns an error.
        """
        if max_attempts is None:
            max_attempts = self._default_max_attempts
        schema = response_model.model_json_schema()
        from master.core.prompts import load_prompt

        system_prompt = load_prompt("structured_output", schema=json.dumps(schema, indent=2))

        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        feedback_start = len(full_messages)

        for attempt in range(max_attempts):
            response = await self._client.complete(
                full_messages,
                **{k: v for k, v in kwargs.items() if k != "stream"},
            )

            raw = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not raw:
                if attempt == max_attempts - 1:
                    raise ValueError(f"LLM returned empty content after {max_attempts} attempts")
                _append_feedback_pair(
                    full_messages,
                    feedback_start,
                    {
                        "role": "assistant",
                        "content": "(empty response)",
                    },
                    {
                        "role": "user",
                        "content": "You returned empty content. Output valid JSON only.",
                    },
                )
                continue

            try:
                # Strip <think> reasoning blocks (Nemotron, DeepSeek, etc.)
                # before JSON validation to avoid parse failures. Loop until no
                # complete pair remains: a single non-greedy pass leaves NESTED
                # <think> blocks behind. Unbalanced input (opener without
                # closer) matches nothing and exits the loop.
                cleaned = raw
                while re.search(r"<think>.*?</think>", cleaned, flags=re.DOTALL):
                    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL)
                cleaned = cleaned.strip()
                return response_model.model_validate_json(cleaned)
            except Exception as exc:
                logger.warning(
                    "StructuredLLM attempt %d/%d failed: %s",
                    attempt + 1,
                    max_attempts,
                    exc,
                )
                if attempt == max_attempts - 1:
                    raise ValueError(
                        f"Structured output failed after {max_attempts} attempts. "
                        f"Last error: {exc}"
                    ) from exc
                _append_feedback_pair(
                    full_messages,
                    feedback_start,
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": f"Validation error: {exc}. Fix the JSON to match the schema exactly.",
                    },
                )

        raise ValueError("Unexpected: loop completed without return or raise")
