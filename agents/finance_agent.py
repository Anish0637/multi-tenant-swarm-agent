"""
Finance Agent - Handles financial operations and compliance.
"""

import logging
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent, AgentType, TaskRequest, TaskResult


logger = logging.getLogger(__name__)


class FinanceAgent(BaseAgent):
    """
    Finance Agent specialized in:
    - Invoicing and billing
    - Expense management
    - Budget tracking
    - Financial reporting
    - Audit compliance
    """
    
    def __init__(
        self,
        tenant_id: str = "finance",
        config: Optional[Dict[str, Any]] = None
    ):
        """Initialize Finance agent"""
        super().__init__(
            name="Finance Agent",
            agent_type=AgentType.FINANCE,
            tenant_id=tenant_id,
            config=config or {}
        )
    
    async def handle_task(self, task: TaskRequest) -> TaskResult:
        """
        Handle finance-specific tasks.
        
        Args:
            task: Task to handle
            
        Returns:
            Task result
        """
        try:
            if task.task_type == "invoice":
                return await self._create_invoice(task)
            elif task.task_type == "expense":
                return await self._process_expense(task)
            elif task.task_type == "budget":
                return await self._track_budget(task)
            elif task.task_type == "report":
                return await self._generate_report(task)
            elif task.task_type == "audit":
                return await self._process_audit(task)
            else:
                return TaskResult(
                    id=task.id,
                    status="unsupported",
                    result={},
                    error=f"Unsupported task type: {task.task_type}"
                )
        
        except Exception as e:
            logger.error(f"Finance task processing failed: {str(e)}")
            return TaskResult(
                id=task.id,
                status="failed",
                result={},
                error=str(e)
            )
    
    async def _create_invoice(self, task: TaskRequest) -> TaskResult:
        """Create invoice"""
        logger.info(f"Creating invoice: {task.id}")
        
        return TaskResult(
            id=task.id,
            status="success",
            result={
                "action": "invoice_created",
                "invoice_id": f"INV-{task.id[:8]}",
                "client": task.payload.get("client"),
                "amount": task.payload.get("amount"),
                "status": "draft",
            }
        )
    
    async def _process_expense(self, task: TaskRequest) -> TaskResult:
        """Process expense"""
        logger.info(f"Processing expense: {task.id}")
        
        return TaskResult(
            id=task.id,
            status="success",
            result={
                "action": "expense_processed",
                "expense_id": f"EXP-{task.id[:8]}",
                "category": task.payload.get("category"),
                "amount": task.payload.get("amount"),
                "approval_status": "pending",
            }
        )
    
    async def _track_budget(self, task: TaskRequest) -> TaskResult:
        """Track budget"""
        logger.info(f"Tracking budget: {task.id}")
        
        return TaskResult(
            id=task.id,
            status="success",
            result={
                "action": "budget_tracked",
                "department": task.payload.get("department"),
                "total_budget": task.payload.get("total_budget"),
                "spent": task.payload.get("spent", 0),
                "remaining": task.payload.get("total_budget", 0) - task.payload.get("spent", 0),
            }
        )
    
    async def _generate_report(self, task: TaskRequest) -> TaskResult:
        """Generate financial report"""
        logger.info(f"Generating report: {task.id}")
        
        return TaskResult(
            id=task.id,
            status="success",
            result={
                "action": "report_generated",
                "report_type": task.payload.get("report_type"),
                "period": task.payload.get("period"),
                "status": "ready",
                "file_location": f"s3://reports/{task.id}.pdf",
            }
        )
    
    async def _process_audit(self, task: TaskRequest) -> TaskResult:
        """Process audit"""
        logger.info(f"Processing audit: {task.id}")
        
        return TaskResult(
            id=task.id,
            status="success",
            result={
                "action": "audit_processed",
                "audit_id": f"AUD-{task.id[:8]}",
                "scope": task.payload.get("scope"),
                "compliance_status": "in_progress",
            }
        )
    
    def get_capabilities(self) -> List[str]:
        """Get Finance agent capabilities"""
        return [
            "create_invoice",
            "process_expense",
            "track_budget",
            "generate_report",
            "process_audit",
            "manage_accounts",
            "compliance_check",
        ]
