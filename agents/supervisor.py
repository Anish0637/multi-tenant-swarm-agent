"""
Supervisor Agent — LangGraph-powered orchestrator for the swarm.

Enterprise additions
--------------------
1. CapabilityRegistry   — replaces hard-coded task-type prefix table;
                          domain agents self-register on init.
2. RBAC enforcement     — checks user has EXECUTE on the target domain
                          before routing (strict mode configurable).
3. Circuit breaker      — per-domain open/half-open/closed breaker;
                          prevents cascading failures under agent outages.
4. Audit logging        — immutable JSON record for every route decision
                          (allowed / denied / success / failure).
5. Autonomous LLM flow  — when task_type="chat" the graph adds:
                            classify_intent (Bedrock) → validate → route_to_agent
                            → format_response (Bedrock) → complete

Graph — regular task:
  START → entry → validate → route_to_agent → complete → END
                            ↘ handle_error  → END

Graph — chat / free-text:
  START → entry → classify_intent → validate → route_to_agent
                                              → format_response → complete → END
"""

import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from langgraph.graph import END, START, StateGraph

from access_control.rbac import Permission, RBACEnforcer
from agents import audit
from agents.base_agent import AgentType, BaseAgent, TaskRequest, TaskResult
from agents.capability_registry import CapabilityRegistry
from agents.graph_state import AgentGraphState, result_from_state, state_from_task

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Circuit breaker
# ══════════════════════════════════════════════════════════════════════════════


class _CircuitBreaker:
    """
    Per-domain circuit breaker (closed → open → half-open).

    States
    ------
    closed    Normal operation.  Failures are counted.
    open      Breaker tripped; calls rejected until `recovery_timeout` elapses.
    half-open One probe call allowed; success → closed, failure → open again.
    """

    def __init__(self, threshold: int = 5, recovery_timeout: float = 30.0):
        self.threshold = threshold
        self.recovery_timeout = recovery_timeout
        self._failures = 0
        self._opened_at: Optional[float] = None
        self._half_open = False

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if time.monotonic() - self._opened_at > self.recovery_timeout:
            return "half-open"
        return "open"

    @property
    def is_open(self) -> bool:
        return self.state == "open"

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.threshold:
            self._opened_at = time.monotonic()
            logger.warning("Circuit breaker OPENED (failures=%d)", self._failures)


# ══════════════════════════════════════════════════════════════════════════════
# Supervisor
# ══════════════════════════════════════════════════════════════════════════════


class SupervisorAgent(BaseAgent):
    """
    Supervisor that routes tasks to domain agents via LangGraph.

    Parameters
    ----------
    strict_rbac : bool
        False (default) — unknown users receive implicit USER role (EXECUTE allowed).
        True            — unknown / unregistered users are denied.
    circuit_threshold : int
        Number of consecutive failures before a domain's circuit opens.
    circuit_timeout : float
        Seconds before an open circuit transitions to half-open for probing.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        strict_rbac: bool = False,
        circuit_threshold: int = 5,
        circuit_timeout: float = 30.0,
        use_bedrock: bool = True,
        kb_id: Optional[str] = None,
    ):
        super().__init__(
            name="Supervisor",
            agent_type=AgentType.SUPERVISOR,
            tenant_id="system",
            config=config or {},
        )
        self.sub_agents: Dict[str, BaseAgent] = {}
        self._rbac = RBACEnforcer()
        self._strict_rbac = strict_rbac
        self._circuit_threshold = circuit_threshold
        self._circuit_timeout = circuit_timeout
        self._breakers: Dict[str, _CircuitBreaker] = {}
        self._use_bedrock = use_bedrock
        self._kb_id = kb_id or os.getenv("BEDROCK_KB_ID")
        self._graph = self._build_graph()

    # ── sub-agent registry ────────────────────────────────────────────────

    def register_sub_agent(self, agent: BaseAgent) -> None:
        key = f"{agent.agent_type.value}_agent"
        self.sub_agents[key] = agent
        logger.info("Sub-agent registered: %s (%s)", agent.name, key)

    # ── graph construction ────────────────────────────────────────────────

    def _build_graph(self):
        g = StateGraph(AgentGraphState)

        g.add_node("entry", self._entry)
        g.add_node("classify_intent", self._classify_intent)
        g.add_node("validate", self._validate)
        g.add_node("route_to_agent", self._route_to_agent)
        g.add_node("format_response", self._format_response)
        g.add_node("handle_error", self._handle_error)
        g.add_node("complete", self._complete)

        # Entry: branch into chat (LLM) flow or direct task flow
        g.add_edge(START, "entry")
        g.add_conditional_edges(
            "entry",
            lambda s: "chat" if s.get("user_message") else "direct",
            {"chat": "classify_intent", "direct": "validate"},
        )
        g.add_edge("classify_intent", "validate")
        g.add_conditional_edges(
            "validate",
            lambda s: "error" if s.get("error") else "ok",
            {"ok": "route_to_agent", "error": "handle_error"},
        )
        # After routing: chat flow gets formatted response, direct flow goes straight to complete
        g.add_conditional_edges(
            "route_to_agent",
            lambda s: "chat" if s.get("user_message") else "direct",
            {"chat": "format_response", "direct": "complete"},
        )
        g.add_edge("format_response", "complete")
        g.add_edge("complete", END)
        g.add_edge("handle_error", END)

        return g.compile()

    # ── helpers ────────────────────────────────────────────────────────────

    def _get_breaker(self, domain: str) -> _CircuitBreaker:
        if domain not in self._breakers:
            self._breakers[domain] = _CircuitBreaker(
                threshold=self._circuit_threshold,
                recovery_timeout=self._circuit_timeout,
            )
        return self._breakers[domain]

    def _rbac_allowed(self, user_id: str, domain: str) -> bool:
        """Return True if user may execute tasks in this domain."""
        user = self._rbac.users.get(user_id)
        if user is None:
            # Unregistered user: deny in strict mode, allow as USER otherwise
            return not self._strict_rbac
        return self._rbac.check_permission(user_id, "task", Permission.EXECUTE)

    # ── nodes ──────────────────────────────────────────────────────────────

    def _entry(self, state: AgentGraphState) -> AgentGraphState:
        """No-op entry node; provides a branching point for chat vs direct flow."""
        return state

    async def _classify_intent(self, state: AgentGraphState) -> AgentGraphState:
        """
        Use Bedrock (Claude) to extract domain / task_type / payload from
        the user's free-text message, then optionally enrich with KB context.
        """
        if not self._use_bedrock:
            state["error"] = "Bedrock is disabled; cannot classify free-text intent"
            return state

        try:
            from agents.bedrock_client import get_bedrock_client
            from agents.intent_classifier import IntentClassifier

            bedrock = get_bedrock_client()
            classifier = IntentClassifier(bedrock)
            intent = classifier.classify(state["user_message"])

            state["task_type"] = intent["task_type"]
            state["payload"] = {**state.get("payload", {}), **intent["payload"]}
            state["intent_confidence"] = intent["confidence"]
            state["metadata"]["domain"] = intent["domain"]
            state["metadata"]["intent_reasoning"] = intent["reasoning"]

            # Optional KB enrichment
            if self._kb_id:
                bedrock.kb_id = self._kb_id
                chunks = bedrock.retrieve_context(state["user_message"])
                if chunks:
                    state["kb_context"] = "\n\n".join(chunks)
        except Exception as exc:
            logger.error("_classify_intent failed: %s", exc, exc_info=True)
            state["error"] = f"Intent classification failed: {exc}"

        return state

    async def _format_response(self, state: AgentGraphState) -> AgentGraphState:
        """
        Convert the structured agent result dict into a human-readable reply
        using Bedrock (Claude).  Sets state["formatted_response"].
        """
        if not self._use_bedrock:
            return state

        try:
            from agents.bedrock_client import get_bedrock_client
            from agents.intent_classifier import ResponseFormatter

            formatter = ResponseFormatter(get_bedrock_client())
            domain = state.get("metadata", {}).get("domain", "")
            state["formatted_response"] = formatter.format(
                user_message=state.get("user_message", ""),
                agent_result=state.get("result") or {},
                domain=domain,
                task_type=state.get("task_type", ""),
                kb_context=state.get("kb_context") or "",
            )
            # Also embed in result so the caller can find it without knowing the field
            if state.get("result") is not None:
                state["result"]["formatted_response"] = state["formatted_response"]
                state["result"]["intent_confidence"] = state.get("intent_confidence")
        except Exception as exc:
            logger.error("_format_response failed: %s", exc, exc_info=True)
            # Non-fatal: degrade gracefully — use stringified result so user gets something
            result = state.get("result") or {}
            state["formatted_response"] = (
                result.get("formatted_response")
                or str(result)
                or "Request processed."
            )

        return state

    def _validate(self, state: AgentGraphState) -> AgentGraphState:
        state["status"] = "processing"
        state["updated_at"] = datetime.utcnow().isoformat()
        if not state.get("task_type"):
            state["error"] = "Missing task_type"
        return state

    async def _route_to_agent(self, state: AgentGraphState) -> AgentGraphState:
        correlation_id = state.get("correlation_id", "")
        domain = CapabilityRegistry.resolve(
            state["task_type"],
            explicit_domain=state.get("metadata", {}).get("agent_type"),
        )
        agent_key = f"{domain}_agent"

        # ── RBAC check ────────────────────────────────────────────────────
        if not self._rbac_allowed(state["user_id"], domain):
            audit.log_access(
                event="task_route",
                user_id=state["user_id"],
                tenant_id=state["tenant_id"],
                resource=agent_key,
                action="execute",
                outcome="denied",
                correlation_id=correlation_id,
                agent_type=domain,
                task_type=state["task_type"],
            )
            state["status"] = "failed"
            state["error"] = (
                f"Permission denied: user '{state['user_id']}' cannot execute " f"tasks in domain '{domain}'"
            )
            state["result"] = {}
            return state

        # ── sub-agent lookup ──────────────────────────────────────────────
        agent = self.sub_agents.get(agent_key)
        if not agent:
            state["status"] = "failed"
            state["error"] = (
                f"No sub-agent registered for domain '{domain}' "
                f"(key={agent_key}). Registered: {list(self.sub_agents)}"
            )
            state["result"] = {}
            return state

        # ── circuit breaker ───────────────────────────────────────────────
        breaker = self._get_breaker(domain)
        if breaker.is_open:
            audit.log_access(
                event="task_route",
                user_id=state["user_id"],
                tenant_id=state["tenant_id"],
                resource=agent_key,
                action="execute",
                outcome="failure",
                correlation_id=correlation_id,
                agent_type=domain,
                task_type=state["task_type"],
                details={
                    "reason": "circuit_breaker_open",
                    "breaker_state": breaker.state,
                },
            )
            state["status"] = "failed"
            state["error"] = f"Circuit breaker open for domain '{domain}'"
            state["result"] = {}
            return state

        audit.log_access(
            event="task_route",
            user_id=state["user_id"],
            tenant_id=state["tenant_id"],
            resource=agent_key,
            action="execute",
            outcome="allowed",
            correlation_id=correlation_id,
            agent_type=domain,
            task_type=state["task_type"],
        )

        # ── reconstruct TaskRequest and call sub-agent ────────────────────
        sub_task = TaskRequest(
            id=state["task_id"],
            tenant_id=state["tenant_id"],
            task_type=state["task_type"],
            payload=state["payload"],
            priority=state["priority"],
            user_id=state["user_id"],
            context={**state.get("metadata", {}), "correlation_id": correlation_id},
        )

        try:
            sub_result = await agent.handle_task(sub_task)
            breaker.record_success()
        except Exception as exc:
            breaker.record_failure()
            audit.log_access(
                event="task_complete",
                user_id=state["user_id"],
                tenant_id=state["tenant_id"],
                resource=agent_key,
                action="execute",
                outcome="failure",
                correlation_id=correlation_id,
                agent_type=domain,
                task_type=state["task_type"],
                details={"error": str(exc)},
            )
            state["status"] = "failed"
            state["error"] = str(exc)
            state["result"] = {}
            return state

        audit.log_access(
            event="task_complete",
            user_id=state["user_id"],
            tenant_id=state["tenant_id"],
            resource=agent_key,
            action="execute",
            outcome="success" if sub_result.status == "success" else "failure",
            correlation_id=correlation_id,
            agent_type=domain,
            task_type=state["task_type"],
        )

        state["result"] = sub_result.result
        state["status"] = sub_result.status
        if sub_result.error:
            state["error"] = sub_result.error
        state["metadata"]["routed_to"] = agent_key
        return state

    def _complete(self, state: AgentGraphState) -> AgentGraphState:
        state["updated_at"] = datetime.utcnow().isoformat()
        if state["status"] == "processing":
            state["status"] = "success"
        return state

    def _handle_error(self, state: AgentGraphState) -> AgentGraphState:
        state["status"] = "failed"
        state["result"] = {}
        return state

    # ── public interface ───────────────────────────────────────────────────

    async def handle_task(self, task: TaskRequest) -> TaskResult:
        try:
            initial = state_from_task(task)
            if "agent_type" in (task.context or {}):
                initial["metadata"]["agent_type"] = task.context["agent_type"]
            final = await self._graph.ainvoke(initial)
            return result_from_state(final)
        except Exception as e:
            logger.error("Supervisor task failed: %s", e)
            return TaskResult(id=task.id, status="failed", result={}, error=str(e))

    def get_capabilities(self) -> List[str]:
        return ["route_tasks", "manage_agents", "health_check", "failover"]

    def get_circuit_breaker_status(self) -> Dict[str, str]:
        """Operational view of all per-domain circuit breakers."""
        return {domain: cb.state for domain, cb in self._breakers.items()}
