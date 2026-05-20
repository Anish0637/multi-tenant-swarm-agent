"""
Production-grade Finance Agent using LangGraph.
Specialized in expenses, budgets, invoices, payments, and financial reporting.
"""

from typing import Any, Dict, Optional, List

from agents.production_agent import ProductionAgent, TaskRequest, TaskResult
from config.logging_config import get_logger


logger = get_logger(__name__)


# ==================== Finance Tools (as regular functions, not @tool decorated) ====================

async def process_expense_report_impl(
    report_id: str,
    employee_id: str,
    amount: float,
    category: str,
    date: str,
    description: str,
    attachments: List[str] = None
) -> Dict[str, Any]:
    """Process expense report submission."""
    logger.info(
        f"Expense report processed",
        extra={
            "report_id": report_id,
            "amount": amount,
            "category": category
        }
    )
    
    return {
        "status": "submitted",
        "report_id": report_id,
        "employee_id": employee_id,
        "amount": amount,
        "category": category,
        "date": date,
        "description": description,
        "submission_date": "2026-05-20T10:00:00Z",
        "approval_status": "pending_review"
    }


async def budget_planning_impl(
    department: str,
    fiscal_year: str,
    budget_amount: float,
    items: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Create budget plan."""
    logger.info(
        f"Budget plan created",
        extra={
            "department": department,
            "fiscal_year": fiscal_year,
            "budget": budget_amount
        }
    )
    
    return {
        "status": "created",
        "department": department,
        "fiscal_year": fiscal_year,
        "total_budget": budget_amount,
        "items_count": len(items),
        "creation_date": "2026-05-20T10:00:00Z",
        "approval_status": "draft"
    }


async def invoice_processing_impl(
    invoice_id: str,
    vendor_id: str,
    amount: float,
    due_date: str,
    description: str,
    line_items: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Process invoice."""
    logger.info(
        f"Invoice processed",
        extra={
            "invoice_id": invoice_id,
            "amount": amount,
            "vendor_id": vendor_id
        }
    )
    
    return {
        "status": "received",
        "invoice_id": invoice_id,
        "vendor_id": vendor_id,
        "amount": amount,
        "due_date": due_date,
        "description": description,
        "line_items": line_items or [],
        "receipt_date": "2026-05-20T10:00:00Z",
        "approval_status": "pending_payment"
    }


async def generate_financial_report_impl(
    report_type: str,
    start_date: str,
    end_date: str,
    department: str = "all",
    format: str = "pdf"
) -> Dict[str, Any]:
    """Generate financial report."""
    logger.info(
        f"Financial report generated",
        extra={
            "report_type": report_type,
            "period": f"{start_date} to {end_date}",
            "department": department
        }
    )
    
    return {
        "status": "generated",
        "report_type": report_type,
        "start_date": start_date,
        "end_date": end_date,
        "department": department,
        "format": format,
        "file_path": f"/reports/{report_type}_{start_date}_{end_date}.{format}",
        "generation_date": "2026-05-20T10:00:00Z"
    }


# ==================== Finance Agent ====================

class FinanceAgentProduction(ProductionAgent):
    """
    Production Finance Agent with LangGraph workflow.
    
    Handles:
    - Expense management
    - Budget planning
    - Invoice processing
    - Financial reporting
    - Payment approvals
    """
    
    def __init__(self, tenant_id: str = "default", config: Optional[Dict[str, Any]] = None):
        """Initialize Finance agent"""
        # Tools are now defined as regular functions
        finance_tools = []
        
        super().__init__(
            agent_id="finance_agent",
            agent_type="finance",
            llm_provider="openai",
            model="gpt-4",
            tools=finance_tools,
            config=config or {}
        )
        
        self.tenant_id = tenant_id
        
        logger.info(
            f"Finance Agent initialized",
            extra={
                "tenant_id": tenant_id,
                "tools": len(finance_tools)
            }
        )
    
    async def handle_expense_report(
        self,
        report_id: str,
        employee_id: str,
        amount: float,
        category: str,
        date: str,
        description: str,
        attachments: List[str] = None
    ) -> Dict[str, Any]:
        """Handle expense report"""
        task = TaskRequest(
            tenant_id=self.tenant_id,
            task_type="expense_report",
            payload={
                "report_id": report_id,
                "employee_id": employee_id,
                "amount": amount,
                "category": category,
                "date": date,
                "description": description,
                "attachments": attachments or []
            },
            user_id="system"
        )
        
        result = await self.execute(task)
        return result.dict()
    
    async def handle_budget_planning(
        self,
        department: str,
        fiscal_year: str,
        budget_amount: float,
        items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Handle budget planning"""
        task = TaskRequest(
            tenant_id=self.tenant_id,
            task_type="budget_planning",
            payload={
                "department": department,
                "fiscal_year": fiscal_year,
                "budget_amount": budget_amount,
                "items": items
            },
            user_id="system"
        )
        
        result = await self.execute(task)
        return result.dict()


# Global agent instance (lazy-loaded)
_finance_agent = None

def get_finance_agent():
    """Get or create Finance agent instance"""
    global _finance_agent
    if _finance_agent is None:
        _finance_agent = FinanceAgentProduction()
    return _finance_agent
