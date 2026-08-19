import pytest
from unittest.mock import AsyncMock, MagicMock
import json

from master.core.chat_engine import ChatEngine
from master.core.tools import ToolExecutor


@pytest.mark.asyncio
async def test_chat_engine_simple_round():
    # Mock LLMClient
    mock_llm = MagicMock()
    
    async def mock_stream(*args, **kwargs):
        yield {"type": "token", "content": "Hello"}
        yield {"type": "done"}
    
    mock_llm.stream = mock_stream

    # Mock NodeManager and DB
    mock_nm = MagicMock()
    mock_nm.get_node = AsyncMock(return_value=None)
    mock_db = AsyncMock()

    engine = ChatEngine(mock_llm, mock_nm, mock_db, "user-1")

    history = []
    events = []
    async for event in engine.run(history, "node-1"):
        events.append(event)

    assert len(events) == 1
    assert events[0] == {"type": "token", "content": "Hello"}
    assert len(history) == 1
    assert history[0] == {"role": "assistant", "content": "Hello"}


@pytest.mark.asyncio
async def test_tool_executor_fleet_overview():
    mock_nm = MagicMock()
    mock_db = AsyncMock()

    # Mock list_nodes
    mock_nm.list_nodes = AsyncMock(return_value=[
        {
            "id": "node-1",
            "name": "prod-1",
            "hostname": "prod-1.local",
            "state": "CONNECTED",
            "online": True,
            "os": "Linux",
            "arch": "amd64",
        }
    ])

    result = await ToolExecutor.execute(
        "get_fleet_overview", {}, mock_nm, mock_db, "user-1"
    )

    assert result["success"] is True
    assert len(result["data"]) == 1
    assert result["data"][0]["name"] == "prod-1"
