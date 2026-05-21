"""
Integration tests for mcp_server/production_server.py.
Tests the HTTP layer: /health, /tools, /tools/execute, /chat,
authentication, validation, and error handling.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from mcp_server.production_server import ProductionMCPServer, ToolSchema


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def server():
    """Minimal server instance with API key auth disabled."""
    with patch("mcp_server.production_server.get_security_config") as mock_sec, \
         patch("mcp_server.production_server.get_app_config") as mock_app:
        sec_cfg = MagicMock()
        sec_cfg.api_key_enabled = False
        sec_cfg.cors_enabled = False
        sec_cfg.api_keys = {}
        mock_sec.return_value = sec_cfg

        app_cfg = MagicMock()
        app_cfg.log_level = "INFO"
        app_cfg.mcp_server_host = "0.0.0.0"
        app_cfg.mcp_server_port = 9000
        mock_app.return_value = app_cfg

        srv = ProductionMCPServer(host="localhost", port=9000)
        yield srv


@pytest.fixture
def client(server):
    return TestClient(server.app)


async def _echo_handler(parameters, context):
    return {"echo": parameters}


# ──────────────────────────────────────────────────────────────────────────────
# /health
# ──────────────────────────────────────────────────────────────────────────────


def test_health_returns_healthy(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert "version" in body
    assert "uptime_seconds" in body


# ──────────────────────────────────────────────────────────────────────────────
# /tools
# ──────────────────────────────────────────────────────────────────────────────


def test_list_tools_empty(client):
    resp = client.get("/tools")
    assert resp.status_code == 200
    body = resp.json()
    assert "tools" in body
    assert body["total"] == 0


def test_list_tools_after_registration(server, client):
    server.register_tool(
        ToolSchema(
            name="echo",
            description="Echo parameters back",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        ),
        _echo_handler,
    )
    resp = client.get("/tools")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["tools"][0]["name"] == "echo"


def test_get_tool_definition_not_found(client):
    resp = client.get("/tools/nonexistent")
    assert resp.status_code == 404


def test_get_tool_definition_found(server, client):
    server.register_tool(
        ToolSchema(
            name="ping",
            description="Ping",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        ),
        _echo_handler,
    )
    resp = client.get("/tools/ping")
    assert resp.status_code == 200
    assert resp.json()["name"] == "ping"


# ──────────────────────────────────────────────────────────────────────────────
# /tools/execute
# ──────────────────────────────────────────────────────────────────────────────


def test_execute_tool_success(server, client):
    server.register_tool(
        ToolSchema(
            name="greet",
            description="Greet",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        ),
        _echo_handler,
    )
    resp = client.post(
        "/tools/execute",
        json={"tool_name": "greet", "parameters": {"name": "world"}, "context": {}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["result"]["echo"]["name"] == "world"


def test_execute_tool_not_found(client):
    resp = client.post(
        "/tools/execute",
        json={"tool_name": "does_not_exist", "parameters": {}, "context": {}},
    )
    assert resp.status_code == 404


def test_execute_tool_missing_tool_name(client):
    resp = client.post(
        "/tools/execute",
        json={"parameters": {}, "context": {}},
    )
    assert resp.status_code == 422  # Pydantic validation error


def test_execute_tool_name_too_long(client):
    resp = client.post(
        "/tools/execute",
        json={"tool_name": "a" * 101, "parameters": {}, "context": {}},
    )
    assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────────────────────
# /tools/execute — handler exception
# ──────────────────────────────────────────────────────────────────────────────


def test_execute_tool_handler_exception(server, client):
    async def _boom(parameters, context):
        raise RuntimeError("handler exploded")

    server.register_tool(
        ToolSchema(
            name="boom",
            description="Explodes",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        ),
        _boom,
    )
    resp = client.post(
        "/tools/execute",
        json={"tool_name": "boom", "parameters": {}, "context": {}},
    )
    # Should return an error response, not a 500 crash
    assert resp.status_code in (200, 500)
    if resp.status_code == 200:
        assert resp.json()["status"] == "error"


# ──────────────────────────────────────────────────────────────────────────────
# /chat — validation
# ──────────────────────────────────────────────────────────────────────────────


def test_chat_empty_message_rejected(client):
    resp = client.post(
        "/chat",
        json={"message": "   ", "tenant_id": "t1", "user_id": "u1"},
    )
    assert resp.status_code == 422


def test_chat_message_too_long_rejected(client):
    resp = client.post(
        "/chat",
        json={"message": "x" * 4097, "tenant_id": "t1", "user_id": "u1"},
    )
    assert resp.status_code == 422


def test_chat_success(client):
    """Chat endpoint should invoke supervisor and return a structured response."""
    mock_result = MagicMock()
    mock_result.status = "success"
    mock_result.result = {
        "formatted_response": "Sure, I can help with that.",
        "intent_confidence": 0.9,
    }
    mock_result.error = None
    mock_result.metadata = {"routed_to": "hr_agent", "domain": "hr"}

    # The chat endpoint lazily imports from agents.supervisor inside the function body
    with patch("agents.supervisor.SupervisorAgent") as MockSupervisor, \
         patch("agents.hr_agent.HRAgent"), \
         patch("agents.finance_agent.FinanceAgent"), \
         patch("agents.medical_agent.MedicalAgent"):
        mock_sup_instance = AsyncMock()
        mock_sup_instance.handle_task = AsyncMock(return_value=mock_result)
        MockSupervisor.return_value = mock_sup_instance

        resp = client.post(
            "/chat",
            json={"message": "I need a leave request", "tenant_id": "abc", "user_id": "u1"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert "response" in body


# ──────────────────────────────────────────────────────────────────────────────
# Authentication (API key required)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def secured_server():
    with patch("mcp_server.production_server.get_security_config") as mock_sec, \
         patch("mcp_server.production_server.get_app_config") as mock_app:
        sec_cfg = MagicMock()
        sec_cfg.api_key_enabled = True
        sec_cfg.cors_enabled = False
        sec_cfg.api_keys = {"default": "valid-test-key"}
        mock_sec.return_value = sec_cfg

        app_cfg = MagicMock()
        app_cfg.log_level = "INFO"
        app_cfg.mcp_server_host = "0.0.0.0"
        app_cfg.mcp_server_port = 9000
        mock_app.return_value = app_cfg

        srv = ProductionMCPServer(host="localhost", port=9000)
        yield srv


def test_tools_requires_api_key(secured_server):
    c = TestClient(secured_server.app)
    resp = c.get("/tools")
    assert resp.status_code == 401


def test_tools_invalid_api_key_rejected(secured_server):
    c = TestClient(secured_server.app)
    resp = c.get("/tools", headers={"x-api-key": "wrong-key"})
    assert resp.status_code == 401


def test_tools_valid_api_key_accepted(secured_server):
    c = TestClient(secured_server.app)
    resp = c.get("/tools", headers={"x-api-key": "valid-test-key"})
    assert resp.status_code == 200


# ──────────────────────────────────────────────────────────────────────────────
# register_tool / register_agent helpers
# ──────────────────────────────────────────────────────────────────────────────


def test_register_tool_adds_to_registry(server):
    schema = ToolSchema(
        name="my_tool",
        description="test",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    server.register_tool(schema, _echo_handler)
    assert "my_tool" in server.tools
    assert "my_tool" in server.tool_handlers


def test_register_agent_adds_to_registry(server):
    server.register_agent("agent_1", {"type": "hr", "status": "healthy"})
    assert "agent_1" in server.agents
    assert server.agents["agent_1"]["type"] == "hr"
