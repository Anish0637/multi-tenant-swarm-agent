"""
Production-grade MCP (Model Context Protocol) Server with FastAPI.
Handles tool management, agent routing, and request processing with security & monitoring.
"""

import asyncio
import time
import logging
import json
import uuid
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime

from fastapi import FastAPI, HTTPException, Header, Request, Depends, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from pydantic import BaseModel, Field, field_validator
from contextlib import asynccontextmanager

from config.production import get_app_config, get_security_config
from config.logging_config import get_logger

try:
    from aws_xray_sdk.core import xray_recorder
    from aws_xray_sdk.core import patch_all
    XRAY_AVAILABLE = True
except ImportError:
    XRAY_AVAILABLE = False


logger = get_logger("mcp-server")


# ==================== Models ====================

class ToolSchema(BaseModel):
    """Tool schema definition"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    required_permissions: List[str] = Field(default_factory=list)


class ToolRequest(BaseModel):
    """Tool execution request"""
    tool_name: str
    tool_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parameters: Dict[str, Any]
    context: Dict[str, Any] = Field(default_factory=dict)
    request_timeout: int = Field(default=30)
    
    @field_validator('tool_name', mode='before')
    @classmethod
    def validate_tool_name(cls, v):
        if not v or len(v) > 100:
            raise ValueError("Invalid tool name")
        return v


class ToolResponse(BaseModel):
    """Tool execution response"""
    tool_id: str
    tool_name: str
    status: str
    result: Dict[str, Any]
    error: Optional[str] = None
    execution_time_ms: float
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class AgentInfo(BaseModel):
    """Agent information"""
    agent_id: str
    agent_type: str
    status: str
    tools_count: int
    last_heartbeat: str


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    timestamp: str
    uptime_seconds: float


# ==================== Dependencies & Middleware ====================

limiter = Limiter(key_func=get_remote_address)

# Authentication dependency
async def verify_api_key(
    x_api_key: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """Verify API key"""
    security_config = get_security_config()
    
    if not security_config.api_key_enabled:
        return {"authenticated": True}
    
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required"
        )
    
    # In production, validate against a database/secret store
    if x_api_key not in security_config.api_keys.values():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    return {"authenticated": True, "api_key": x_api_key}


# ==================== Production MCP Server ====================

class ProductionMCPServer:
    """
    Production-grade MCP Server with:
    - FastAPI integration
    - Rate limiting
    - API authentication
    - Distributed tracing (X-Ray)
    - Structured logging
    - Error recovery
    - Metrics collection
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
        """Initialize MCP Server"""
        self.host = host
        self.port = port
        self.start_time = time.time()
        self.tools: Dict[str, ToolSchema] = {}
        self.tool_handlers: Dict[str, Callable] = {}
        self.agents: Dict[str, Dict[str, Any]] = {}
        self.config = get_app_config()
        
        # Setup X-Ray if available
        if XRAY_AVAILABLE:
            patch_all()
            xray_recorder.configure(service="swarm-agent-mcp")
        
        # Create FastAPI app with lifespan
        self.app = self._create_app()
        
        logger.info(
            "MCP Server initialized",
            extra={
                "host": self.host,
                "port": self.port,
                "xray_enabled": XRAY_AVAILABLE
            }
        )
    
    def _create_app(self) -> FastAPI:
        """Create FastAPI application"""
        
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            logger.info("MCP Server starting")
            yield
            # Shutdown
            logger.info("MCP Server shutting down")
        
        app = FastAPI(
            title="MCP Server",
            version="2.0.0",
            description="Production-grade Model Context Protocol Server",
            lifespan=lifespan
        )
        
        # Add CORS middleware
        security_config = get_security_config()
        if security_config.cors_enabled:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=security_config.cors_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        
        # Add rate limiting
        app.state.limiter = limiter
        app.add_exception_handler(
            Exception,
            self._global_exception_handler
        )
        
        # Setup routes
        self._setup_routes(app)
        
        return app
    
    def _setup_routes(self, app: FastAPI) -> None:
        """Setup FastAPI routes"""
        
        @app.get("/health", response_model=HealthResponse)
        async def health_check():
            """Health check endpoint"""
            uptime = time.time() - self.start_time
            return HealthResponse(
                status="healthy",
                version="2.0.0",
                timestamp=datetime.utcnow().isoformat(),
                uptime_seconds=uptime
            )
        
        @app.get("/tools")
        async def list_tools(
            auth: Dict = Depends(verify_api_key)
        ):
            """List all available tools"""
            return {
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "required_permissions": tool.required_permissions
                    }
                    for tool in self.tools.values()
                ],
                "total": len(self.tools)
            }
        
        @app.get("/tools/{tool_name}", response_model=ToolSchema)
        async def get_tool_definition(
            tool_name: str,
            auth: Dict = Depends(verify_api_key)
        ):
            """Get tool definition"""
            if tool_name not in self.tools:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Tool '{tool_name}' not found"
                )
            return self.tools[tool_name]
        
        @app.post("/tools/execute", response_model=ToolResponse)
        @limiter.limit("1000/minute")
        async def execute_tool(
            request: Request,
            tool_request: ToolRequest,
            auth: Dict = Depends(verify_api_key)
        ):
            """Execute a tool"""
            start_time = time.time()
            
            logger.info(
                f"Tool execution requested",
                extra={
                    "tool_name": tool_request.tool_name,
                    "tool_id": tool_request.tool_id,
                    "correlation_id": tool_request.context.get("correlation_id")
                }
            )
            
            # Validate tool exists
            if tool_request.tool_name not in self.tools:
                logger.warning(
                    f"Tool not found",
                    extra={"tool_name": tool_request.tool_name}
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Tool '{tool_request.tool_name}' not found"
                )
            
            # Get handler
            handler = self.tool_handlers.get(tool_request.tool_name)
            if not handler:
                logger.error(
                    f"No handler for tool",
                    extra={"tool_name": tool_request.tool_name}
                )
                return ToolResponse(
                    tool_id=tool_request.tool_id,
                    tool_name=tool_request.tool_name,
                    status="error",
                    result={},
                    error=f"No handler for tool {tool_request.tool_name}",
                    execution_time_ms=(time.time() - start_time) * 1000
                )
            
            # Execute with X-Ray tracing
            try:
                if XRAY_AVAILABLE:
                    with xray_recorder.capture(f"tool_{tool_request.tool_name}"):
                        result = await handler(tool_request.parameters, tool_request.context)
                else:
                    result = await handler(tool_request.parameters, tool_request.context)
                
                execution_time = (time.time() - start_time) * 1000
                
                logger.info(
                    f"Tool executed successfully",
                    extra={
                        "tool_name": tool_request.tool_name,
                        "tool_id": tool_request.tool_id,
                        "execution_time_ms": execution_time
                    }
                )
                
                return ToolResponse(
                    tool_id=tool_request.tool_id,
                    tool_name=tool_request.tool_name,
                    status="success",
                    result=result,
                    execution_time_ms=execution_time
                )
            
            except asyncio.TimeoutError:
                execution_time = (time.time() - start_time) * 1000
                logger.error(
                    f"Tool execution timeout",
                    extra={
                        "tool_name": tool_request.tool_name,
                        "timeout_seconds": tool_request.request_timeout,
                        "execution_time_ms": execution_time
                    }
                )
                return ToolResponse(
                    tool_id=tool_request.tool_id,
                    tool_name=tool_request.tool_name,
                    status="timeout",
                    result={},
                    error="Tool execution timeout",
                    execution_time_ms=execution_time
                )
            
            except Exception as e:
                execution_time = (time.time() - start_time) * 1000
                logger.error(
                    f"Tool execution failed",
                    extra={
                        "tool_name": tool_request.tool_name,
                        "error": str(e),
                        "execution_time_ms": execution_time
                    }
                )
                return ToolResponse(
                    tool_id=tool_request.tool_id,
                    tool_name=tool_request.tool_name,
                    status="error",
                    result={},
                    error=str(e),
                    execution_time_ms=execution_time
                )
        
        @app.get("/agents")
        async def list_agents(
            auth: Dict = Depends(verify_api_key)
        ):
            """List all registered agents"""
            return {
                "agents": [
                    {
                        "agent_id": agent_id,
                        "info": info
                    }
                    for agent_id, info in self.agents.items()
                ],
                "total": len(self.agents)
            }
        
        @app.get("/agents/{agent_id}")
        async def get_agent_status(
            agent_id: str,
            auth: Dict = Depends(verify_api_key)
        ):
            """Get agent status"""
            if agent_id not in self.agents:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent '{agent_id}' not found"
                )
            return self.agents[agent_id]
        
        @app.post("/metrics")
        async def record_metric(
            metric: Dict[str, Any],
            auth: Dict = Depends(verify_api_key)
        ):
            """Record custom metric"""
            logger.info(
                "Metric recorded",
                extra={"metric": metric}
            )
            return {"status": "recorded"}
    
    async def _global_exception_handler(self, request: Request, exc: Exception):
        """Global exception handler"""
        logger.error(
            f"Unhandled exception",
            extra={
                "path": request.url.path,
                "method": request.method,
                "error": str(exc)
            }
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Internal server error",
                "request_id": request.headers.get("x-request-id", "unknown")
            }
        )
    
    def register_tool(self, tool_schema: ToolSchema, handler: Callable) -> None:
        """Register a tool"""
        self.tools[tool_schema.name] = tool_schema
        self.tool_handlers[tool_schema.name] = handler
        logger.info(f"Tool registered: {tool_schema.name}")
    
    def register_agent(self, agent_id: str, agent_info: Dict[str, Any]) -> None:
        """Register an agent"""
        self.agents[agent_id] = {
            **agent_info,
            "last_heartbeat": datetime.utcnow().isoformat()
        }
        logger.info(f"Agent registered: {agent_id}")
    
    def get_app(self) -> FastAPI:
        """Get FastAPI application"""
        return self.app
    
    def run(self, workers: int = 1) -> None:
        """Run the server"""
        import uvicorn
        
        logger.info(
            f"Starting MCP Server",
            extra={
                "host": self.host,
                "port": self.port,
                "workers": workers
            }
        )
        
        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            workers=workers,
            log_level=self.config.log_level.lower(),
            access_log=True
        )


# Import for module usage
import asyncio

# Create global server instance
mcp_server = ProductionMCPServer(
    host=get_app_config().mcp_server_host,
    port=get_app_config().mcp_server_port
)

app = mcp_server.get_app()
