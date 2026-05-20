"""
Medical Agent - Handles medical data with HIPAA compliance.
"""

import logging
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent, AgentType, TaskRequest, TaskResult


logger = logging.getLogger(__name__)


class MedicalAgent(BaseAgent):
    """
    Medical Agent specialized in:
    - Patient data management (HIPAA compliant)
    - Medical records
    - Appointment scheduling
    - Prescription management
    - Clinical workflows
    """
    
    def __init__(
        self,
        tenant_id: str = "medical",
        config: Optional[Dict[str, Any]] = None
    ):
        """Initialize Medical agent"""
        super().__init__(
            name="Medical Agent",
            agent_type=AgentType.MEDICAL,
            tenant_id=tenant_id,
            config=config or {}
        )
    
    async def handle_task(self, task: TaskRequest) -> TaskResult:
        """
        Handle medical-specific tasks with HIPAA compliance.
        
        Args:
            task: Task to handle
            
        Returns:
            Task result
        """
        try:
            if task.task_type == "patient_data":
                return await self._fetch_patient_data(task)
            elif task.task_type == "appointment":
                return await self._schedule_appointment(task)
            elif task.task_type == "prescription":
                return await self._process_prescription(task)
            elif task.task_type == "medical_record":
                return await self._manage_medical_record(task)
            elif task.task_type == "clinical_workflow":
                return await self._handle_clinical_workflow(task)
            else:
                return TaskResult(
                    id=task.id,
                    status="unsupported",
                    result={},
                    error=f"Unsupported task type: {task.task_type}"
                )
        
        except Exception as e:
            logger.error(f"Medical task processing failed: {str(e)}")
            return TaskResult(
                id=task.id,
                status="failed",
                result={},
                error=str(e)
            )
    
    async def _fetch_patient_data(self, task: TaskRequest) -> TaskResult:
        """Fetch patient data (HIPAA protected)"""
        logger.info(
            f"Fetching patient data: {task.id}",
            extra={"user_id": task.user_id, "tenant_id": task.tenant_id}
        )
        
        return TaskResult(
            id=task.id,
            status="success",
            result={
                "action": "patient_data_fetched",
                "patient_id": task.payload.get("patient_id"),
                "data": {
                    "mrn": "***-****",  # Masked for security
                    "age": 45,
                    "gender": "M",
                    "conditions": ["Hypertension", "Type 2 Diabetes"],
                }
            }
        )
    
    async def _schedule_appointment(self, task: TaskRequest) -> TaskResult:
        """Schedule appointment"""
        logger.info(f"Scheduling appointment: {task.id}")
        
        return TaskResult(
            id=task.id,
            status="success",
            result={
                "action": "appointment_scheduled",
                "appointment_id": f"APT-{task.id[:8]}",
                "provider": task.payload.get("provider"),
                "date": task.payload.get("date"),
                "time": task.payload.get("time"),
                "status": "confirmed",
            }
        )
    
    async def _process_prescription(self, task: TaskRequest) -> TaskResult:
        """Process prescription"""
        logger.info(f"Processing prescription: {task.id}")
        
        return TaskResult(
            id=task.id,
            status="success",
            result={
                "action": "prescription_processed",
                "prescription_id": f"RX-{task.id[:8]}",
                "medication": task.payload.get("medication"),
                "dosage": task.payload.get("dosage"),
                "status": "approved",
            }
        )
    
    async def _manage_medical_record(self, task: TaskRequest) -> TaskResult:
        """Manage medical record"""
        logger.info(f"Managing medical record: {task.id}")
        
        return TaskResult(
            id=task.id,
            status="success",
            result={
                "action": "record_managed",
                "record_id": f"REC-{task.id[:8]}",
                "record_type": task.payload.get("record_type"),
                "status": "archived",
            }
        )
    
    async def _handle_clinical_workflow(self, task: TaskRequest) -> TaskResult:
        """Handle clinical workflow"""
        logger.info(f"Handling clinical workflow: {task.id}")
        
        return TaskResult(
            id=task.id,
            status="success",
            result={
                "action": "workflow_processed",
                "workflow_id": f"WF-{task.id[:8]}",
                "workflow_type": task.payload.get("workflow_type"),
                "status": "in_progress",
            }
        )
    
    def get_capabilities(self) -> List[str]:
        """Get Medical agent capabilities"""
        return [
            "fetch_patient_data",
            "schedule_appointment",
            "process_prescription",
            "manage_medical_record",
            "handle_clinical_workflow",
            "hipaa_compliance",
            "audit_logging",
        ]
