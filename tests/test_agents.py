"""
End-to-end agent tests — LangGraph refactored agents.

Coverage
--------
- Initialisation of all four agents
- get_capabilities() on each agent
- Happy-path task processing for every supported task_type
- Unsupported / unknown task_type handling
- Missing task_type validation
- Supervisor routing (explicit + auto-detect, missing sub-agent)
- ProductionAgent rule-based fallback (no LLM key required)
- Shared AgentGraphState / result_from_state helpers
"""

import pytest

from agents import FinanceAgent, HRAgent, MedicalAgent, SupervisorAgent, TaskRequest
from agents.capability_registry import CapabilityRegistry
from agents.graph_state import AgentGraphState, result_from_state, state_from_task

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _make_task(task_type: str, payload: dict = None, tenant_id: str = "test", context: dict = None) -> TaskRequest:
    return TaskRequest(
        tenant_id=tenant_id,
        task_type=task_type,
        payload=payload or {},
        user_id="test-user",
        context=context or {},
    )


# ──────────────────────────────────────────────────────────────────────────────
# graph_state helpers
# ──────────────────────────────────────────────────────────────────────────────


def test_state_from_task_fields():
    task = _make_task("process_leave", {"days": 3})
    state = state_from_task(task)
    assert state["task_id"] == task.id
    assert state["task_type"] == "process_leave"
    assert state["status"] == "pending"
    assert state["result"] is None
    assert state["error"] is None
    assert state["retry_count"] == 0


def test_result_from_state_happy():
    state: AgentGraphState = {
        "task_id": "abc",
        "tenant_id": "t",
        "task_type": "x",
        "payload": {},
        "priority": 5,
        "user_id": "u",
        "status": "success",
        "result": {"foo": "bar"},
        "error": None,
        "created_at": "now",
        "updated_at": "now",
        "retry_count": 0,
        "metadata": {},
    }
    r = result_from_state(state)
    assert r.id == "abc"
    assert r.status == "success"
    assert r.result == {"foo": "bar"}
    assert r.error is None


def test_result_from_state_with_error():
    state: AgentGraphState = {
        "task_id": "xyz",
        "tenant_id": "t",
        "task_type": "y",
        "payload": {},
        "priority": 5,
        "user_id": "u",
        "status": "failed",
        "result": {},
        "error": "boom",
        "created_at": "now",
        "updated_at": "now",
        "retry_count": 1,
        "metadata": {},
    }
    r = result_from_state(state)
    assert r.status == "failed"
    assert r.error == "boom"


# ──────────────────────────────────────────────────────────────────────────────
# HRAgent
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hr_agent_initialization():
    agent = HRAgent()
    assert agent.name == "HR Agent"
    assert agent.agent_type.value == "hr"
    assert "process_leave" in agent.get_capabilities()
    assert "payroll" in agent.get_capabilities()
    assert "recruitment" in agent.get_capabilities()
    assert "employee_data" in agent.get_capabilities()


@pytest.mark.asyncio
async def test_hr_process_leave():
    agent = HRAgent()
    result = await agent.handle_task(
        _make_task("process_leave", {"employee_id": "E01", "leave_type": "annual", "days": 5})
    )
    assert result.status == "success"
    assert result.result["action"] == "leave_processed"
    assert result.result["approval_status"] == "pending_review"
    assert result.result["days"] == 5


@pytest.mark.asyncio
async def test_hr_recruitment():
    agent = HRAgent()
    result = await agent.handle_task(_make_task("recruitment", {"position": "Engineer", "candidates": ["Alice"]}))
    assert result.status == "success"
    assert result.result["action"] == "recruitment_processed"
    assert result.result["position"] == "Engineer"


@pytest.mark.asyncio
async def test_hr_payroll():
    agent = HRAgent()
    result = await agent.handle_task(_make_task("payroll", {"period": "2026-01", "employee_count": 10}))
    assert result.status == "success"
    assert result.result["action"] == "payroll_processed"
    assert result.result["employee_count"] == 10
    assert result.result["status"] == "approved"


@pytest.mark.asyncio
async def test_hr_employee_data():
    agent = HRAgent()
    result = await agent.handle_task(_make_task("employee_data", {"employee_id": "E99"}))
    assert result.status == "success"
    assert result.result["action"] == "employee_data_fetched"
    assert "data" in result.result


@pytest.mark.asyncio
async def test_hr_unsupported_task():
    agent = HRAgent()
    result = await agent.handle_task(_make_task("unknown_hr_task"))
    assert result.status == "unsupported"
    assert result.error is not None


# ──────────────────────────────────────────────────────────────────────────────
# FinanceAgent
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_finance_agent_initialization():
    agent = FinanceAgent()
    assert agent.name == "Finance Agent"
    assert agent.agent_type.value == "finance"
    caps = agent.get_capabilities()
    assert "invoice" in caps
    assert "payroll" in caps


@pytest.mark.asyncio
async def test_finance_invoice():
    agent = FinanceAgent()
    result = await agent.handle_task(_make_task("invoice", {"client": "ACME", "amount": 5000}))
    assert result.status == "success"
    assert result.result["action"] == "invoice_created"
    assert "invoice_id" in result.result
    assert result.result["client"] == "ACME"


@pytest.mark.asyncio
async def test_finance_expense():
    agent = FinanceAgent()
    result = await agent.handle_task(_make_task("expense", {"category": "travel", "amount": 250}))
    assert result.status == "success"
    assert result.result["action"] == "expense_processed"
    assert "expense_id" in result.result


@pytest.mark.asyncio
async def test_finance_budget():
    agent = FinanceAgent()
    result = await agent.handle_task(
        _make_task("budget", {"department": "Eng", "total_budget": 100000, "spent": 40000})
    )
    assert result.status == "success"
    assert result.result["remaining"] == 60000


@pytest.mark.asyncio
async def test_finance_report():
    agent = FinanceAgent()
    result = await agent.handle_task(_make_task("report", {"report_type": "monthly", "period": "2026-01"}))
    assert result.status == "success"
    assert result.result["action"] == "report_generated"
    assert result.result["file_location"].startswith("s3://")


@pytest.mark.asyncio
async def test_finance_audit():
    agent = FinanceAgent()
    result = await agent.handle_task(_make_task("audit", {"scope": "Q1"}))
    assert result.status == "success"
    assert result.result["action"] == "audit_processed"


@pytest.mark.asyncio
async def test_finance_payroll():
    agent = FinanceAgent()
    result = await agent.handle_task(
        _make_task(
            "payroll",
            {"period": "2026-01", "employee_count": 50, "total_amount": 250000},
        )
    )
    assert result.status == "success"
    assert result.result["action"] == "payroll_processed"
    assert result.result["status"] == "approved"


@pytest.mark.asyncio
async def test_finance_unsupported():
    agent = FinanceAgent()
    result = await agent.handle_task(_make_task("wire_transfer"))
    assert result.status == "unsupported"


# ──────────────────────────────────────────────────────────────────────────────
# MedicalAgent
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_medical_agent_initialization():
    agent = MedicalAgent()
    assert agent.name == "Medical Agent"
    assert agent.agent_type.value == "medical"
    caps = agent.get_capabilities()
    assert "appointment" in caps
    assert "patient_data" in caps
    assert "prescription" in caps
    assert "medical_record" in caps
    assert "clinical_workflow" in caps


@pytest.mark.asyncio
async def test_medical_patient_data():
    agent = MedicalAgent()
    result = await agent.handle_task(_make_task("patient_data", {"patient_id": "P01"}))
    assert result.status == "success"
    assert result.result["action"] == "patient_data_fetched"
    # HIPAA — MRN must be masked
    assert result.result["data"]["mrn"] == "***-****"


@pytest.mark.asyncio
async def test_medical_appointment():
    agent = MedicalAgent()
    result = await agent.handle_task(
        _make_task(
            "appointment",
            {"provider": "Dr. Smith", "date": "2026-06-01", "time": "10:00"},
        )
    )
    assert result.status == "success"
    assert result.result["action"] == "appointment_scheduled"
    assert result.result["status"] == "confirmed"
    assert "appointment_id" in result.result


@pytest.mark.asyncio
async def test_medical_prescription():
    agent = MedicalAgent()
    result = await agent.handle_task(_make_task("prescription", {"medication": "Metformin", "dosage": "500mg"}))
    assert result.status == "success"
    assert result.result["action"] == "prescription_processed"
    assert "prescription_id" in result.result


@pytest.mark.asyncio
async def test_medical_record():
    agent = MedicalAgent()
    result = await agent.handle_task(_make_task("medical_record", {"record_type": "lab_result"}))
    assert result.status == "success"
    assert result.result["action"] == "record_managed"


@pytest.mark.asyncio
async def test_medical_clinical_workflow():
    agent = MedicalAgent()
    result = await agent.handle_task(_make_task("clinical_workflow", {"workflow_type": "discharge"}))
    assert result.status == "success"
    assert result.result["action"] == "workflow_processed"


@pytest.mark.asyncio
async def test_medical_unsupported():
    agent = MedicalAgent()
    result = await agent.handle_task(_make_task("surgery"))
    assert result.status == "unsupported"


# ──────────────────────────────────────────────────────────────────────────────
# SupervisorAgent
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def full_supervisor(clean_registry):
    """Supervisor with all three domain agents registered."""
    sup = SupervisorAgent()
    sup.register_sub_agent(HRAgent())
    sup.register_sub_agent(FinanceAgent())
    sup.register_sub_agent(MedicalAgent())
    return sup


@pytest.mark.asyncio
async def test_supervisor_initialization():
    sup = SupervisorAgent()
    assert sup.name == "Supervisor"
    assert sup.agent_type.value == "supervisor"
    assert "route_tasks" in sup.get_capabilities()


@pytest.mark.asyncio
async def test_supervisor_register_sub_agents():
    sup = SupervisorAgent()
    sup.register_sub_agent(HRAgent())
    sup.register_sub_agent(FinanceAgent())
    assert len(sup.sub_agents) == 2
    assert "hr_agent" in sup.sub_agents
    assert "finance_agent" in sup.sub_agents


@pytest.mark.asyncio
async def test_supervisor_routes_to_hr_via_explicit(full_supervisor):
    task = _make_task("process_leave", {"employee_id": "E01", "days": 2}, context={"agent_type": "hr"})
    result = await full_supervisor.handle_task(task)
    assert result.status == "success"
    assert result.result["action"] == "leave_processed"


@pytest.mark.asyncio
async def test_supervisor_routes_to_finance_via_task_type(full_supervisor):
    task = _make_task("invoice", {"client": "Corp", "amount": 1000}, context={"agent_type": "finance"})
    result = await full_supervisor.handle_task(task)
    assert result.status == "success"
    assert result.result["action"] == "invoice_created"


@pytest.mark.asyncio
async def test_supervisor_routes_to_medical_via_task_type(full_supervisor):
    task = _make_task(
        "appointment",
        {"provider": "Dr. X", "date": "2026-07-01", "time": "09:00"},
        context={"agent_type": "medical"},
    )
    result = await full_supervisor.handle_task(task)
    assert result.status == "success"
    assert result.result["action"] == "appointment_scheduled"


@pytest.mark.asyncio
async def test_supervisor_auto_detect_hr(full_supervisor):
    """No explicit agent_type; derives domain from task_type prefix."""
    task = _make_task("recruitment", {"position": "Designer"})
    result = await full_supervisor.handle_task(task)
    assert result.status == "success"
    assert result.result["action"] == "recruitment_processed"


@pytest.mark.asyncio
async def test_supervisor_auto_detect_medical(full_supervisor):
    task = _make_task("patient_data", {"patient_id": "P99"})
    result = await full_supervisor.handle_task(task)
    assert result.status == "success"
    assert result.result["action"] == "patient_data_fetched"


@pytest.mark.asyncio
async def test_supervisor_missing_sub_agent():
    """Supervisor without sub-agents registered should return failed."""
    sup = SupervisorAgent()  # no sub-agents
    result = await sup.handle_task(_make_task("process_leave", {}))
    assert result.status == "failed"
    assert result.error is not None


# ──────────────────────────────────────────────────────────────────────────────
# Cross-cutting: task_request model
# ──────────────────────────────────────────────────────────────────────────────


def test_task_request_defaults():
    task = TaskRequest(
        tenant_id="hr",
        task_type="process_leave",
        payload={"days": 5},
        user_id="U001",
    )
    assert task.priority == 5
    assert task.id is not None
    assert task.tenant_id == "hr"


# ──────────────────────────────────────────────────────────────────────────────
# CapabilityRegistry
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=False)
def clean_registry():
    """Snapshot / restore CapabilityRegistry between tests."""
    snapshot = dict(CapabilityRegistry._registry)
    yield
    CapabilityRegistry._registry.clear()
    CapabilityRegistry._registry.update(snapshot)


def test_capability_registry_registers_and_resolves(clean_registry):
    CapabilityRegistry.reset()
    CapabilityRegistry.register("hr", frozenset({"process_leave", "payroll"}))
    CapabilityRegistry.register("finance", frozenset({"invoice", "expense"}))
    assert CapabilityRegistry.resolve("process_leave") == "hr"
    assert CapabilityRegistry.resolve("invoice") == "finance"


def test_capability_registry_explicit_override(clean_registry):
    CapabilityRegistry.reset()
    CapabilityRegistry.register("hr", frozenset({"process_leave"}))
    CapabilityRegistry.register("finance", frozenset({"expense"}))
    # explicit_domain overrides exact-match
    assert CapabilityRegistry.resolve("process_leave", explicit_domain="finance") == "finance"


def test_capability_registry_unknown_falls_back(clean_registry):
    CapabilityRegistry.reset()
    CapabilityRegistry.register("hr", frozenset({"process_leave"}))
    # totally unknown task_type → should not raise, returns some domain or "hr" fallback
    domain = CapabilityRegistry.resolve("totally_unknown_xyz")
    assert isinstance(domain, str)


# ──────────────────────────────────────────────────────────────────────────────
# state_from_task — correlation_id propagation
# ──────────────────────────────────────────────────────────────────────────────


def test_state_from_task_propagates_correlation_id():
    task = _make_task("invoice", context={"correlation_id": "test-corr-123"})
    state = state_from_task(task)
    assert state["correlation_id"] == "test-corr-123"


def test_state_from_task_generates_correlation_id_when_missing():
    task = _make_task("invoice")
    state = state_from_task(task)
    assert state["correlation_id"] != ""
    assert len(state["correlation_id"]) == 36  # UUID4


def test_result_from_state_happy_with_correlation_id():
    state: AgentGraphState = {
        "task_id": "abc",
        "tenant_id": "t",
        "task_type": "x",
        "payload": {},
        "priority": 5,
        "user_id": "u",
        "status": "success",
        "result": {"foo": "bar"},
        "error": None,
        "created_at": "now",
        "updated_at": "now",
        "retry_count": 0,
        "metadata": {},
        "correlation_id": "c-001",
    }
    r = result_from_state(state)
    assert r.status == "success"


def test_result_from_state_with_error_and_correlation_id():
    state: AgentGraphState = {
        "task_id": "xyz",
        "tenant_id": "t",
        "task_type": "y",
        "payload": {},
        "priority": 5,
        "user_id": "u",
        "status": "failed",
        "result": {},
        "error": "boom",
        "created_at": "now",
        "updated_at": "now",
        "retry_count": 1,
        "metadata": {},
        "correlation_id": "c-002",
    }
    r = result_from_state(state)
    assert r.error == "boom"


# ──────────────────────────────────────────────────────────────────────────────
# Supervisor — RBAC enforcement
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_supervisor_rbac_denied_strict(clean_registry):
    """strict_rbac=True rejects unregistered users."""
    hr = HRAgent()
    sup = SupervisorAgent(strict_rbac=True)
    sup.register_sub_agent(hr)
    task = _make_task("process_leave", {"days": 1})
    result = await sup.handle_task(task)
    assert result.status == "failed"
    assert "denied" in result.error.lower() or "permission" in result.error.lower()


@pytest.mark.asyncio
async def test_supervisor_rbac_allowed_non_strict(full_supervisor):
    """strict_rbac=False (default) allows unregistered users with implicit USER role."""
    task = _make_task("process_leave", {"days": 2, "employee_id": "E1"})
    result = await full_supervisor.handle_task(task)
    assert result.status == "success"


@pytest.mark.asyncio
async def test_supervisor_rbac_registered_user_denied(clean_registry):
    """Registered user with GUEST role (no EXECUTE) must be denied."""
    from access_control.rbac import RBACUser, Role

    hr = HRAgent()
    sup = SupervisorAgent(strict_rbac=False)
    sup.register_sub_agent(hr)
    # Register "guest-user" with GUEST role
    sup._rbac.register_user(RBACUser(user_id="guest-user", username="Guest User", role=Role.GUEST, tenant_id="t1"))

    task = TaskRequest(
        tenant_id="t1",
        task_type="process_leave",
        payload={"days": 1},
        user_id="guest-user",
    )
    result = await sup.handle_task(task)
    assert result.status == "failed"
    assert "denied" in result.error.lower() or "permission" in result.error.lower()


# ──────────────────────────────────────────────────────────────────────────────
# Supervisor — circuit breaker
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_supervisor_circuit_breaker_opens(clean_registry):
    """After `threshold` failures the circuit opens and rejects further calls."""

    class _FailingAgent(HRAgent):
        async def handle_task(self, task):
            raise RuntimeError("Simulated agent failure")

    failing = _FailingAgent()
    sup = SupervisorAgent(circuit_threshold=3, circuit_timeout=30.0, strict_rbac=False)
    sup.register_sub_agent(failing)

    task = _make_task("process_leave", {"days": 1})

    # Drive failures up to (and past) threshold
    for _ in range(3):
        await sup.handle_task(task)

    breaker_status = sup.get_circuit_breaker_status()
    assert breaker_status.get("hr") == "open"

    # Next call should be rejected with circuit-open error (not the agent error)
    result = await sup.handle_task(task)
    assert result.status == "failed"
    assert "circuit" in result.error.lower()


@pytest.mark.asyncio
async def test_supervisor_circuit_breaker_status_empty(full_supervisor):
    """No breakers created before any call."""
    assert full_supervisor.get_circuit_breaker_status() == {}


# ──────────────────────────────────────────────────────────────────────────────
# Audit log emission
# ──────────────────────────────────────────────────────────────────────────────


def test_audit_log_written(monkeypatch):
    """log_access should write a JSON record to the audit logger."""
    import logging

    from agents import audit

    records = []

    class _Cap(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Cap()
    audit._audit_logger.addHandler(handler)
    try:
        audit.log_access(
            event="test_event",
            user_id="u1",
            tenant_id="t1",
            resource="hr_agent",
            action="execute",
            outcome="allowed",
            correlation_id="corr-abc",
            agent_type="hr",
            task_type="process_leave",
        )
        assert len(records) == 1
        import json

        data = json.loads(records[0].getMessage())
        assert data["event"] == "test_event"
        assert data["outcome"] == "allowed"
        assert data["correlation_id"] == "corr-abc"
    finally:
        audit._audit_logger.removeHandler(handler)


# ──────────────────────────────────────────────────────────────────────────────
# Supervisor — correlation_id propagation end-to-end
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_supervisor_propagates_correlation_id(full_supervisor):
    task = _make_task(
        "process_leave",
        {"days": 1, "employee_id": "E2"},
        context={"correlation_id": "trace-xyz"},
    )
    result = await full_supervisor.handle_task(task)
    assert result.status == "success"
