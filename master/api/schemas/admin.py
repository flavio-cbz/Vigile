"""
Vigile — Admin Schemas
Defines request and response schemas for administrator endpoints.
"""

from pydantic import BaseModel, Field


class LLMSettingsUpdate(BaseModel):
    """Schema for updating LLM settings."""
    llm_base_url: str = Field(..., description="Base URL of the OpenAI-compatible LLM provider")
    llm_api_key: str = Field(..., description="API key (or '••••••••' to keep current key)")
    llm_model: str = Field(..., description="Model name to use for completions")


class IntentConfigUpdate(BaseModel):
    """Schema for updating default intent max age."""
    default_intent_max_age: float = Field(..., gt=0, description="Default max age in seconds for pending intents")
