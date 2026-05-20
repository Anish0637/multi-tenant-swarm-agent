"""
Test registry service functionality.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from registry import ServiceRegistry


@pytest_asyncio.fixture
async def registry():
    """Create registry for testing"""
    return ServiceRegistry(heartbeat_timeout=30)


@pytest.mark.asyncio
async def test_register_agent(registry):
    """Test agent registration"""
    registration = await registry.register_agent(
        agent_id="test_agent_1",
        agent_name="Test Agent",
        agent_type="test",
        tenant_id="default",
        capabilities=["test_capability"],
        endpoint="http://localhost:8001"
    )
    
    assert registration.agent_id == "test_agent_1"
    assert registration.status == "healthy"


@pytest.mark.asyncio
async def test_discover_agents(registry):
    """Test agent discovery"""
    await registry.register_agent(
        agent_id="hr_agent",
        agent_name="HR Agent",
        agent_type="hr",
        tenant_id="hr",
        capabilities=["process_leave"],
        endpoint="http://localhost:8001"
    )
    
    # Discover by type
    agents = await registry.discover_agents(agent_type="hr")
    assert len(agents) == 1
    assert agents[0].agent_name == "HR Agent"


@pytest.mark.asyncio
async def test_heartbeat(registry):
    """Test agent heartbeat"""
    await registry.register_agent(
        agent_id="test_agent_2",
        agent_name="Test Agent 2",
        agent_type="test",
        tenant_id="default",
        capabilities=[],
        endpoint="http://localhost:8001"
    )
    
    # Send heartbeat
    result = await registry.heartbeat("test_agent_2")
    assert result is True
    
    # Check status
    agent = await registry.get_agent("test_agent_2")
    assert agent.status == "healthy"


@pytest.mark.asyncio
async def test_health_check(registry):
    """Test health check"""
    await registry.register_agent(
        agent_id="test_agent_3",
        agent_name="Test Agent 3",
        agent_type="test",
        tenant_id="default",
        capabilities=[],
        endpoint="http://localhost:8001"
    )
    
    # Health check
    health = await registry.health_check()
    assert health["total_agents"] == 1
    assert health["healthy"] == 1
    assert health["unhealthy"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
