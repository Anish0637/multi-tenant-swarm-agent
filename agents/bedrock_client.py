"""
AWS Bedrock client — LLM inference (Claude) + Knowledge Base RAG.

Env vars
--------
BEDROCK_REGION      default us-east-1
BEDROCK_MODEL_ID    default anthropic.claude-3-5-haiku-20241022-v1:0
BEDROCK_KB_ID       optional — set to enable Knowledge Base RAG
BEDROCK_KB_MODEL_ARN optional — full model ARN for KB retrieve-and-generate
"""

import json
import logging
import os
import re
from typing import Dict, Iterator, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "us.amazon.nova-2-lite-v1:0"
_DEFAULT_REGION = "us-east-1"


class BedrockClient:
    """
    Thin wrapper around boto3 Bedrock runtime clients.

    Provides:
    - invoke()                  — single-turn LLM call (Claude Messages API)
    - retrieve_context()        — semantic search against a Bedrock Knowledge Base
    - retrieve_and_generate()   — fully managed RAG via Bedrock KB
    """

    def __init__(
        self,
        region: Optional[str] = None,
        model_id: Optional[str] = None,
        kb_id: Optional[str] = None,
    ):
        self.region = region or os.getenv("BEDROCK_REGION", _DEFAULT_REGION)
        self.model_id = model_id or os.getenv("BEDROCK_MODEL_ID", _DEFAULT_MODEL)
        self.kb_id = kb_id or os.getenv("BEDROCK_KB_ID")

        self._runtime = boto3.client("bedrock-runtime", region_name=self.region)
        self._agent_runtime = boto3.client("bedrock-agent-runtime", region_name=self.region)

    # ── LLM inference ────────────────────────────────────────────────────────

    def invoke(
        self,
        user: str,
        system: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> str:
        """
        Single-turn invocation via the Bedrock Converse API.

        The Converse API is model-agnostic (Anthropic, Amazon, Meta, etc.)
        and is the recommended approach for new applications.

        Returns the assistant's text content.
        Raises on Bedrock / network errors after logging.
        """
        messages = [{"role": "user", "content": [{"text": user}]}]
        kwargs: dict = {
            "modelId": self.model_id,
            "messages": messages,
            "inferenceConfig": {
                "maxTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system:
            kwargs["system"] = [{"text": system}]

        try:
            response = self._runtime.converse(**kwargs)
            return response["output"]["message"]["content"][0]["text"]
        except ClientError as exc:
            logger.error("Bedrock converse failed: %s", exc)
            raise

    def invoke_json(
        self,
        user: str,
        system: str = "",
        max_tokens: int = 1024,
    ) -> dict:        """
        Like invoke() but parses the first JSON object from the response.
        Returns an empty dict on parse failure.
        """
        raw = self.invoke(user=user, system=system, max_tokens=max_tokens)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        logger.warning("invoke_json: could not parse JSON from response: %s", raw[:200])
        return {}

    # ── Knowledge Base RAG ───────────────────────────────────────────────────

    def retrieve_context(self, query: str, n_results: int = 3) -> List[str]:
        """
        Semantic search against the configured Bedrock Knowledge Base.
        Returns a list of relevant text chunks.
        Returns [] when BEDROCK_KB_ID is not set.
        """
        if not self.kb_id:
            return []
        try:
            response = self._agent_runtime.retrieve(
                knowledgeBaseId=self.kb_id,
                retrievalQuery={"text": query},
                retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": n_results}},
            )
            return [r["content"]["text"] for r in response.get("retrievalResults", [])]
        except ClientError as exc:
            logger.warning("KB retrieve failed (kb_id=%s): %s", self.kb_id, exc)
            return []

    def retrieve_and_generate(self, query: str) -> str:
        """
        Fully managed RAG: retrieve from KB + generate response with Bedrock.
        Returns empty string when BEDROCK_KB_ID is not set.
        """
        if not self.kb_id:
            return ""
        model_arn = os.getenv(
            "BEDROCK_KB_MODEL_ARN",
            f"arn:aws:bedrock:{self.region}::foundation-model/{self.model_id}",
        )
        try:
            response = self._agent_runtime.retrieve_and_generate(
                input={"text": query},
                retrieveAndGenerateConfiguration={
                    "type": "KNOWLEDGE_BASE",
                    "knowledgeBaseConfiguration": {
                        "knowledgeBaseId": self.kb_id,
                        "modelArn": model_arn,
                    },
                },
            )
            return response["output"]["text"]
        except ClientError as exc:
            logger.warning("KB retrieve_and_generate failed: %s", exc)
            return ""

    # ── Multi-turn & streaming ────────────────────────────────────────────────

    def invoke_with_history(
        self,
        history: List[Dict[str, str]],
        user: str,
        system: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> str:
        """
        Multi-turn invocation via Bedrock Converse API.

        history: list of {role: "user"|"assistant", content: "<text>"}
        The current user turn is appended automatically.
        Returns the assistant reply text.
        """
        messages = [
            {"role": m["role"], "content": [{"text": m["content"]}]}
            for m in history
        ]
        messages.append({"role": "user", "content": [{"text": user}]})
        kwargs: dict = {
            "modelId": self.model_id,
            "messages": messages,
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
        }
        if system:
            kwargs["system"] = [{"text": system}]
        try:
            response = self._runtime.converse(**kwargs)
            return response["output"]["message"]["content"][0]["text"]
        except ClientError as exc:
            logger.error("Bedrock converse_with_history failed: %s", exc)
            raise

    def invoke_stream_with_history(
        self,
        history: List[Dict[str, str]],
        user: str,
        system: str = "",
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        """
        Streaming multi-turn invocation via Bedrock ConverseStream API.
        Yields text chunks as they arrive from the model.
        """
        messages = [
            {"role": m["role"], "content": [{"text": m["content"]}]}
            for m in history
        ]
        messages.append({"role": "user", "content": [{"text": user}]})
        kwargs: dict = {
            "modelId": self.model_id,
            "messages": messages,
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0.0},
        }
        if system:
            kwargs["system"] = [{"text": system}]
        try:
            response = self._runtime.converse_stream(**kwargs)
            for event in response.get("stream", []):
                if "contentBlockDelta" in event:
                    delta = event["contentBlockDelta"].get("delta", {})
                    if "text" in delta:
                        yield delta["text"]
        except ClientError as exc:
            logger.error("Bedrock converse_stream failed: %s", exc)
            raise


# Module-level singleton — created lazily on first use
_client: Optional[BedrockClient] = None


def get_bedrock_client() -> BedrockClient:
    """Return the module-level BedrockClient singleton."""
    global _client
    if _client is None:
        _client = BedrockClient()
    return _client
