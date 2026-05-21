"""
Medical Agent — LangGraph-powered HIPAA-compliant workflow for medical domain tasks.

Supported task types: patient_data, appointment, prescription,
                      medical_record, clinical_workflow
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

_SUPPORTED = frozenset(
    {
        "patient_data",
        "appointment",
        "prescription",
        "medical_record",
        "clinical_workflow",
    }
)


class MedicalAgent(BaseAgent):
    """
    Medical Agent with LangGraph stateful workflow (HIPAA-compliant).

    Domain: patient data management, appointment scheduling,
            prescription management, clinical workflows.
    All PII is masked in results before leaving this agent.
    """

    def __init__(
        self,
        tenant_id: str = "medical",
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            name="Medical Agent",
            agent_type=AgentType.MEDICAL,
            tenant_id=tenant_id,
            config=config or {},
        )
        CapabilityRegistry.register("medical", _SUPPORTED)
        self._graph = self._build_graph()

    # ── graph construction ──────────────────────────────────────────────────

    def _build_graph(self):
        g = StateGraph(AgentGraphState)

        g.add_node("validate", self._validate)
        g.add_node("patient_data", self._fetch_patient_data)
        g.add_node("appointment", self._schedule_appointment)
        g.add_node("prescription", self._process_prescription)
        g.add_node("medical_record", self._manage_medical_record)
        g.add_node("clinical_workflow", self._handle_clinical_workflow)
        g.add_node("unsupported", self._unsupported)
        g.add_node("handle_error", self._handle_error)
        g.add_node("complete", self._complete)

        g.add_edge(START, "validate")
        g.add_conditional_edges(
            "validate",
            self._route,
            {
                "patient_data": "patient_data",
                "appointment": "appointment",
                "prescription": "prescription",
                "medical_record": "medical_record",
                "clinical_workflow": "clinical_workflow",
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

    def _fetch_patient_data(self, state: AgentGraphState) -> AgentGraphState:
        """HIPAA: all PII masked before returning."""
        logger.info(
            "Fetching patient data: %s (user=%s tenant=%s)",
            state["task_id"],
            state["user_id"],
            state["tenant_id"],
        )
        state["result"] = {
            "action": "patient_data_fetched",
            "patient_id": "[REDACTED]",  # Masked per HIPAA
            "data": {
                "mrn": "***-****",        # Masked per HIPAA
                "age": "[REDACTED]",      # Masked per HIPAA
                "gender": "[REDACTED]",   # Masked per HIPAA
                "conditions": ["[REDACTED]"],  # Masked per HIPAA
            },
            "phi_masked": True,
        }
        return state

    def _schedule_appointment(self, state: AgentGraphState) -> AgentGraphState:
        logger.info("Scheduling appointment: %s", state["task_id"])
        state["result"] = {
            "action": "appointment_scheduled",
            "appointment_id": f"APT-{state['task_id'][:8]}",
            "provider": state["payload"].get("provider"),
            "date": state["payload"].get("date"),
            "time": state["payload"].get("time"),
            "status": "confirmed",
        }
        return state

    def _process_prescription(self, state: AgentGraphState) -> AgentGraphState:
        logger.info("Processing prescription: %s", state["task_id"])

        state["result"] = {
            "action": "prescription_processed",
            "prescription_id": f"RX-{state['task_id'][:8]}",
            "medication": state["payload"].get("medication"),
            "dosage": state["payload"].get("dosage"),
            "status": "approved",
        }
        return state

    def _manage_medical_record(self, state: AgentGraphState) -> AgentGraphState:
        logger.info("Managing medical record: %s", state["task_id"])
        state["result"] = {
            "action": "record_managed",
            "record_id": f"REC-{state['task_id'][:8]}",
            "record_type": state["payload"].get("record_type"),
            "status": "archived",
        }
        return state

    def _handle_clinical_workflow(self, state: AgentGraphState) -> AgentGraphState:
        logger.info("Handling clinical workflow: %s", state["task_id"])
        state["result"] = {
            "action": "workflow_processed",
            "workflow_id": f"WF-{state['task_id'][:8]}",
            "workflow_type": state["payload"].get("workflow_type"),
            "status": "in_progress",
        }
        return state

    # ── public interface ─────────────────────────────────────────────────────

    async def handle_task(self, task: TaskRequest) -> TaskResult:
        try:
            initial = state_from_task(task)
            final = await self._graph.ainvoke(initial)
            return result_from_state(final)
        except Exception as e:
            logger.error("Medical task failed: %s", e)
            return TaskResult(id=task.id, status="failed", result={}, error=str(e))

    def get_capabilities(self) -> List[str]:
        return sorted(_SUPPORTED)
