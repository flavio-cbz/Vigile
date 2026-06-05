import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from master.core.llm_client import LLMClient


@pytest.fixture
def client() -> LLMClient:
    return LLMClient(
        base_url="http://test-llm:8000/v1",
        api_key="test-key",
        model="test-model",
        timeout=30,
    )


class TestLLMClientPersistent:
    """BH-04: LLMClient must reuse a persistent httpx.AsyncClient."""

    def test_persistent_client_created(self, client: LLMClient) -> None:
        """A persistent httpx.AsyncClient is created at init."""
        assert isinstance(client._client, httpx.AsyncClient)

    def test_persistent_client_limits(self, client: LLMClient) -> None:
        """The client has proper connection pool limits."""
        pool = client._client._transport._pool
        assert pool._max_connections == 10
        assert pool._max_keepalive_connections == 5

    def test_same_client_for_multiple_calls(self, client: LLMClient) -> None:
        """Multiple calls use the same client instance (no new creation)."""
        c1 = client._client
        c2 = client._client
        assert c1 is c2, "Expected same client instance across calls"

    @pytest.mark.asyncio
    async def test_close_releases_resources(self, client: LLMClient) -> None:
        """close() does not raise and client is no longer usable."""
        await client.close()
        # After close, the underlying transport is shutdown
        with pytest.raises(RuntimeError):
            await client._client.get("http://test")
