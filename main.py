"""
Main entry point for multi-tenant swarm agent platform.
"""

import asyncio
import logging
import os
from typing import Optional

from agents import (
    SupervisorAgent,
    HRAgent,
    FinanceAgent,
    MedicalAgent,
    TaskRequest,
)
from mcp_server import MCPServer
from registry import ServiceRegistry
from access_control import (
    RBACEnforcer,
    ABACEnforcer,
    CBACEnforcer,
    RBACUser,
    Role,
    Subject,
    Resource,
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SwarmPlatform:
    """
    Multi-tenant swarm agent platform orchestrator.
    """
    
    def __init__(self):
        """Initialize the platform"""
        self.supervisor: Optional[SupervisorAgent] = None
        self.agents = {}
        self.registry = ServiceRegistry()
        self.mcp_server = MCPServer()
        self.rbac = RBACEnforcer()
        self.abac = ABACEnforcer()
        self.cbac = CBACEnforcer()
    
    async def initialize(self) -> None:
        """Initialize the platform"""
        logger.info("Initializing multi-tenant swarm agent platform...")
        
        # Create agents
        self.supervisor = SupervisorAgent()
        hr_agent = HRAgent()
        finance_agent = FinanceAgent()
        medical_agent = MedicalAgent()
        
        self.agents = {
            "supervisor": self.supervisor,
            "hr": hr_agent,
            "finance": finance_agent,
            "medical": medical_agent,
        }
        
        # Register sub-agents with supervisor
        self.supervisor.register_sub_agent(hr_agent)
        self.supervisor.register_sub_agent(finance_agent)
        self.supervisor.register_sub_agent(medical_agent)
        
        # Register agents with registry
        for name, agent in self.agents.items():
            if name != "supervisor":
                await self.registry.register_agent(
                    agent_id=agent.id,
                    agent_name=agent.name,
                    agent_type=agent.agent_type.value,
                    tenant_id=agent.tenant_id,
                    capabilities=agent.get_capabilities(),
                    endpoint=f"http://localhost:800{list(self.agents.keys()).index(name)}"
                )
        
        # Setup default RBAC users
        self._setup_default_rbac_users()
        
        # Setup default ABAC attributes
        self._setup_default_abac_attributes()
        
        logger.info("Platform initialized successfully")
    
    def _setup_default_rbac_users(self) -> None:
        """Setup default RBAC users"""
        users = [
            RBACUser(user_id="admin1", username="admin", role=Role.ADMIN, tenant_id="default"),
            RBACUser(user_id="mgr1", username="manager", role=Role.MANAGER, tenant_id="default"),
            RBACUser(user_id="user1", username="employee", role=Role.USER, tenant_id="default"),
        ]
        
        for user in users:
            self.rbac.register_user(user)
    
    def _setup_default_abac_attributes(self) -> None:
        """Setup default ABAC attributes"""
        # HR department subject
        hr_subject = Subject(
            subject_id="hr_emp1",
            attributes={"department": "HR", "clearance_level": 3}
        )
        self.abac.register_subject(hr_subject)
        
        # Finance department subject
        finance_subject = Subject(
            subject_id="fin_emp1",
            attributes={"department": "Finance", "clearance_level": 3}
        )
        self.abac.register_subject(finance_subject)
        
        # Medical department subject
        medical_subject = Subject(
            subject_id="med_emp1",
            attributes={"department": "Medical", "clearance_level": 4}
        )
        self.abac.register_subject(medical_subject)
        
        # HR resource
        hr_resource = Resource(
            resource_id="hr_res1",
            resource_type="hr",
            attributes={"sensitivity": "normal", "owner": "hr"}
        )
        self.abac.register_resource(hr_resource)
        
        # Finance resource
        finance_resource = Resource(
            resource_id="fin_res1",
            resource_type="finance",
            attributes={"sensitivity": "high", "owner": "finance"}
        )
        self.abac.register_resource(finance_resource)
        
        # Medical resource
        medical_resource = Resource(
            resource_id="med_res1",
            resource_type="medical",
            attributes={"sensitivity": "high", "owner": "medical"}
        )
        self.abac.register_resource(medical_resource)
    
    async def submit_task(
        self,
        tenant_id: str,
        task_type: str,
        payload: dict,
        user_id: str
    ) -> dict:
        """
        Submit a task to the platform.
        
        Args:
            tenant_id: Tenant ID
            task_type: Type of task
            payload: Task payload
            user_id: User submitting the task
            
        Returns:
            Task result
        """
        # Check RBAC permissions
        if not self.rbac.check_permission(user_id, "task", "execute"):
            return {"error": "Permission denied", "status": "failed"}
        
        # Create task
        task = TaskRequest(
            tenant_id=tenant_id,
            task_type=task_type,
            payload=payload,
            user_id=user_id
        )
        
        # Route through supervisor
        if self.supervisor:
            result = await self.supervisor.handle_task(task)
            return result.dict()
        
        return {"error": "Supervisor not initialized", "status": "failed"}
    
    async def get_platform_status(self) -> dict:
        """Get platform status"""
        health = await self.registry.health_check()
        
        return {
            "platform_status": "operational",
            "agents": self.supervisor.get_agent_status() if self.supervisor else {},
            "registry": health,
            "timestamp": health["timestamp"]
        }


async def main():
    """Main entry point"""
    logger.info("Starting multi-tenant swarm agent platform...")
    
    # Initialize platform
    platform = SwarmPlatform()
    await platform.initialize()
    
    # Log platform status
    status = await platform.get_platform_status()
    logger.info(f"Platform Status: {status}")
    
    # Submit sample task
    logger.info("Submitting sample HR task...")
    result = await platform.submit_task(
        tenant_id="hr",
        task_type="process_leave",
        payload={
            "employee_id": "EMP001",
            "leave_type": "annual",
            "days": 5
        },
        user_id="user1"
    )
    logger.info(f"Task Result: {result}")
    
    # Get final status
    final_status = await platform.get_platform_status()
    logger.info(f"Final Platform Status: {final_status}")


if __name__ == "__main__":
    asyncio.run(main())
