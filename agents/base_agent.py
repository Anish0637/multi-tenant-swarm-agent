"""
Base Agent class for multi-tenant swarm agent platform.
Provides common functionality for all agent types.
"""

import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AgentType(str, Enum):
    """Agent type enumeration"""

    SUPERVISOR = "supervisor"
    HR = "hr"
    FINANCE = "finance"
    MEDICAL = "medical"


class AgentStatus(str, Enum):
    """Agent status enumeration"""

    IDLE = "idle"
    PROCESSING = "processing"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


class Message(BaseModel):
    """Message model for agent communication"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender: str
    recipient: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    priority: int = Field(default=0, ge=0, le=10)


class TaskRequest(BaseModel):
    """Task request model"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    task_type: str
    payload: Dict[str, Any]
    priority: int = Field(default=5, ge=0, le=10)
    user_id: str
    context: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TaskResult(BaseModel):
    """Task result model"""

    id: str
    status: str
    result: Dict[str, Any]
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    completed_at: datetime = Field(default_factory=datetime.utcnow)


class BaseAgent(ABC):
    """
    Base class for all agents in the swarm.

    Provides:
    - Agent lifecycle management
    - Message routing
    - Task execution
    - Health monitoring
    - Audit logging
    """

    def __init__(
        self,
        name: str,
        agent_type: AgentType,
        tenant_id: str = "default",
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize base agent.

        Args:
            name: Agent name
            agent_type: Type of agent
            tenant_id: Tenant this agent belongs to
            config: Agent configuration
        """
        self.id = str(uuid.uuid4())
        self.name = name
        self.agent_type = agent_type
        self.tenant_id = tenant_id
        self.config = config or {}
        self.status = AgentStatus.IDLE
        self.created_at = datetime.utcnow()
        self.last_heartbeat = datetime.utcnow()
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.message_handlers: Dict[str, callable] = {}
        self.metrics = {
            "tasks_processed": 0,
            "tasks_failed": 0,
            "avg_processing_time": 0.0,
            "total_processing_time": 0.0,
        }

        logger.info(
            f"Agent {self.name} ({self.id}) initialized",
            extra={
                "agent_id": self.id,
                "agent_type": self.agent_type.value,
                "tenant_id": self.tenant_id,
            },
        )

    async def start(self) -> None:
        """Start the agent"""
        self.status = AgentStatus.PROCESSING
        logger.info(f"Agent {self.name} started")
        await self._run()

    async def stop(self) -> None:
        """Stop the agent"""
        self.status = AgentStatus.STOPPED
        logger.info(f"Agent {self.name} stopped")

    async def _run(self) -> None:
        """Main agent loop"""
        try:
            while self.status != AgentStatus.STOPPED:
                try:
                    # Process task queue with timeout
                    task = await asyncio.wait_for(self.task_queue.get(), timeout=5.0)
                    await self._process_task(task)
                except asyncio.TimeoutError:
                    # Send heartbeat
                    await self._send_heartbeat()
                except Exception as e:
                    logger.error(
                        f"Error processing task: {str(e)}",
                        extra={"agent_id": self.id, "error": str(e)},
                    )
                    self.status = AgentStatus.ERROR
        except Exception as e:
            logger.error(
                f"Agent {self.name} crashed: {str(e)}",
                extra={"agent_id": self.id, "error": str(e)},
                exc_info=True,
            )
            self.status = AgentStatus.ERROR

    async def _process_task(self, task: TaskRequest) -> None:
        """
        Process a task.

        Args:
            task: Task to process
        """
        start_time = datetime.utcnow()
        try:
            logger.info(
                f"Processing task {task.id}",
                extra={
                    "agent_id": self.id,
                    "task_id": task.id,
                    "task_type": task.task_type,
                },
            )

            result = await self.handle_task(task)

            # Update metrics
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            self.metrics["tasks_processed"] += 1
            self.metrics["total_processing_time"] += processing_time
            self.metrics["avg_processing_time"] = (
                self.metrics["total_processing_time"] / self.metrics["tasks_processed"]
            )

            logger.info(
                f"Task {task.id} completed",
                extra={
                    "agent_id": self.id,
                    "task_id": task.id,
                    "processing_time": processing_time,
                },
            )

        except Exception as e:
            self.metrics["tasks_failed"] += 1
            logger.error(
                f"Task {task.id} failed: {str(e)}",
                extra={"agent_id": self.id, "task_id": task.id, "error": str(e)},
                exc_info=True,
            )

    @abstractmethod
    async def handle_task(self, task: TaskRequest) -> TaskResult:
        """
        Handle a task (implemented by subclasses).

        Args:
            task: Task to handle

        Returns:
            Task result
        """
        pass

    async def send_message(self, message: Message) -> None:
        """
        Send a message to another agent.

        Args:
            message: Message to send
        """
        logger.info(
            f"Message from {message.sender} to {message.recipient}",
            extra={
                "message_id": message.id,
                "sender": message.sender,
                "recipient": message.recipient,
            },
        )

    async def receive_message(self, message: Message) -> None:
        """
        Receive a message from another agent.

        Args:
            message: Received message
        """
        handler = self.message_handlers.get(message.sender)
        if handler:
            await handler(message)
        else:
            logger.warning(
                f"No handler for message from {message.sender}",
                extra={"message_id": message.id},
            )

    async def _send_heartbeat(self) -> None:
        """Send heartbeat to registry"""
        self.last_heartbeat = datetime.utcnow()
        logger.debug(f"Agent {self.name} heartbeat", extra={"agent_id": self.id})

    def get_status(self) -> Dict[str, Any]:
        """Get agent status"""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.agent_type.value,
            "tenant_id": self.tenant_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "metrics": self.metrics,
        }

    def get_capabilities(self) -> List[str]:
        """Get agent capabilities (implemented by subclasses)"""
        return []
