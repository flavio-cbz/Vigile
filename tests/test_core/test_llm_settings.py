"""
Vigile — Unit tests for LLM settings overrides
"""

import pytest
from master.config import Settings


def test_settings_apply_overrides() -> None:
    """Test applying overrides to LLM settings directly in memory."""
    settings = Settings(
        llm_base_url="http://original-base",
        llm_api_key="original-key",
        llm_model="original-model"
    )

    settings.apply_overrides(
        base_url="http://new-base",
        api_key="new-key",
        model="new-model"
    )

    assert settings.llm_base_url == "http://new-base"
    assert settings.llm_api_key == "new-key"
    assert settings.llm_model == "new-model"


def test_settings_apply_overrides_masked_key() -> None:
    """Test that applying overrides with a masked API key does not overwrite the existing key."""
    settings = Settings(
        llm_base_url="http://original-base",
        llm_api_key="original-key",
        llm_model="original-model"
    )

    settings.apply_overrides(
        base_url="http://new-base",
        api_key="••••••••",
        model="new-model"
    )

    assert settings.llm_base_url == "http://new-base"
    assert settings.llm_api_key == "original-key"  # remains unchanged
    assert settings.llm_model == "new-model"
