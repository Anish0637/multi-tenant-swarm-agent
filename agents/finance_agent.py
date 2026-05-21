"""
Finance Agent — LangGraph-powered stateful workflow for Finance domain tasks.

Supported task types: invoice, expense, budget, report, audit, payroll
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

_SUPPORTED = frozenset({"invoice", "expense", "budget", "report", "audit", "payroll"})


class FinanceAgent(BaseAgent):
    """
    Finance Agent with LangGraph stateful workflow.

    Domain: invoicing, expense management, budget tracking,
            financial reporting, audit compliance, payroll.
    """

    def __init__(
        self,
        tenant_id: str = "finance",
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            name="Finance Agent",
            agent_type=AgentType.FINANCE,
            tenant_id=tenant_id,
            config=config or {},
        )
        CapabilityRegistry.register("finance", _SUPPORTED)
        self._graph = self._build_graph()

    # ── graph construction ──────────────────────────────────────────────────

    def _build_graph(self):
        g = StateGraph(AgentGraphState)

        g.add_node("validate", self._validate)
        g.add_node("invoice", self._create_invoice)
        g.add_node("expense", self._process_expense)
        g.add_node("budget", self._track_budget)
        g.add_node("report", self._generate_report)
        g.add_node("audit", self._process_audit)
        g.add_node("payroll", self._process_payroll)
        g.add_node("unsupported", self._unsupported)
        g.add_node("handle_error", self._handle_error)
        g.add_node("complete", self._complete)

        g.add_edge(START, "validate")
        g.add_conditional_edges(
            "validate",
            self._route,
            {
                "invoice": "invoice",
                "expense": "expense",
                "budget": "budget",
                "report": "report",
                "audit": "audit",
                "payroll": "payroll",
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

    # ── lifecycle nodes ──────────────────────────────────────────────────────

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

    def _create_invoice(self, state: AgentGraphState) -> AgentGraphState:
        logger.info("Creating invoice: %s", state["task_id"])
        state["result"] = {
            "action": "invoice_created",
            "invoice_id": f"INV-{state['task_id'][:8]}",
            "client": state["payload"].get("client"),
            "amount": state["payload"].get("amount"),
            "status": "draft",
        }
        return state

    def _process_expense(self, state: AgentGraphState) -> AgentGraphState:
        logger.info("Processing expense: %s", state["task_id"])

        state["result"] = {
            "action": "expense_processed",
            "expense_id": f"EXP-{state['task_id'][:8]}",
            "category": state["payload"].get("category"),
            "amount": state["payload"].get("amount"),
            "approval_status": "pending",
        }
        return state

    def _track_budget(self, state: AgentGraphState) -> AgentGraphState:
        logger.info("Tracking budget: %s", state["task_id"])
        total = state["payload"].get("total_budget", 0)
        spent = state["payload"].get("spent", 0)
        state["result"] = {
            "action": "budget_tracked",
            "department": state["payload"].get("department"),
            "total_budget": total,
            "spent": spent,
            "remaining": total - spent,
        }
        return state

    def _generate_report(self, state: AgentGraphState) -> AgentGraphState:
        logger.info("Generating report: %s", state["task_id"])
        state["result"] = {
            "action": "report_generated",
            "report_type": state["payload"].get("report_type"),
            "period": state["payload"].get("period"),
            "status": "ready",
            "file_location": f"s3://reports/{state['task_id']}.pdf",
        }
        return state

    def _process_audit(self, state: AgentGraphState) -> AgentGraphState:
        logger.info("Processing audit: %s", state["task_id"])
        state["result"] = {
            "action": "audit_processed",
            "audit_id": f"AUD-{state['task_id'][:8]}",
            "scope": state["payload"].get("scope"),
            "compliance_status": "in_progress",
        }
        return state

    def _process_payroll(self, state: AgentGraphState) -> AgentGraphState:
        logger.info("Processing payroll: %s", state["task_id"])
        state["result"] = {
            "action": "payroll_processed",
            "payroll_period": state["payload"].get("period"),
            "employee_count": state["payload"].get("employee_count", 0),
            "total_amount": state["payload"].get("total_amount", 0),
            "status": "approved",
        }
        return state

    # ── public interface ─────────────────────────────────────────────────────

    async def handle_task(self, task: TaskRequest) -> TaskResult:
        try:
            initial = state_from_task(task)
            final = await self._graph.ainvoke(initial)
            return result_from_state(final)
        except Exception as e:
            logger.error("Finance task failed: %s", e)
            return TaskResult(id=task.id, status="failed", result={}, error=str(e))

    def get_capabilities(self) -> List[str]:
        return sorted(_SUPPORTED)
