"""
Registry Service - Agent discovery and health monitoring.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AgentRegistration(BaseModel):
    """Agent registration entry"""

    agent_id: str
    agent_name: str
    agent_type: str
    tenant_id: str
    status: str
    capabilities: List[str]
    endpoint: str
    registered_at: datetime
    last_heartbeat: datetime
    metadata: Dict[str, Any]


class ServiceRegistry:
    """
    Service Registry for agent discovery and health monitoring.
    """

    def __init__(self, heartbeat_timeout: int = 30):
        """
        Initialize service registry.

        Args:
            heartbeat_timeout: Seconds before marking agent as unhealthy
        """
        self.registry: Dict[str, AgentRegistration] = {}
        self.heartbeat_timeout = heartbeat_timeout

    async def register_agent(
        self,
        agent_id: str,
        agent_name: str,
        agent_type: str,
        tenant_id: str,
        capabilities: List[str],
        endpoint: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentRegistration:
        """
        Register an agent.

        Args:
            agent_id: Unique agent ID
            agent_name: Human-readable agent name
            agent_type: Type of agent
            tenant_id: Tenant ID
            capabilities: List of capabilities
            endpoint: Agent endpoint
            metadata: Additional metadata

        Returns:
            Registration entry
        """
        registration = AgentRegistration(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_type=agent_type,
            tenant_id=tenant_id,
            status="healthy",
            capabilities=capabilities,
            endpoint=endpoint,
            registered_at=datetime.utcnow(),
            last_heartbeat=datetime.utcnow(),
            metadata=metadata or {},
        )

        self.registry[agent_id] = registration
        logger.info(
            f"Agent registered: {agent_name}",
            extra={
                "agent_id": agent_id,
                "agent_type": agent_type,
                "tenant_id": tenant_id,
            },
        )

        return registration

    async def deregister_agent(self, agent_id: str) -> bool:
        """
        Deregister an agent.

        Args:
            agent_id: Agent ID to deregister

        Returns:
            True if successful
        """
        if agent_id in self.registry:
            del self.registry[agent_id]
            logger.info(f"Agent deregistered: {agent_id}")
            return True
        return False

    async def heartbeat(self, agent_id: str) -> bool:
        """
        Record heartbeat from an agent.

        Args:
            agent_id: Agent ID

        Returns:
            True if successful
        """
        if agent_id not in self.registry:
            return False

        self.registry[agent_id].last_heartbeat = datetime.utcnow()
        self.registry[agent_id].status = "healthy"
        return True

    async def get_agent(self, agent_id: str) -> Optional[AgentRegistration]:
        """
        Get agent registration.

        Args:
            agent_id: Agent ID

        Returns:
            Registration entry or None
        """
        return self.registry.get(agent_id)

    async def discover_agents(
        self,
        agent_type: Optional[str] = None,
        tenant_id: Optional[str] = None,
        capability: Optional[str] = None,
    ) -> List[AgentRegistration]:
        """
        Discover agents by type, tenant, or capability.

        Args:
            agent_type: Filter by agent type
            tenant_id: Filter by tenant
            capability: Filter by capability

        Returns:
            List of matching agents
        """
        results = []
        for registration in self.registry.values():
            if registration.status != "healthy":
                continue

            if agent_type and registration.agent_type != agent_type:
                continue

            if tenant_id and registration.tenant_id != tenant_id:
                continue

            if capability and capability not in registration.capabilities:
                continue

            results.append(registration)

        logger.info(
            f"Agent discovery: found {len(results)} agents",
            extra={
                "agent_type": agent_type,
                "tenant_id": tenant_id,
                "capability": capability,
            },
        )

        return results

    async def health_check(self) -> Dict[str, Any]:
        """
        Check health of all registered agents.

        Returns:
            Health status report
        """
        now = datetime.utcnow()
        healthy = 0
        unhealthy = 0
        timeout = timedelta(seconds=self.heartbeat_timeout)

        for agent_id, registration in self.registry.items():
            if now - registration.last_heartbeat > timeout:
                registration.status = "unhealthy"
                unhealthy += 1
                logger.warning(
                    f"Agent marked unhealthy: {registration.agent_name}",
                    extra={"agent_id": agent_id},
                )
            else:
                healthy += 1

        return {
            "total_agents": len(self.registry),
            "healthy": healthy,
            "unhealthy": unhealthy,
            "timestamp": now.isoformat(),
            "agents": [
                {
                    "id": reg.agent_id,
                    "name": reg.agent_name,
                    "status": reg.status,
                    "last_heartbeat": reg.last_heartbeat.isoformat(),
                }
                for reg in self.registry.values()
            ],
        }

    def get_all_agents(self) -> List[AgentRegistration]:
        """Get all registered agents"""
        return list(self.registry.values())
