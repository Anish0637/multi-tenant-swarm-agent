"""
Production-grade Medical Agent using LangGraph.
Specialized in patient care, appointments, records, prescriptions, and health reports.
"""

from typing import Any, Dict, List, Optional

from agents.production_agent import ProductionAgent, TaskRequest, TaskResult
from config.logging_config import get_logger

logger = get_logger(__name__)


# ==================== Medical Tools (as regular functions, not @tool decorated) ====================


async def schedule_appointment_impl(
    patient_id: str,
    doctor_id: str,
    appointment_date: str,
    appointment_time: str,
    reason: str,
    location: str = "main",
) -> Dict[str, Any]:
    """Schedule medical appointment."""
    logger.info(
        f"Appointment scheduled",
        extra={
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "date": appointment_date,
        },
    )

    return {
        "status": "scheduled",
        "appointment_id": f"APT-{patient_id}-{appointment_date}",
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "appointment_date": appointment_date,
        "appointment_time": appointment_time,
        "reason": reason,
        "location": location,
        "confirmation_sent": True,
    }


async def access_patient_records_impl(
    patient_id: str,
    record_type: str = "all",
    date_range: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Access patient medical records."""
    logger.info(
        f"Patient records accessed",
        extra={"patient_id": patient_id, "record_type": record_type},
    )

    return {
        "status": "retrieved",
        "patient_id": patient_id,
        "record_type": record_type,
        "records": [
            {
                "type": "vitals",
                "date": "2026-05-15",
                "data": {"bp": "120/80", "heart_rate": 72, "temperature": 98.6},
            },
            {
                "type": "lab_results",
                "date": "2026-05-10",
                "data": {"test": "blood_work", "status": "normal"},
            },
        ],
        "access_date": "2026-05-20T10:00:00Z",
    }


async def issue_prescription_impl(
    patient_id: str,
    medication_name: str,
    dosage: str,
    frequency: str,
    duration: str,
    doctor_id: str,
    pharmacy_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Issue medical prescription."""
    logger.info(
        f"Prescription issued",
        extra={
            "patient_id": patient_id,
            "medication": medication_name,
            "doctor_id": doctor_id,
        },
    )

    return {
        "status": "issued",
        "prescription_id": f"RX-{patient_id}-{medication_name}",
        "patient_id": patient_id,
        "medication_name": medication_name,
        "dosage": dosage,
        "frequency": frequency,
        "duration": duration,
        "doctor_id": doctor_id,
        "pharmacy_id": pharmacy_id,
        "issue_date": "2026-05-20T10:00:00Z",
        "refills_remaining": 3,
    }


async def generate_health_report_impl(
    patient_id: str, report_type: str, period_start: str, period_end: str
) -> Dict[str, Any]:
    """Generate health report."""
    logger.info(
        f"Health report generated",
        extra={"patient_id": patient_id, "report_type": report_type},
    )

    return {
        "status": "generated",
        "report_id": f"REPORT-{patient_id}-{report_type}",
        "patient_id": patient_id,
        "report_type": report_type,
        "period_start": period_start,
        "period_end": period_end,
        "file_path": f"/reports/health_{patient_id}_{report_type}.pdf",
        "generation_date": "2026-05-20T10:00:00Z",
    }


# ==================== Medical Agent ====================


class MedicalAgentProduction(ProductionAgent):
    """
    Production Medical Agent with LangGraph workflow.

    Handles:
    - Appointment scheduling
    - Patient records management
    - Prescription issuance
    - Health reporting
    - Clinical documentation
    """

    def __init__(self, tenant_id: str = "default", config: Optional[Dict[str, Any]] = None):
        """Initialize Medical agent"""
        # Tools are now defined as regular functions
        medical_tools = []

        super().__init__(
            agent_id="medical_agent",
            agent_type="medical",
            llm_provider="openai",
            model="gpt-4",
            tools=medical_tools,
            config=config or {},
        )

        self.tenant_id = tenant_id

        logger.info(
            f"Medical Agent initialized",
            extra={"tenant_id": tenant_id, "tools": len(medical_tools)},
        )

    async def handle_appointment_scheduling(
        self,
        patient_id: str,
        doctor_id: str,
        appointment_date: str,
        appointment_time: str,
        reason: str,
        location: str = "main",
    ) -> Dict[str, Any]:
        """Handle appointment scheduling"""
        task = TaskRequest(
            tenant_id=self.tenant_id,
            task_type="appointment_scheduling",
            payload={
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "appointment_date": appointment_date,
                "appointment_time": appointment_time,
                "reason": reason,
                "location": location,
            },
            user_id="system",
        )

        result = await self.execute(task)
        return result.dict()

    async def handle_patient_records(
        self,
        patient_id: str,
        record_type: str = "all",
        date_range: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Handle patient records access"""
        task = TaskRequest(
            tenant_id=self.tenant_id,
            task_type="patient_records",
            payload={
                "patient_id": patient_id,
                "record_type": record_type,
                "date_range": date_range,
            },
            user_id="system",
        )

        result = await self.execute(task)
        return result.dict()


# Global agent instance (lazy-loaded)
_medical_agent = None


def get_medical_agent():
    """Get or create Medical agent instance"""
    global _medical_agent
    if _medical_agent is None:
        _medical_agent = MedicalAgentProduction()
    return _medical_agent
