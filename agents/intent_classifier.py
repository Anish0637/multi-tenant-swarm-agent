"""
LLM-powered intent classifier and response formatter using Bedrock (Claude).

IntentClassifier  — free text → {domain, task_type, payload, confidence}
ResponseFormatter — agent result dict + user message → natural language answer
"""

import logging
from typing import Any, Dict

from agents.bedrock_client import BedrockClient

logger = logging.getLogger(__name__)

# ── Prompts ──────────────────────────────────────────────────────────────────

_INTENT_SYSTEM = """You are an intent classifier for a multi-tenant enterprise AI agent system.

The system has three specialized agents with the following task types:

HR Agent       → employee_data | process_leave | recruitment | payroll
Finance Agent  → invoice | expense | budget | report | audit | payroll
Medical Agent  → patient_data | appointment | prescription | diagnosis | treatment

Given a user message, extract the intent and return ONLY a JSON object:
{
  "domain":     "hr" | "finance" | "medical",
  "task_type":  one of the task types listed above,
  "payload":    { ...key fields extracted from the message... },
  "confidence": 0.0 to 1.0,
  "reasoning":  "one-sentence explanation"
}

Rules:
- payload must only contain fields explicitly mentioned or clearly implied
- Use snake_case for all field names
- If the message is ambiguous, choose the most likely domain and set confidence < 0.7
- Never add extra keys outside the schema above
"""

_FORMAT_SYSTEM = """You are a helpful enterprise AI assistant. A user sent a request,
a specialized agent processed it, and you must return a clear, concise natural-language
response.

Rules:
- Be conversational and professional
- Confirm what was done and any key details from the result
- If there are next steps or status updates, mention them
- Keep the response under 3 sentences unless detail is critical
- Do NOT expose internal JSON keys verbatim; translate them to plain English
- If the agent returned an error, acknowledge it politely and suggest contacting support
"""


class IntentClassifier:
    """
    Classifies a free-text user message into a structured intent that the
    SupervisorAgent can route.
    """

    def __init__(self, bedrock: BedrockClient):
        self._bedrock = bedrock

    def classify(self, message: str) -> Dict[str, Any]:
        """
        Parse *message* and return:
          {domain, task_type, payload, confidence, reasoning}

        Never raises — returns a safe fallback on any error.
        """
        try:
            result = self._bedrock.invoke_json(
                system=_INTENT_SYSTEM,
                user=f"User message: {message}",
                max_tokens=512,
            )
            # Validate required fields; fill defaults on partial response
            domain = result.get("domain", "hr")
            task_type = result.get("task_type", "employee_data")
            payload = result.get("payload") or {}
            confidence = float(result.get("confidence", 0.5))
            reasoning = result.get("reasoning", "")
            logger.info(
                "Intent classified: domain=%s task_type=%s confidence=%.2f",
                domain,
                task_type,
                confidence,
            )
            return {
                "domain": domain,
                "task_type": task_type,
                "payload": payload,
                "confidence": confidence,
                "reasoning": reasoning,
            }
        except Exception as exc:
            logger.error("IntentClassifier.classify failed: %s", exc)
            return {
                "domain": "hr",
                "task_type": "employee_data",
                "payload": {},
                "confidence": 0.0,
                "reasoning": f"classification error: {exc}",
            }


class ResponseFormatter:
    """
    Converts a structured agent result dict into a natural-language reply
    tailored to the original user message.
    """

    def __init__(self, bedrock: BedrockClient):
        self._bedrock = bedrock

    def format(
        self,
        user_message: str,
        agent_result: Dict[str, Any],
        domain: str,
        task_type: str,
        kb_context: str = "",
    ) -> str:
        """
        Return a human-readable response string.
        Never raises — returns a plain-English fallback on any error.
        """
        context_block = f"\nRelevant policy/knowledge context:\n{kb_context}\n" if kb_context else ""
        user_prompt = (
            f"Original user request: {user_message}\n"
            f"Agent domain: {domain}, task type: {task_type}\n"
            f"Agent result: {agent_result}{context_block}\n"
            "Write a helpful response to the user."
        )
        try:
            return self._bedrock.invoke(
                system=_FORMAT_SYSTEM,
                user=user_prompt,
                max_tokens=512,
                temperature=0.3,
            )
        except Exception as exc:
            logger.error("ResponseFormatter.format failed: %s", exc)
            # Graceful degradation — return a plain summary
            status = agent_result.get("status", agent_result.get("action", "processed"))
            return (
                f"Your {task_type.replace('_', ' ')} request has been {status}. "
                "Please check the details below or contact support if you need assistance."
            )
