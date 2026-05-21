"""
MCP Server - Model Context Protocol server for agent tool management.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ToolDefinition(BaseModel):
    """Tool definition"""

    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    required_permissions: List[str]


class ToolRequest(BaseModel):
    """Tool request"""

    tool_name: str
    tool_id: str
    parameters: Dict[str, Any]
    context: Dict[str, Any]


class ToolResponse(BaseModel):
    """Tool response"""

    tool_id: str
    status: str
    result: Dict[str, Any]
    error: Optional[str] = None


class MCPServer:
    """
    Model Context Protocol (MCP) Server for managing agent tools.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
        """Initialize MCP server"""
        self.host = host
        self.port = port
        self.app = FastAPI(title="MCP Server", version="1.0.0")
        self.tools: Dict[str, ToolDefinition] = {}
        self.tool_handlers: Dict[str, callable] = {}
        self._setup_routes()
        self._register_default_tools()

    def _setup_routes(self) -> None:
        """Setup FastAPI routes"""

        @self.app.get("/health")
        async def health():
            """Health check"""
            return {"status": "healthy", "server": "MCP"}

        @self.app.get("/tools")
        async def list_tools():
            """List available tools"""
            return {"tools": [{"name": tool.name, "description": tool.description} for tool in self.tools.values()]}

        @self.app.get("/tools/{tool_name}")
        async def get_tool(tool_name: str):
            """Get tool definition"""
            if tool_name not in self.tools:
                raise HTTPException(status_code=404, detail="Tool not found")

            tool = self.tools[tool_name]
            return {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
            }

        @self.app.post("/tools/execute")
        async def execute_tool(request: ToolRequest):
            """Execute a tool"""
            if request.tool_name not in self.tools:
                return ToolResponse(
                    tool_id=request.tool_id,
                    status="failed",
                    result={},
                    error=f"Tool {request.tool_name} not found",
                )

            handler = self.tool_handlers.get(request.tool_name)
            if not handler:
                return ToolResponse(
                    tool_id=request.tool_id,
                    status="failed",
                    result={},
                    error=f"No handler for tool {request.tool_name}",
                )

            try:
                result = await handler(request.parameters, request.context)
                return ToolResponse(tool_id=request.tool_id, status="success", result=result)
            except Exception as e:
                logger.error(f"Tool execution failed: {str(e)}")
                return ToolResponse(tool_id=request.tool_id, status="failed", result={}, error=str(e))

    def _register_default_tools(self) -> None:
        """Register default tools"""

        # Agent management tools
        self.register_tool(
            ToolDefinition(
                name="list_agents",
                description="List all available agents",
                input_schema={
                    "type": "object",
                    "properties": {
                        "agent_type": {"type": "string"},
                        "tenant_id": {"type": "string"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {"agents": {"type": "array"}},
                },
                required_permissions=["read"],
            ),
            self._list_agents_handler,
        )

        self.register_tool(
            ToolDefinition(
                name="submit_task",
                description="Submit a task to an agent",
                input_schema={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                        "task_type": {"type": "string"},
                        "payload": {"type": "object"},
                    },
                    "required": ["agent_id", "task_type"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "status": {"type": "string"},
                    },
                },
                required_permissions=["write", "execute"],
            ),
            self._submit_task_handler,
        )

        self.register_tool(
            ToolDefinition(
                name="get_agent_status",
                description="Get status of an agent",
                input_schema={
                    "type": "object",
                    "properties": {"agent_id": {"type": "string"}},
                    "required": ["agent_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {"status": {"type": "string"}},
                },
                required_permissions=["read"],
            ),
            self._get_agent_status_handler,
        )

    def register_tool(self, tool: ToolDefinition, handler: callable) -> None:
        """Register a tool and its handler"""
        self.tools[tool.name] = tool
        self.tool_handlers[tool.name] = handler
        logger.info(f"Tool registered: {tool.name}")

    async def _list_agents_handler(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Handler for list_agents tool"""
        return {
            "agents": [
                {
                    "id": "supervisor",
                    "name": "Supervisor Agent",
                    "type": "supervisor",
                    "status": "healthy",
                },
                {
                    "id": "hr_agent",
                    "name": "HR Agent",
                    "type": "hr",
                    "status": "healthy",
                },
                {
                    "id": "finance_agent",
                    "name": "Finance Agent",
                    "type": "finance",
                    "status": "healthy",
                },
                {
                    "id": "medical_agent",
                    "name": "Medical Agent",
                    "type": "medical",
                    "status": "healthy",
                },
            ]
        }

    async def _submit_task_handler(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Handler for submit_task tool"""
        return {
            "task_id": f"task-{params.get('agent_id')}",
            "status": "submitted",
            "message": f"Task submitted to {params.get('agent_id')}",
        }

    async def _get_agent_status_handler(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Handler for get_agent_status tool"""
        return {
            "status": "healthy",
            "agent_id": params.get("agent_id"),
            "tasks_processed": 42,
            "uptime_seconds": 3600,
        }
