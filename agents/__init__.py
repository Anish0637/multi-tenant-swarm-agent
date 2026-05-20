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
    "SupervisorAgent",
    "HRAgent",
    "FinanceAgent",
    "MedicalAgent",
]
