"""
Public REST API Gateway for Multi-Tenant Swarm Agent System.

This is the externally-accessible API that clients call.
Sits behind the ALB at /api/* and routes tasks to the appropriate agents
via the internal MCP Server.

Endpoints:
  POST /api/tasks          - Submit a task to an agent
  GET  /api/tasks/{id}     - Poll task status / retrieve result
  GET  /api/agents         - List available agents
  GET  /api/health         - Health check
  GET  /docs               - Swagger UI
  GET  /openapi.json       - OpenAPI schema
"""

import asyncio
import collections
import time
import uuid
import httpx
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Depends, Request, Security, BackgroundTasks
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from starlette.status import HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND, HTTP_202_ACCEPTED, HTTP_429_TOO_MANY_REQUESTS

from config.logging_config import get_logger

logger = get_logger("public-api")

# ============================================================
# Settings (read from environment / .env)
# ============================================================

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:9000")
INTERNAL_API_KEY = os.getenv("MCP_INTERNAL_API_KEY", "sk-internal-key")
API_KEYS = set(os.getenv("API_KEYS", "sk-prod-demo-key-12345678").split(","))

# ============================================================
# Pydantic models
# ============================================================

class TaskSubmitRequest(BaseModel):
    """Request body for submitting a task."""
    agent_type: str = Field(
        ...,
        description="Target agent: hr | finance | medical | supervisor",
        pattern="^(hr|finance|medical|supervisor)$"
    )
    task_type: str = Field(..., max_length=100)
    payload: Dict[str, Any] = Field(default_factory=dict)
    tenant_id: str = Field(..., max_length=64)
    priority: int = Field(default=5, ge=1, le=10)

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant(cls, v: str) -> str:
        if not v.isalnum() or len(v) < 3:
            raise ValueError("tenant_id must be alphanumeric and at least 3 chars")
        return v


class TaskSubmitResponse(BaseModel):
    """Returned when a task is accepted."""
    task_id: str
    status: str = "accepted"
    agent_type: str
    submitted_at: str
    poll_url: str


class TaskStatusResponse(BaseModel):
    """Task status / result."""
    task_id: str
    status: str                           # accepted | processing | completed | failed
    agent_type: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    execution_time_ms: Optional[float] = None


class AgentInfo(BaseModel):
    name: str
    type: str
    status: str
    description: str


class HealthResponse(BaseModel):
    status: str
    api_version: str = "1.0.0"
    mcp_server: str
    timestamp: str


# ============================================================
# Task store — Redis-backed with in-memory fallback
# ============================================================

class TaskStore:
    """Async task store.  Uses Redis when REDIS_URL is set; falls back to dict."""

    def __init__(self) -> None:
        self._redis = None
        self._mem: Dict[str, Any] = {}
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis.asyncio as aioredis  # type: ignore
                self._redis = aioredis.from_url(redis_url, decode_responses=True)
                logger.info("TaskStore: Redis backend at %s", redis_url)
            except Exception as exc:  # pragma: no cover
                logger.warning("Redis unavailable, using in-memory store: %s", exc)
        else:
            logger.info("TaskStore: using in-memory backend (no REDIS_URL set)")

    async def set(self, task_id: str, data: Dict[str, Any], ttl: int = 86400) -> None:
        if self._redis:
            import json
            await self._redis.setex(f"task:{task_id}", ttl, json.dumps(data))
        else:
            self._mem[task_id] = data

    async def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        if self._redis:
            import json
            raw = await self._redis.get(f"task:{task_id}")
            return json.loads(raw) if raw else None
        return self._mem.get(task_id)

    async def update(self, task_id: str, updates: Dict[str, Any], ttl: int = 86400) -> None:
        existing = (await self.get(task_id)) or {}
        existing.update(updates)
        await self.set(task_id, existing, ttl=ttl)


task_store = TaskStore()


# ============================================================
# Per-tenant rate limiter (sliding window)
# ============================================================

class TenantRateLimiter:
    """Sliding-window rate limiter keyed by tenant_id."""

    def __init__(self, limit: int = 60, window: int = 60) -> None:
        self._limit  = limit
        self._window = window
        self._buckets: Dict[str, collections.deque] = {}

    def is_allowed(self, tenant_id: str) -> bool:
        now = time.monotonic()
        dq  = self._buckets.setdefault(tenant_id, collections.deque())
        cutoff = now - self._window
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= self._limit:
            return False
        dq.append(now)
        return True


_rate_limiter = TenantRateLimiter(
    limit=int(os.getenv("TENANT_RATE_LIMIT", "60")),
    window=int(os.getenv("TENANT_RATE_WINDOW", "60")),
)


# ============================================================
# Auth
# ============================================================

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key not in API_KEYS:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key. Pass X-API-Key header."
        )
    return api_key


# ============================================================
# FastAPI app
# ============================================================

app = FastAPI(
    title="Multi-Tenant Swarm Agent API",
    description=(
        "Public REST API for submitting tasks to HR, Finance, Medical, and Supervisor agents.\n\n"
        "**Authentication**: Pass your API key in the `X-API-Key` header.\n\n"
        "**Flow**: Submit task → receive task_id → poll status until completed."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ============================================================
# Helper: forward task to MCP Server
# ============================================================

async def _dispatch_to_mcp(
    task_id: str,
    request: TaskSubmitRequest,
    correlation_id: str,
) -> None:
    """Background task: send the job to the MCP server and update task store."""
    await task_store.update(task_id, {"status": "processing"})

    payload = {
        "tool_name": "submit_task",
        "tool_id": task_id,
        "parameters": {
            "agent_type": request.agent_type,
            "task_type": request.task_type,
            "payload": request.payload,
            "tenant_id": request.tenant_id,
            "priority": request.priority,
        },
        "context": {"task_id": task_id, "correlation_id": correlation_id},
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{MCP_SERVER_URL}/tools/execute",
                json=payload,
                headers={
                    "X-API-Key": INTERNAL_API_KEY,
                    "X-Correlation-ID": correlation_id,
                },
            )
            response.raise_for_status()
            data = response.json()

            await task_store.update(task_id, {
                "status": data.get("status", "completed"),
                "result": data.get("result"),
                "completed_at": datetime.utcnow().isoformat(),
                "execution_time_ms": data.get("execution_time_ms"),
            })

    except Exception as exc:
        logger.error("Task dispatch failed: %s", exc, extra={"task_id": task_id})
        await task_store.update(task_id, {
            "status": "failed",
            "error": str(exc),
            "completed_at": datetime.utcnow().isoformat(),
        })


# ============================================================
# Routes
# ============================================================

@app.get("/api/health", response_model=HealthResponse, tags=["System"])
async def health():
    """Health check endpoint (no auth required)."""
    mcp_ok = "unreachable"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{MCP_SERVER_URL}/health")
            mcp_ok = "healthy" if r.status_code == 200 else "degraded"
    except Exception:
        pass

    return HealthResponse(
        status="healthy",
        mcp_server=mcp_ok,
        timestamp=datetime.utcnow().isoformat(),
    )


@app.get("/api/agents", response_model=List[AgentInfo], tags=["Agents"],
         dependencies=[Depends(verify_api_key)])
async def list_agents():
    """List all available agents and their current status."""
    return [
        AgentInfo(name="HR Agent",      type="hr",         status="active",
                  description="Employee management, leave, payroll, performance"),
        AgentInfo(name="Finance Agent", type="finance",    status="active",
                  description="Expenses, budgets, invoices, financial reports"),
        AgentInfo(name="Medical Agent", type="medical",    status="active",
                  description="Appointments, patient records, prescriptions"),
        AgentInfo(name="Supervisor",    type="supervisor", status="active",
                  description="Orchestrates multi-agent workflows"),
    ]


@app.post(
    "/api/tasks",
    response_model=TaskSubmitResponse,
    status_code=HTTP_202_ACCEPTED,
    tags=["Tasks"],
    dependencies=[Depends(verify_api_key)],
)
async def submit_task(
    request: TaskSubmitRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
):
    """
    Submit a task to an agent.

    Returns immediately with a `task_id`. Use `GET /api/tasks/{task_id}` to
    poll for the result.

    **Example body**:
    ```json
    {
      "agent_type": "hr",
      "task_type": "employee_onboarding",
      "tenant_id": "acme",
      "payload": {
        "employee_name": "Jane Doe",
        "department": "Engineering",
        "start_date": "2026-06-01"
      }
    }
    ```
    """
    # ── rate limiting ─────────────────────────────────────────────────────
    if not _rate_limiter.is_allowed(request.tenant_id):
        raise HTTPException(
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded for tenant '{request.tenant_id}'. "
                   f"Max {os.getenv('TENANT_RATE_LIMIT', '60')} requests per minute.",
        )

    # ── correlation ID ────────────────────────────────────────────────────
    correlation_id = (
        http_request.headers.get("X-Correlation-ID")
        or str(uuid.uuid4())
    )

    task_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    await task_store.set(task_id, {
        "task_id": task_id,
        "status": "accepted",
        "agent_type": request.agent_type,
        "task_type": request.task_type,
        "tenant_id": request.tenant_id,
        "correlation_id": correlation_id,
        "created_at": now,
        "result": None,
        "error": None,
        "completed_at": None,
        "execution_time_ms": None,
    })

    background_tasks.add_task(_dispatch_to_mcp, task_id, request, correlation_id)

    logger.info(
        "Task accepted",
        extra={
            "task_id": task_id,
            "agent_type": request.agent_type,
            "tenant_id": request.tenant_id,
            "correlation_id": correlation_id,
        },
    )

    return TaskSubmitResponse(
        task_id=task_id,
        agent_type=request.agent_type,
        submitted_at=now,
        poll_url=f"/api/tasks/{task_id}",
    )


@app.get(
    "/api/tasks/{task_id}",
    response_model=TaskStatusResponse,
    tags=["Tasks"],
    dependencies=[Depends(verify_api_key)],
)
async def get_task_status(task_id: str):
    """
    Poll task status or retrieve the completed result.

    Status values: `accepted` → `processing` → `completed` | `failed`
    """
    task = await task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found")
    return TaskStatusResponse(**task)


# ============================================================
# Entry point (for local dev / Docker)
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.public_api:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        workers=int(os.getenv("WORKERS", "2")),
        log_level="info",
    )
