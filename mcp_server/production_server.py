"""
Production-grade MCP (Model Context Protocol) Server with FastAPI.
Handles tool management, agent routing, and request processing with security & monitoring.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from agents.conversation_store import ConversationStore
from config.logging_config import get_logger
from config.production import get_app_config, get_security_config

try:
    from aws_xray_sdk.core import patch_all, xray_recorder

    XRAY_AVAILABLE = True
except ImportError:
    XRAY_AVAILABLE = False


logger = get_logger("mcp-server")

# ── Valid API keys (parsed from env at startup, not from broken SecurityConfig dict) ──
_raw_keys = os.getenv("API_KEYS", "")
_internal_key = os.getenv("MCP_INTERNAL_API_KEY", "")
_VALID_KEYS: set = {k.strip() for k in _raw_keys.split(",") if k.strip()}
if _internal_key:
    _VALID_KEYS.add(_internal_key)

# ── Module-level conversation store singleton ─────────────────────────────────
_conv_store = ConversationStore()


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

    @field_validator("tool_name", mode="before")
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


class ChatRequest(BaseModel):
    """Free-text chat request that triggers the autonomous LLM flow."""

    message: str = Field(..., min_length=1, max_length=4096)
    tenant_id: str = Field(default="default")
    user_id: str = Field(default="user")
    conversation_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))

    @field_validator("message", mode="before")
    @classmethod
    def sanitise_message(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("message must not be empty")
        return v.strip()


class ChatResponse(BaseModel):
    """Response from the autonomous chat endpoint."""

    response: str
    agent_used: Optional[str] = None
    task_type: Optional[str] = None
    confidence: Optional[float] = None
    status: str
    conversation_id: Optional[str] = None
    correlation_id: Optional[str] = None


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
async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Verify API key against env-var-configured valid keys."""
    security_config = get_security_config()

    if not security_config.api_key_enabled:
        return {"authenticated": True}

    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key required")

    # _VALID_KEYS is empty only when no API_KEYS / MCP_INTERNAL_API_KEY is configured
    # (e.g. local dev without any env vars) — allow in that case to avoid locking out devs
    if _VALID_KEYS and x_api_key not in _VALID_KEYS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

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
                "xray_enabled": XRAY_AVAILABLE,
            },
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
            lifespan=lifespan,
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
        app.add_exception_handler(Exception, self._global_exception_handler)

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
                uptime_seconds=uptime,
            )

        @app.get("/tools")
        async def list_tools(auth: Dict = Depends(verify_api_key)):
            """List all available tools"""
            return {
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "required_permissions": tool.required_permissions,
                    }
                    for tool in self.tools.values()
                ],
                "total": len(self.tools),
            }

        @app.get("/tools/{tool_name}", response_model=ToolSchema)
        async def get_tool_definition(tool_name: str, auth: Dict = Depends(verify_api_key)):
            """Get tool definition"""
            if tool_name not in self.tools:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Tool '{tool_name}' not found",
                )
            return self.tools[tool_name]

        @app.post("/tools/execute", response_model=ToolResponse)
        @limiter.limit("1000/minute")
        async def execute_tool(
            request: Request,
            tool_request: ToolRequest,
            auth: Dict = Depends(verify_api_key),
        ):
            """Execute a tool"""
            start_time = time.time()

            logger.info(
                f"Tool execution requested",
                extra={
                    "tool_name": tool_request.tool_name,
                    "tool_id": tool_request.tool_id,
                    "correlation_id": tool_request.context.get("correlation_id"),
                },
            )

            # Validate tool exists
            if tool_request.tool_name not in self.tools:
                logger.warning(f"Tool not found", extra={"tool_name": tool_request.tool_name})
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Tool '{tool_request.tool_name}' not found",
                )

            # Get handler
            handler = self.tool_handlers.get(tool_request.tool_name)
            if not handler:
                logger.error(f"No handler for tool", extra={"tool_name": tool_request.tool_name})
                return ToolResponse(
                    tool_id=tool_request.tool_id,
                    tool_name=tool_request.tool_name,
                    status="error",
                    result={},
                    error=f"No handler for tool {tool_request.tool_name}",
                    execution_time_ms=(time.time() - start_time) * 1000,
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
                        "execution_time_ms": execution_time,
                    },
                )

                return ToolResponse(
                    tool_id=tool_request.tool_id,
                    tool_name=tool_request.tool_name,
                    status="success",
                    result=result,
                    execution_time_ms=execution_time,
                )

            except asyncio.TimeoutError:
                execution_time = (time.time() - start_time) * 1000
                logger.error(
                    f"Tool execution timeout",
                    extra={
                        "tool_name": tool_request.tool_name,
                        "timeout_seconds": tool_request.request_timeout,
                        "execution_time_ms": execution_time,
                    },
                )
                return ToolResponse(
                    tool_id=tool_request.tool_id,
                    tool_name=tool_request.tool_name,
                    status="timeout",
                    result={},
                    error="Tool execution timeout",
                    execution_time_ms=execution_time,
                )

            except Exception as e:
                execution_time = (time.time() - start_time) * 1000
                logger.error(
                    f"Tool execution failed",
                    extra={
                        "tool_name": tool_request.tool_name,
                        "error": str(e),
                        "execution_time_ms": execution_time,
                    },
                )
                return ToolResponse(
                    tool_id=tool_request.tool_id,
                    tool_name=tool_request.tool_name,
                    status="error",
                    result={},
                    error=str(e),
                    execution_time_ms=execution_time,
                )

        @app.get("/agents")
        async def list_agents(auth: Dict = Depends(verify_api_key)):
            """List all registered agents"""
            return {
                "agents": [{"agent_id": agent_id, "info": info} for agent_id, info in self.agents.items()],
                "total": len(self.agents),
            }

        @app.get("/agents/{agent_id}")
        async def get_agent_status(agent_id: str, auth: Dict = Depends(verify_api_key)):
            """Get agent status"""
            if agent_id not in self.agents:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent '{agent_id}' not found",
                )
            return self.agents[agent_id]

        @app.post("/metrics")
        async def record_metric(metric: Dict[str, Any], auth: Dict = Depends(verify_api_key)):
            """Record custom metric"""
            logger.info("Metric recorded", extra={"metric": metric})
            return {"status": "recorded"}

        @app.post("/chat", response_model=ChatResponse)
        @limiter.limit("60/minute")
        async def chat(
            request: Request,
            chat_request: ChatRequest,
            auth: Dict = Depends(verify_api_key),
        ):
            """
            Autonomous free-text chat endpoint with persistent conversation memory.

            Workflow:
              1. Load prior turns from DynamoDB (ConversationStore)
              2. Wrap message + history in TaskRequest with task_type="chat"
              3. SupervisorAgent._classify_intent() extracts domain/task_type/payload
              4. Domain agent processes the structured request
              5. SupervisorAgent._format_response() generates the natural-language reply
                 using the full conversation history for context
              6. Save both user + assistant turns back to DynamoDB
            """
            from agents.finance_agent import FinanceAgent
            from agents.hr_agent import HRAgent
            from agents.medical_agent import MedicalAgent
            from agents.supervisor import SupervisorAgent
            from agents.base_agent import TaskRequest as TR

            start = time.time()
            conv_id = chat_request.conversation_id or str(uuid.uuid4())

            logger.info(
                "Chat request received",
                extra={
                    "user_id": chat_request.user_id,
                    "conversation_id": conv_id,
                    "correlation_id": chat_request.correlation_id,
                },
            )

            # Load conversation history before processing
            history = _conv_store.load(conv_id)

            try:
                supervisor = SupervisorAgent(
                    use_bedrock=True,
                    kb_id=os.getenv("BEDROCK_KB_ID"),
                )
                supervisor.register_sub_agent(HRAgent(tenant_id=chat_request.tenant_id))
                supervisor.register_sub_agent(FinanceAgent(tenant_id=chat_request.tenant_id))
                supervisor.register_sub_agent(MedicalAgent(tenant_id=chat_request.tenant_id))

                task = TR(
                    tenant_id=chat_request.tenant_id,
                    task_type="chat",
                    payload={},
                    user_id=chat_request.user_id,
                    context={
                        "user_message": chat_request.message,
                        "correlation_id": chat_request.correlation_id,
                        "conversation_history": history,
                    },
                )

                result = await supervisor.handle_task(task)

                if result.result and result.result.get("formatted_response"):
                    formatted = result.result["formatted_response"]
                elif result.result:
                    formatted = str(result.result)
                else:
                    formatted = result.error or "Unable to process your request."

                # Persist both turns to DynamoDB
                _conv_store.append(conv_id, "user", chat_request.message)
                _conv_store.append(
                    conv_id,
                    "assistant",
                    formatted,
                    metadata={
                        "agent_used": result.metadata.get("routed_to"),
                        "task_type": result.metadata.get("domain"),
                    },
                )

                logger.info(
                    "Chat request completed",
                    extra={
                        "status": result.status,
                        "execution_ms": (time.time() - start) * 1000,
                        "agent_used": result.metadata.get("routed_to"),
                        "conversation_id": conv_id,
                    },
                )

                return ChatResponse(
                    response=formatted,
                    agent_used=result.metadata.get("routed_to"),
                    task_type=result.metadata.get("domain"),
                    confidence=result.result.get("intent_confidence") if result.result else None,
                    status=result.status,
                    conversation_id=conv_id,
                    correlation_id=chat_request.correlation_id,
                )

            except Exception as exc:
                logger.error("Chat endpoint error: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Chat processing failed",
                )

        @app.get("/chat/stream")
        @limiter.limit("60/minute")
        async def chat_stream(
            request: Request,
            message: str = Query(..., min_length=1, max_length=4096),
            tenant_id: str = Query(default="default"),
            user_id: str = Query(default="user"),
            conversation_id: Optional[str] = Query(default=None),
            auth: Dict = Depends(verify_api_key),
        ):
            """
            Streaming chat endpoint (SSE).

            Runs the full classify → route → agent pipeline, then streams
            the Bedrock format_response call token-by-token as SSE events.

            Events:
              data: <text chunk>
              data: [DONE]
            """
            from agents.bedrock_client import get_bedrock_client
            from agents.capability_registry import CapabilityRegistry
            from agents.finance_agent import FinanceAgent
            from agents.hr_agent import HRAgent
            from agents.intent_classifier import IntentClassifier, ResponseFormatter, _FORMAT_SYSTEM
            from agents.medical_agent import MedicalAgent
            from agents.supervisor import SupervisorAgent
            from agents.base_agent import TaskRequest as TR

            conv_id = conversation_id or str(uuid.uuid4())
            history = _conv_store.load(conv_id)
            clean_message = message.strip()

            async def event_generator() -> AsyncIterator[str]:
                bedrock = get_bedrock_client()
                classifier = IntentClassifier(bedrock)

                # 1. Classify intent
                intent = classifier.classify(clean_message)
                domain = intent.get("domain", "hr")
                task_type = intent.get("task_type", "employee_data")
                payload = intent.get("payload", {})

                # 2. Route to sub-agent
                supervisor = SupervisorAgent(use_bedrock=False)  # skip double-Bedrock in stream mode
                supervisor.register_sub_agent(HRAgent(tenant_id=tenant_id))
                supervisor.register_sub_agent(FinanceAgent(tenant_id=tenant_id))
                supervisor.register_sub_agent(MedicalAgent(tenant_id=tenant_id))

                task = TR(
                    tenant_id=tenant_id,
                    task_type=task_type,
                    payload=payload,
                    user_id=user_id,
                    context={"agent_type": domain},
                )
                result = await supervisor.handle_task(task)
                agent_result = result.result or {}

                # 3. Stream format_response using Bedrock ConverseStream
                kb_context = ""
                context_block = f"\nRelevant context:\n{kb_context}\n" if kb_context else ""
                user_prompt = (
                    f"Original user request: {clean_message}\n"
                    f"Agent domain: {domain}, task type: {task_type}\n"
                    f"Agent result: {agent_result}{context_block}\n"
                    "Write a helpful response to the user."
                )

                full_response = ""
                try:
                    for chunk in bedrock.invoke_stream_with_history(
                        history=history,
                        user=user_prompt,
                        system=_FORMAT_SYSTEM,
                        max_tokens=512,
                    ):
                        full_response += chunk
                        yield f"data: {json.dumps({'chunk': chunk, 'conversation_id': conv_id})}\n\n"
                except Exception as exc:
                    logger.error("Stream format_response failed: %s", exc)
                    fallback = f"Your {task_type.replace('_', ' ')} request has been processed."
                    full_response = fallback
                    yield f"data: {json.dumps({'chunk': fallback, 'conversation_id': conv_id})}\n\n"

                # 4. Persist turns
                _conv_store.append(conv_id, "user", clean_message)
                _conv_store.append(conv_id, "assistant", full_response)

                yield f"data: {json.dumps({'done': True, 'conversation_id': conv_id})}\n\n"

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Conversation-Id": conv_id},
            )

    async def _global_exception_handler(self, request: Request, exc: Exception):
        """Global exception handler"""
        logger.error(
            f"Unhandled exception",
            extra={
                "path": request.url.path,
                "method": request.method,
                "error": str(exc),
            },
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Internal server error",
                "request_id": request.headers.get("x-request-id", "unknown"),
            },
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
            "last_heartbeat": datetime.utcnow().isoformat(),
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
            extra={"host": self.host, "port": self.port, "workers": workers},
        )

        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            workers=workers,
            log_level=self.config.log_level.lower(),
            access_log=True,
        )


# Import for module usage
import asyncio

# Create global server instance
mcp_server = ProductionMCPServer(host=get_app_config().mcp_server_host, port=get_app_config().mcp_server_port)

app = mcp_server.get_app()
