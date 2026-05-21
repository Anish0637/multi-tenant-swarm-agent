"""
MCP Server main entry point for running as a module.
"""

import logging

import uvicorn

from agents.base_agent import TaskRequest
from agents.finance_agent import FinanceAgent
from agents.hr_agent import HRAgent
from agents.medical_agent import MedicalAgent
from config.logging_config import setup_logging
from config.production import get_app_config
from mcp_server.production_server import ProductionMCPServer, ToolSchema

# Setup logging
logger = setup_logging("mcp-server")


async def _submit_task_handler(parameters: dict, context: dict) -> dict:
    """Route the task to the appropriate agent based on agent_type."""
    agent_type = parameters.get("agent_type", "hr").lower()
    task_type = parameters.get("task_type", "generic")
    payload = parameters.get("payload", {})
    tenant_id = parameters.get("tenant_id", "default")
    priority = int(parameters.get("priority", 5))

    task = TaskRequest(
        tenant_id=tenant_id,
        task_type=task_type,
        payload=payload,
        priority=priority,
        user_id="mcp-server",
    )

    if agent_type == "finance":
        agent = FinanceAgent(tenant_id=tenant_id)
    elif agent_type == "medical":
        agent = MedicalAgent(tenant_id=tenant_id)
    else:
        agent = HRAgent(tenant_id=tenant_id)

    result = await agent.handle_task(task)
    return result.dict()


if __name__ == "__main__":
    app_config = get_app_config()

    # Create production MCP server instance
    mcp = ProductionMCPServer(host=app_config.mcp_server_host, port=app_config.mcp_server_port)

    # Register the submit_task tool used by public-api
    mcp.register_tool(
        ToolSchema(
            name="submit_task",
            description="Submit a task to the appropriate agent (hr, finance, medical)",
            input_schema={
                "type": "object",
                "properties": {
                    "agent_type": {"type": "string"},
                    "task_type": {"type": "string"},
                    "payload": {"type": "object"},
                    "tenant_id": {"type": "string"},
                    "priority": {"type": "integer"},
                },
                "required": ["agent_type", "task_type", "payload", "tenant_id"],
            },
            output_schema={"type": "object"},
        ),
        _submit_task_handler,
    )

    # Run with uvicorn
    # workers > 1 requires an import string, not a direct app object; use 1 worker here
    logger.info(f"Starting Production MCP Server on " f"{app_config.mcp_server_host}:{app_config.mcp_server_port}")
    uvicorn.run(
        mcp.app,
        host=app_config.mcp_server_host,
        port=app_config.mcp_server_port,
        workers=1,
        log_level=app_config.log_level.lower(),
    )
