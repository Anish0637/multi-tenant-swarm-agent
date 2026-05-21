"""
Package initialization for agents module.
"""

from agents.base_agent import (
    BaseAgent,
    AgentType,
    AgentStatus,
    Message,
    TaskRequest,
    TaskResult,
)
from agents.graph_state import AgentGraphState, state_from_task, result_from_state
from agents.capability_registry import CapabilityRegistry
from agents import audit
from agents.supervisor import SupervisorAgent
from agents.hr_agent import HRAgent
from agents.finance_agent import FinanceAgent
from agents.medical_agent import MedicalAgent

__all__ = [
    "BaseAgent",
    "AgentType",
    "AgentStatus",
    "Message",
    "TaskRequest",
    "TaskResult",
    "AgentGraphState",
    "state_from_task",
    "result_from_state",
    "CapabilityRegistry",
    "audit",
    "SupervisorAgent",
    "HRAgent",
    "FinanceAgent",
    "MedicalAgent",
]
