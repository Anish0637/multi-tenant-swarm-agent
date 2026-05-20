"""
Supervisor Agent - Orchestrates other agents and manages task distribution.
"""

import logging
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent, AgentType, TaskRequest, TaskResult


logger = logging.getLogger(__name__)


class SupervisorAgent(BaseAgent):
    """
    Supervisor agent that:
    - Routes tasks to appropriate sub-agents
    - Manages agent lifecycle
    - Handles failover and recovery
    - Monitors system health
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize supervisor agent"""
        super().__init__(
            name="Supervisor",
            agent_type=AgentType.SUPERVISOR,
            tenant_id="system",
            config=config or {}
        )
        self.sub_agents: Dict[str, BaseAgent] = {}
        self.task_routing: Dict[str, str] = {
            "hr": "hr_agent",
            "finance": "finance_agent",
            "medical": "medical_agent",
        }
    
    async def handle_task(self, task: TaskRequest) -> TaskResult:
        """
        Route task to appropriate sub-agent.
        
        Args:
            task: Task to route
            
        Returns:
            Task result
        """
        try:
            # Determine target agent
            target_agent_name = self.task_routing.get(
                task.task_type,
                "hr_agent"  # Default routing
            )
            
            target_agent = self.sub_agents.get(target_agent_name)
            if not target_agent:
                raise ValueError(f"Target agent {target_agent_name} not found")
            
            # Queue task with target agent
            await target_agent.task_queue.put(task)
            
            return TaskResult(
                id=task.id,
                status="routed",
                result={
                    "target_agent": target_agent_name,
                    "timestamp": str(task.created_at),
                }
            )
            
        except Exception as e:
            logger.error(f"Task routing failed: {str(e)}")
            return TaskResult(
                id=task.id,
                status="failed",
                result={},
                error=str(e)
            )
    
    def register_sub_agent(self, agent: BaseAgent) -> None:
        """
        Register a sub-agent.
        
        Args:
            agent: Agent to register
        """
        agent_key = f"{agent.agent_type.value}_agent"
        self.sub_agents[agent_key] = agent
        logger.info(
            f"Sub-agent registered: {agent.name}",
            extra={"agent_id": agent.id, "agent_key": agent_key}
        )
    
    def get_capabilities(self) -> List[str]:
        """Get supervisor capabilities"""
        return [
            "route_tasks",
            "manage_agents",
            "health_check",
            "failover",
            "monitoring",
            "load_balancing",
        ]
    
    def get_agent_status(self) -> Dict[str, Any]:
        """Get status of all agents"""
        return {
            "supervisor": super().get_status(),
            "sub_agents": {
                name: agent.get_status()
                for name, agent in self.sub_agents.items()
            }
        }
