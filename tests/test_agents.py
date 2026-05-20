"""
Test agents functionality.
"""

import asyncio
import pytest
from agents import SupervisorAgent, HRAgent, FinanceAgent, MedicalAgent, TaskRequest


@pytest.mark.asyncio
async def test_hr_agent_initialization():
    """Test HR agent initialization"""
    agent = HRAgent()
    assert agent.name == "HR Agent"
    assert agent.agent_type.value == "hr"
    assert "process_leave" in agent.get_capabilities()


@pytest.mark.asyncio
async def test_finance_agent_initialization():
    """Test Finance agent initialization"""
    agent = FinanceAgent()
    assert agent.name == "Finance Agent"
    assert agent.agent_type.value == "finance"
    assert "create_invoice" in agent.get_capabilities()


@pytest.mark.asyncio
async def test_medical_agent_initialization():
    """Test Medical agent initialization"""
    agent = MedicalAgent()
    assert agent.name == "Medical Agent"
    assert agent.agent_type.value == "medical"
    assert "fetch_patient_data" in agent.get_capabilities()


@pytest.mark.asyncio
async def test_supervisor_agent():
    """Test supervisor agent"""
    supervisor = SupervisorAgent()
    assert supervisor.name == "Supervisor"
    assert supervisor.agent_type.value == "supervisor"
    
    # Register sub-agents
    hr_agent = HRAgent()
    finance_agent = FinanceAgent()
    
    supervisor.register_sub_agent(hr_agent)
    supervisor.register_sub_agent(finance_agent)
    
    assert len(supervisor.sub_agents) == 2


@pytest.mark.asyncio
async def test_task_request():
    """Test task request creation"""
    task = TaskRequest(
        tenant_id="hr",
        task_type="process_leave",
        payload={"employee_id": "EMP001", "days": 5},
        user_id="USER001"
    )
    assert task.tenant_id == "hr"
    assert task.task_type == "process_leave"
    assert task.payload["days"] == 5


@pytest.mark.asyncio
async def test_hr_agent_task_processing():
    """Test HR agent task processing"""
    agent = HRAgent()
    task = TaskRequest(
        tenant_id="hr",
        task_type="process_leave",
        payload={"employee_id": "EMP001", "leave_type": "annual", "days": 5},
        user_id="USER001"
    )
    
    result = await agent.handle_task(task)
    assert result.status == "success"
    assert result.result["action"] == "leave_processed"


@pytest.mark.asyncio
async def test_finance_agent_invoice():
    """Test finance agent invoice creation"""
    agent = FinanceAgent()
    task = TaskRequest(
        tenant_id="finance",
        task_type="invoice",
        payload={"client": "ACME Corp", "amount": 5000},
        user_id="USER001"
    )
    
    result = await agent.handle_task(task)
    assert result.status == "success"
    assert result.result["action"] == "invoice_created"
    assert "invoice_id" in result.result


@pytest.mark.asyncio
async def test_medical_agent_patient_data():
    """Test medical agent patient data"""
    agent = MedicalAgent()
    task = TaskRequest(
        tenant_id="medical",
        task_type="patient_data",
        payload={"patient_id": "PAT001"},
        user_id="USER001"
    )
    
    result = await agent.handle_task(task)
    assert result.status == "success"
    assert result.result["action"] == "patient_data_fetched"
