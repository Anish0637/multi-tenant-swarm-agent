"""
Shared LangGraph state schema and conversion utilities.

All domain agents (HR, Finance, Medical, Supervisor) share this canonical
AgentGraphState so that graphs can be composed and tested uniformly.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional, TypedDict

from agents.base_agent import TaskRequest, TaskResult


class AgentGraphState(TypedDict):
    """
    Canonical state carried through every agent's LangGraph workflow.

    Lifecycle: pending → processing → success | failed | unsupported
    """

    task_id: str
    tenant_id: str
    task_type: str
    payload: Dict[str, Any]
    priority: int
    user_id: str
    status: str  # pending | processing | success | failed | unsupported
    result: Optional[Dict[str, Any]]
    error: Optional[str]
    created_at: str
    updated_at: str
    retry_count: int
    metadata: Dict[str, Any]
    correlation_id: str  # propagated from X-Correlation-ID header end-to-end


def state_from_task(task: TaskRequest) -> AgentGraphState:
    """Build an initial AgentGraphState from a TaskRequest."""
    return AgentGraphState(
        task_id=task.id,
        tenant_id=task.tenant_id,
        task_type=task.task_type,
        payload=dict(task.payload),
        priority=task.priority,
        user_id=task.user_id,
        status="pending",
        result=None,
        error=None,
        created_at=str(task.created_at),
        updated_at=datetime.utcnow().isoformat(),
        retry_count=0,
        metadata={},
        correlation_id=(task.context or {}).get("correlation_id", str(uuid.uuid4())),
    )


def result_from_state(state: AgentGraphState) -> TaskResult:
    """Convert a terminal AgentGraphState back to a TaskResult."""
    return TaskResult(
        id=state["task_id"],
        status=state["status"],
        result=state["result"] or {},
        error=state.get("error"),
        metadata=state.get("metadata") or {},
    )
