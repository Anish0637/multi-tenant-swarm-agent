"""
HR Agent — LangGraph-powered stateful workflow for HR domain tasks.

Supported task types: process_leave, recruitment, payroll, employee_data
Graph: START → validate → [handler] → complete → END
                        ↘ unsupported/handle_error → END
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from langgraph.graph import END, START, StateGraph

from agents.base_agent import AgentType, BaseAgent, TaskRequest, TaskResult
from agents.capability_registry import CapabilityRegistry
from agents.graph_state import AgentGraphState, result_from_state, state_from_task

logger = logging.getLogger(__name__)

_SUPPORTED = frozenset({"process_leave", "recruitment", "payroll", "employee_data"})


class HRAgent(BaseAgent):
    """
    HR Agent with LangGraph stateful workflow.

    Domain: employee management, leave & attendance, recruitment,
            payroll processing, compliance policies.
    """

    def __init__(self, tenant_id: str = "hr", config: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="HR Agent",
            agent_type=AgentType.HR,
            tenant_id=tenant_id,
            config=config or {},
        )
        CapabilityRegistry.register("hr", _SUPPORTED)
        self._graph = self._build_graph()

    # ── graph construction ──────────────────────────────────────────────────

    def _build_graph(self):
        g = StateGraph(AgentGraphState)

        g.add_node("validate", self._validate)
        g.add_node("process_leave", self._process_leave)
        g.add_node("recruitment", self._handle_recruitment)
        g.add_node("payroll", self._process_payroll)
        g.add_node("employee_data", self._fetch_employee_data)
        g.add_node("unsupported", self._unsupported)
        g.add_node("handle_error", self._handle_error)
        g.add_node("complete", self._complete)

        g.add_edge(START, "validate")
        g.add_conditional_edges(
            "validate",
            self._route,
            {
                "process_leave": "process_leave",
                "recruitment": "recruitment",
                "payroll": "payroll",
                "employee_data": "employee_data",
                "unsupported": "unsupported",
                "error": "handle_error",
            },
        )
        for node in _SUPPORTED:
            g.add_edge(node, "complete")
        g.add_edge("complete", END)
        g.add_edge("unsupported", END)
        g.add_edge("handle_error", END)

        return g.compile()

    # ── routing ─────────────────────────────────────────────────────────────

    def _route(self, state: AgentGraphState) -> str:
        if state.get("error"):
            return "error"
        tt = state["task_type"]
        return tt if tt in _SUPPORTED else "unsupported"

    # ── shared lifecycle nodes ───────────────────────────────────────────────

    def _validate(self, state: AgentGraphState) -> AgentGraphState:
        state["status"] = "processing"
        state["updated_at"] = datetime.utcnow().isoformat()
        if not state.get("task_type"):
            state["error"] = "Missing task_type"
        return state

    def _complete(self, state: AgentGraphState) -> AgentGraphState:
        state["status"] = "success"
        state["updated_at"] = datetime.utcnow().isoformat()
        return state

    def _unsupported(self, state: AgentGraphState) -> AgentGraphState:
        state["status"] = "unsupported"
        state["error"] = f"Unsupported task type: {state['task_type']}"
        state["result"] = {}
        return state

    def _handle_error(self, state: AgentGraphState) -> AgentGraphState:
        state["status"] = "failed"
        state["result"] = {}
        return state

    # ── domain handler nodes ─────────────────────────────────────────────────

    def _process_leave(self, state: AgentGraphState) -> AgentGraphState:
        logger.info("Processing leave request: %s", state["task_id"])
        state["result"] = {
            "action": "leave_processed",
            "employee_id": state["payload"].get("employee_id"),
            "leave_type": state["payload"].get("leave_type"),
            "days": state["payload"].get("days"),
            "approval_status": "pending_review",
        }
        return state

    def _handle_recruitment(self, state: AgentGraphState) -> AgentGraphState:
        logger.info("Processing recruitment: %s", state["task_id"])
        state["result"] = {
            "action": "recruitment_processed",
            "position": state["payload"].get("position"),
            "candidates": state["payload"].get("candidates", []),
            "status": "in_progress",
        }
        return state

    def _process_payroll(self, state: AgentGraphState) -> AgentGraphState:
        logger.info("Processing payroll: %s", state["task_id"])
        state["result"] = {
            "action": "payroll_processed",
            "payroll_period": state["payload"].get("period"),
            "employee_count": state["payload"].get("employee_count", 0),
            "status": "approved",
        }
        return state

    def _fetch_employee_data(self, state: AgentGraphState) -> AgentGraphState:
        logger.info("Fetching employee data: %s", state["task_id"])
        state["result"] = {
            "action": "employee_data_fetched",
            "employee_id": state["payload"].get("employee_id"),
            "data": {
                "name": "John Doe",
                "department": "Engineering",
                "status": "active",
            },
        }
        return state

    # ── public interface ─────────────────────────────────────────────────────

    async def handle_task(self, task: TaskRequest) -> TaskResult:
        try:
            initial = state_from_task(task)
            final = await self._graph.ainvoke(initial)
            return result_from_state(final)
        except Exception as e:
            logger.error("HR task failed: %s", e)
            return TaskResult(id=task.id, status="failed", result={}, error=str(e))

    def get_capabilities(self) -> List[str]:
        return sorted(_SUPPORTED)
