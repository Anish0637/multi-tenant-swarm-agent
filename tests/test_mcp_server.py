"""
Test MCP server functionality.
"""

import pytest
from mcp_server import MCPServer, ToolDefinition, ToolRequest


@pytest.fixture
def mcp_server():
    """Create MCP server for testing"""
    return MCPServer(host="localhost", port=8000)


@pytest.mark.asyncio
async def test_mcp_server_initialization(mcp_server):
    """Test MCP server initialization"""
    assert mcp_server.host == "localhost"
    assert mcp_server.port == 8000
    assert len(mcp_server.tools) > 0


@pytest.mark.asyncio
async def test_mcp_list_agents(mcp_server):
    """Test list agents tool"""
    request = ToolRequest(
        tool_name="list_agents",
        tool_id="test_1",
        parameters={},
        context={}
    )
    
    handler = mcp_server.tool_handlers.get("list_agents")
    result = await handler({}, {})
    
    assert "agents" in result
    assert len(result["agents"]) > 0


@pytest.mark.asyncio
async def test_mcp_submit_task(mcp_server):
    """Test submit task tool"""
    request = ToolRequest(
        tool_name="submit_task",
        tool_id="test_2",
        parameters={
            "agent_id": "hr_agent",
            "task_type": "process_leave"
        },
        context={}
    )
    
    handler = mcp_server.tool_handlers.get("submit_task")
    result = await handler(request.parameters, request.context)
    
    assert result["status"] == "submitted"
    assert "task_id" in result


@pytest.mark.asyncio
async def test_mcp_get_agent_status(mcp_server):
    """Test get agent status tool"""
    handler = mcp_server.tool_handlers.get("get_agent_status")
    result = await handler({"agent_id": "supervisor"}, {})
    
    assert result["status"] == "healthy"
    assert result["agent_id"] == "supervisor"
    assert "tasks_processed" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
