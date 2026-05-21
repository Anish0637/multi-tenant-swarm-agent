"""
Integration tests for api/public_api.py.
Tests HTTP routes, authentication, rate limiting, validation, and task lifecycle.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


# Patch out config-level side-effects before importing the app module
def _make_app_client():
    """
    Import the public API app with ephemeral dev keys so the module-level
    key-generation code doesn't raise in test context.
    """
    import importlib
    import sys
    import os

    os.environ.setdefault("ENV", "development")
    os.environ.setdefault("API_KEYS", "test-api-key-1234")
    os.environ.setdefault("MCP_INTERNAL_API_KEY", "test-internal-key")

    # Force reimport so module-level code picks up env vars
    if "api.public_api" in sys.modules:
        del sys.modules["api.public_api"]

    import api.public_api as api_module
    return TestClient(api_module.app), api_module


@pytest.fixture(scope="module")
def client_module():
    c, mod = _make_app_client()
    return c, mod


@pytest.fixture(scope="module")
def client(client_module):
    return client_module[0]


VALID_KEY = "test-api-key-1234"


# ──────────────────────────────────────────────────────────────────────────────
# /api/health (no auth required)
# ──────────────────────────────────────────────────────────────────────────────


def test_health_no_auth_required(client):
    with patch("httpx.AsyncClient") as _:
        # health tries to contact MCP server — mock it away
        import httpx
        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_ctx = AsyncMock()
            mock_ctx.get = AsyncMock(return_value=mock_resp)
            mock_enter.return_value = mock_ctx

            resp = client.get("/api/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert "timestamp" in body


# ──────────────────────────────────────────────────────────────────────────────
# /api/agents
# ──────────────────────────────────────────────────────────────────────────────


def test_agents_requires_auth(client):
    resp = client.get("/api/agents")
    assert resp.status_code == 403


def test_agents_with_valid_key(client):
    resp = client.get("/api/agents", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 200
    agents = resp.json()
    assert isinstance(agents, list)
    assert len(agents) == 4
    types = {a["type"] for a in agents}
    assert types == {"hr", "finance", "medical", "supervisor"}


def test_agents_with_invalid_key(client):
    resp = client.get("/api/agents", headers={"X-API-Key": "bad-key"})
    assert resp.status_code == 403


# ──────────────────────────────────────────────────────────────────────────────
# /api/tasks POST — validation
# ──────────────────────────────────────────────────────────────────────────────


def test_submit_task_requires_auth(client):
    resp = client.post(
        "/api/tasks",
        json={
            "agent_type": "hr",
            "task_type": "process_leave",
            "tenant_id": "acme",
            "payload": {},
        },
    )
    assert resp.status_code == 403


def test_submit_task_invalid_agent_type(client):
    resp = client.post(
        "/api/tasks",
        json={
            "agent_type": "unknown",
            "task_type": "process_leave",
            "tenant_id": "acme",
            "payload": {},
        },
        headers={"X-API-Key": VALID_KEY},
    )
    assert resp.status_code == 422


def test_submit_task_tenant_too_short(client):
    resp = client.post(
        "/api/tasks",
        json={
            "agent_type": "hr",
            "task_type": "process_leave",
            "tenant_id": "ab",  # < 3 chars
            "payload": {},
        },
        headers={"X-API-Key": VALID_KEY},
    )
    assert resp.status_code == 422


def test_submit_task_non_alphanumeric_tenant(client):
    resp = client.post(
        "/api/tasks",
        json={
            "agent_type": "hr",
            "task_type": "process_leave",
            "tenant_id": "bad-tenant!",
            "payload": {},
        },
        headers={"X-API-Key": VALID_KEY},
    )
    assert resp.status_code == 422


def test_submit_task_priority_out_of_range(client):
    resp = client.post(
        "/api/tasks",
        json={
            "agent_type": "hr",
            "task_type": "process_leave",
            "tenant_id": "acme",
            "payload": {},
            "priority": 11,  # max is 10
        },
        headers={"X-API-Key": VALID_KEY},
    )
    assert resp.status_code == 422


def test_submit_task_accepted(client):
    """Valid task submission should return 202 with a task_id."""
    with patch("api.public_api._dispatch_to_mcp", new=AsyncMock()):
        resp = client.post(
            "/api/tasks",
            json={
                "agent_type": "hr",
                "task_type": "process_leave",
                "tenant_id": "acme",
                "payload": {"employee_id": "E01"},
            },
            headers={"X-API-Key": VALID_KEY},
        )

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "accepted"
    assert "task_id" in body
    assert "poll_url" in body


# ──────────────────────────────────────────────────────────────────────────────
# /api/tasks/{id} GET — poll
# ──────────────────────────────────────────────────────────────────────────────


def test_poll_task_not_found(client):
    resp = client.get(
        "/api/tasks/00000000-0000-0000-0000-000000000000",
        headers={"X-API-Key": VALID_KEY},
    )
    assert resp.status_code == 404


def test_poll_task_found_after_submit(client):
    """Submit a task then immediately poll — status should be accepted or processing."""
    with patch("api.public_api._dispatch_to_mcp", new=AsyncMock()):
        submit_resp = client.post(
            "/api/tasks",
            json={
                "agent_type": "finance",
                "task_type": "generate_report",
                "tenant_id": "acme",
                "payload": {},
            },
            headers={"X-API-Key": VALID_KEY},
        )

    assert submit_resp.status_code == 202
    task_id = submit_resp.json()["task_id"]

    poll_resp = client.get(
        f"/api/tasks/{task_id}",
        headers={"X-API-Key": VALID_KEY},
    )
    assert poll_resp.status_code == 200
    body = poll_resp.json()
    assert body["task_id"] == task_id
    assert body["status"] in ("accepted", "processing", "completed", "failed")


# ──────────────────────────────────────────────────────────────────────────────
# Rate limiting
# ──────────────────────────────────────────────────────────────────────────────


def test_rate_limiter_blocks_after_limit():
    """TenantRateLimiter should block requests beyond the limit."""
    from api.public_api import TenantRateLimiter

    limiter = TenantRateLimiter(limit=3, window=60)
    tenant = "test-tenant"

    assert limiter.is_allowed(tenant) is True
    assert limiter.is_allowed(tenant) is True
    assert limiter.is_allowed(tenant) is True
    # 4th request should be blocked
    assert limiter.is_allowed(tenant) is False


def test_rate_limiter_different_tenants_independent():
    from api.public_api import TenantRateLimiter

    limiter = TenantRateLimiter(limit=2, window=60)
    assert limiter.is_allowed("tenant_a") is True
    assert limiter.is_allowed("tenant_a") is True
    assert limiter.is_allowed("tenant_a") is False  # blocked

    # tenant_b should still be allowed
    assert limiter.is_allowed("tenant_b") is True
    assert limiter.is_allowed("tenant_b") is True


# ──────────────────────────────────────────────────────────────────────────────
# TaskStore
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_task_store_create_and_get():
    from api.public_api import TaskStore

    store = TaskStore()
    await store.set("task-1", {"status": "accepted", "agent_type": "hr"})
    record = await store.get("task-1")
    assert record is not None
    assert record["status"] == "accepted"


@pytest.mark.asyncio
async def test_task_store_get_missing():
    from api.public_api import TaskStore

    store = TaskStore()
    assert await store.get("does-not-exist") is None


@pytest.mark.asyncio
async def test_task_store_update():
    from api.public_api import TaskStore

    store = TaskStore()
    await store.set("task-2", {"status": "accepted"})
    await store.update("task-2", {"status": "completed", "result": {"ok": True}})
    record = await store.get("task-2")
    assert record["status"] == "completed"
    assert record["result"] == {"ok": True}
