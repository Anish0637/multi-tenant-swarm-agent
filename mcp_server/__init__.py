"""
Package initialization for MCP server module.
"""

# Primary (production) server — use this in all new code
from mcp_server.production_server import ProductionMCPServer, ToolSchema, ToolRequest, ToolResponse

# Legacy compatibility — MCPServer, ToolDefinition kept for main.py and test_mcp_server.py
from mcp_server.server import MCPServer, ToolDefinition
from mcp_server.server import ToolRequest as _LegacyToolRequest  # noqa: F401

__all__ = [
    # Production
    "ProductionMCPServer",
    "ToolSchema",
    "ToolRequest",
    "ToolResponse",
    # Legacy (deprecated — use ProductionMCPServer instead)
    "MCPServer",
    "ToolDefinition",
]
