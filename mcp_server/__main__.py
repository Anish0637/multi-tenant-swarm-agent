"""
MCP Server main entry point for running as a module.
"""

import logging
import uvicorn
from config.logging_config import setup_logging
from config.production import get_app_config
from mcp_server.production_server import ProductionMCPServer

# Setup logging
logger = setup_logging("mcp-server")

if __name__ == "__main__":
    app_config = get_app_config()
    
    # Create production MCP server instance
    mcp = ProductionMCPServer(
        host=app_config.mcp_server_host,
        port=app_config.mcp_server_port
    )
    
    # Run with uvicorn
    # workers > 1 requires an import string, not a direct app object; use 1 worker here
    logger.info(f"Starting Production MCP Server on {app_config.mcp_server_host}:{app_config.mcp_server_port}")
    uvicorn.run(
        mcp.app,
        host=app_config.mcp_server_host,
        port=app_config.mcp_server_port,
        workers=1,
        log_level=app_config.log_level.lower()
    )
