"""
Production-grade agent using LangGraph for stateful workflow management.

When OPENAI_API_KEY (or ANTHROPIC_API_KEY) is set, the agent uses a real LLM
for reasoning.  Without any key the agent falls back to rule-based processing
so that the graph can still run in environments without paid API access.
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

try:
    from langchain_core.tools import BaseTool as Tool
except ImportError:
    Tool = object  # type: ignore[assignment,misc]

from pydantic import BaseModel, Field

from config.logging_config import get_logger

logger = get_logger(__name__)


# ==================== State Management ====================


class AgentState(TypedDict):
    """State schema for agent workflows."""

    task_id: str
    tenant_id: str
    agent_id: str
    task_type: str
    payload: Dict[str, Any]
    priority: int
    user_id: str
    status: str  # pending | processing | completed | failed
    messages: List[Dict[str, str]]
    result: Optional[Dict[str, Any]]
    error: Optional[str]
    created_at: str
    updated_at: str
    execution_time_ms: float
    retry_count: int
    metadata: Dict[str, Any]


class TaskRequest(BaseModel):
    """Task request model (production agent — separate from base_agent.TaskRequest)."""

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    task_type: str
    payload: Dict[str, Any]
    priority: int = Field(default=5, ge=0, le=10)
    user_id: str
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class TaskResult(BaseModel):
    """Task result model."""

    task_id: str
    status: str
    result: Dict[str, Any]
    error: Optional[str] = None
    execution_time_ms: float
    completed_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ==================== LLM helper ====================


def _build_llm(provider: str, model: str):
    """
    Attempt to instantiate an LLM client.
    Returns None (triggers rule-based fallback) if the required key is absent
    or the package is not installed, so the graph still runs without API keys.
    """
    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            logger.warning("OPENAI_API_KEY not set — using rule-based fallback")
            return None
        try:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(model_name=model, temperature=0.7, max_tokens=2048, request_timeout=30)
        except ImportError:
            logger.warning("langchain-openai not installed — using rule-based fallback")
            return None

    if provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            logger.warning("ANTHROPIC_API_KEY not set — using rule-based fallback")
            return None
        try:
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(model=model, temperature=0.7, max_tokens=2048, timeout=30)
        except ImportError:
            logger.warning("langchain-anthropic not installed — using rule-based fallback")
            return None

    raise ValueError(f"Unsupported LLM provider: {provider}")


# ==================== Production Agent ====================


class ProductionAgent:
    """
    Production-grade agent backed by a LangGraph StateGraph.

    Features
    --------
    - Optional LLM reasoning (OpenAI / Anthropic) — degrades gracefully to
      rule-based processing when no API key is available.
    - Tool registry with pluggable LangChain Tools.
    - Structured audit logging on every state transition.
    - Retry logic (up to 3 attempts) in the error-handling node.
    """

    MAX_RETRIES = 3

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        llm_provider: str = "openai",
        model: str = "gpt-4",
        tools: Optional[List[Tool]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.model = model
        self.tools: List[Tool] = tools or []
        self.config = config or {}
        self.logger = get_logger(f"agent.{agent_id}")

        self.llm = _build_llm(llm_provider, model)
        self.workflow = self._build_workflow()

        self.logger.info(
            "Agent initialised",
            extra={
                "agent_id": agent_id,
                "agent_type": agent_type,
                "model": model,
                "tools_count": len(self.tools),
                "llm_available": self.llm is not None,
            },
        )

    # ── workflow ─────────────────────────────────────────────────────────────

    def _build_workflow(self):
        g = StateGraph(AgentState)

        g.add_node("process_task", self._process_task_node)
        g.add_node("reason", self._reason_node)
        g.add_node("execute_tools", self._execute_tools_node)
        g.add_node("complete", self._complete_node)
        g.add_node("handle_error", self._handle_error_node)

        g.add_edge(START, "process_task")
        g.add_edge("process_task", "reason")
        g.add_conditional_edges(
            "reason",
            self._should_use_tools,
            {
                "execute": "execute_tools",
                "complete": "complete",
                "error": "handle_error",
            },
        )
        g.add_edge("execute_tools", "reason")
        g.add_edge("complete", END)
        g.add_conditional_edges(
            "handle_error",
            lambda s: "retry" if s["retry_count"] < self.MAX_RETRIES else "done",
            {"retry": "process_task", "done": END},
        )

        return g.compile()

    # ── nodes ────────────────────────────────────────────────────────────────

    async def _process_task_node(self, state: AgentState) -> AgentState:
        self.logger.info(
            "Processing task",
            extra={
                "task_id": state["task_id"],
                "task_type": state["task_type"],
                "tenant_id": state["tenant_id"],
            },
        )
        state["status"] = "processing"
        state["updated_at"] = datetime.utcnow().isoformat()
        state["messages"] = [
            {
                "role": "system",
                "content": f"You are a {self.agent_type} agent. Task: {state['task_type']}",
            },
            {"role": "user", "content": json.dumps(state["payload"])},
        ]
        return state

    async def _reason_node(self, state: AgentState) -> AgentState:
        if state["status"] in ("failed",):
            return state

        if self.llm is None:
            # Rule-based fallback: synthesise a result directly from the payload
            state["result"] = {
                "response": f"[rule-based] processed {state['task_type']}",
                "payload_echo": state["payload"],
            }
            state["messages"].append({"role": "assistant", "content": json.dumps(state["result"])})
            return state

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            lc_msgs = [
                (SystemMessage(content=m["content"]) if m["role"] == "system" else HumanMessage(content=m["content"]))
                for m in state["messages"]
                if m["role"] in ("system", "user")
            ]
            response = await self.llm.ainvoke(lc_msgs)
            state["messages"].append({"role": "assistant", "content": response.content or ""})
        except Exception as e:
            self.logger.error("Reasoning failed: %s", e)
            state["status"] = "failed"
            state["error"] = str(e)

        return state

    def _should_use_tools(self, state: AgentState) -> str:
        if state["status"] == "failed":
            return "error"
        if self.tools and "tool" in str(state["messages"][-1].get("content", "") if state["messages"] else "").lower():
            return "execute"
        return "complete"

    async def _execute_tools_node(self, state: AgentState) -> AgentState:
        if not self.tools:
            return state
        last = state["messages"][-1] if state["messages"] else {}
        # Execute the first matching tool by name if present in the message
        for tool in self.tools:
            if tool.name.lower() in last.get("content", "").lower():
                try:
                    tool_result = await tool.arun(last["content"])
                    state["messages"].append({"role": "tool", "content": str(tool_result)})
                except Exception as e:
                    self.logger.error("Tool %s failed: %s", tool.name, e)
                    state["error"] = str(e)
                    state["status"] = "failed"
                break
        return state

    async def _complete_node(self, state: AgentState) -> AgentState:
        state["status"] = "completed"
        state["updated_at"] = datetime.utcnow().isoformat()
        if state["result"] is None and state["messages"]:
            state["result"] = {
                "response": state["messages"][-1].get("content", ""),
                "messages_count": len(state["messages"]),
            }
        self.logger.info(
            "Task completed",
            extra={
                "task_id": state["task_id"],
                "status": "completed",
            },
        )
        return state

    async def _handle_error_node(self, state: AgentState) -> AgentState:
        state["retry_count"] += 1
        if state["retry_count"] < self.MAX_RETRIES:
            self.logger.warning(
                "Retrying task (attempt %d)",
                state["retry_count"],
                extra={"task_id": state["task_id"]},
            )
            state["status"] = "pending"
            state["error"] = None
        else:
            state["status"] = "failed"
        return state

    # ── public interface ─────────────────────────────────────────────────────

    async def execute(self, task: TaskRequest) -> TaskResult:
        start = time.time()
        initial: AgentState = {
            "task_id": task.task_id,
            "tenant_id": task.tenant_id,
            "agent_id": self.agent_id,
            "task_type": task.task_type,
            "payload": task.payload,
            "priority": task.priority,
            "user_id": task.user_id,
            "status": "pending",
            "messages": [],
            "result": None,
            "error": None,
            "created_at": task.created_at,
            "updated_at": datetime.utcnow().isoformat(),
            "execution_time_ms": 0.0,
            "retry_count": 0,
            "metadata": {},
        }
        try:
            final = await self.workflow.ainvoke(initial)
            elapsed = (time.time() - start) * 1000
            return TaskResult(
                task_id=final["task_id"],
                status=final["status"],
                result=final["result"] or {},
                error=final.get("error"),
                execution_time_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            self.logger.error(
                "Task execution failed",
                extra={
                    "task_id": task.task_id,
                    "error": str(e),
                },
            )
            return TaskResult(
                task_id=task.task_id,
                status="failed",
                result={},
                error=str(e),
                execution_time_ms=elapsed,
            )

    def add_tool(self, tool: Tool) -> None:
        self.tools.append(tool)
        self.logger.debug("Tool added: %s", tool.name)

    def get_tools(self) -> List[Tool]:
        return self.tools

    def get_status(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "model": self.model,
            "tools_count": len(self.tools),
            "llm_available": self.llm is not None,
            "status": "healthy",
        }
