"""
DynamoDB-backed conversation history for persistent multi-turn chat.

Table schema (auto-created if absent):
  Table name  : swarm-agent-conversations   (env: CONVERSATIONS_TABLE)
  PK          : conversation_id  (String – partition key)
  SK          : turn_index       (String – sort key, zero-padded for ordering)
  Attributes  : role, content, ts (epoch), meta (map), ttl (epoch, 30-day)

Falls back transparently to an in-memory dict when DynamoDB is unavailable
(e.g. local dev without AWS credentials) so the chat still works without infra.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

TABLE_NAME = os.getenv("CONVERSATIONS_TABLE", "swarm-agent-conversations")
MAX_HISTORY = 20  # max turns loaded per conversation (10 user + 10 assistant)


class ConversationStore:
    """
    Persist per-conversation message history in DynamoDB.

    Each conversation turn is stored as a separate item:
      PK  = conversation_id
      SK  = zero-padded turn index (000000, 000001, …)

    Usage
    -----
    store = ConversationStore()
    history = store.load("conv-abc")           # → [{role, content}, ...]
    store.append("conv-abc", "user", "Hello")
    store.append("conv-abc", "assistant", "Hi!")
    """

    def __init__(self) -> None:
        region = os.getenv("AWS_REGION", "us-east-1")
        try:
            ddb = boto3.resource("dynamodb", region_name=region)
            self._table = self._ensure_table(ddb)
            self._available = True
            logger.info("ConversationStore: connected to DynamoDB table '%s'", TABLE_NAME)
        except Exception as exc:
            logger.warning(
                "ConversationStore: DynamoDB unavailable (%s) — using in-memory fallback "
                "(history will not persist across restarts)",
                exc,
            )
            self._table = None
            self._available = False
            self._mem: Dict[str, List[Dict]] = {}

    # ── DynamoDB table bootstrap ──────────────────────────────────────────────

    @staticmethod
    def _ensure_table(ddb):
        """Return the DynamoDB Table, creating it if it doesn't exist."""
        table = ddb.Table(TABLE_NAME)
        try:
            table.load()  # raises ResourceNotFoundException if absent
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ResourceNotFoundException":
                raise
            logger.info("Creating DynamoDB table '%s'…", TABLE_NAME)
            table = ddb.create_table(
                TableName=TABLE_NAME,
                KeySchema=[
                    {"AttributeName": "conversation_id", "KeyType": "HASH"},
                    {"AttributeName": "turn_index", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "conversation_id", "AttributeType": "S"},
                    {"AttributeName": "turn_index", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
                TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"},
            )
            table.wait_until_exists()
            logger.info("DynamoDB table '%s' created", TABLE_NAME)
        return table

    # ── public API ────────────────────────────────────────────────────────────

    def load(self, conversation_id: str) -> List[Dict[str, str]]:
        """Return [{role, content}, ...] ordered oldest→newest, max MAX_HISTORY items."""
        if not self._available:
            return list(self._mem.get(conversation_id, []))[-MAX_HISTORY:]
        try:
            resp = self._table.query(
                KeyConditionExpression=Key("conversation_id").eq(conversation_id),
                ScanIndexForward=True,
                Limit=MAX_HISTORY * 2,
            )
            return [
                {"role": item["role"], "content": item["content"]}
                for item in resp.get("Items", [])
            ]
        except ClientError as exc:
            logger.warning("ConversationStore.load failed (conv=%s): %s", conversation_id, exc)
            return []

    def append(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist one turn. turn_index is auto-incremented."""
        if not self._available:
            turns = self._mem.setdefault(conversation_id, [])
            turns.append({"role": role, "content": content})
            return

        idx = self.turn_count(conversation_id)
        try:
            self._table.put_item(
                Item={
                    "conversation_id": conversation_id,
                    "turn_index": f"{idx:06d}",
                    "role": role,
                    "content": content,
                    "ts": int(time.time()),
                    "meta": metadata or {},
                    "ttl": int(time.time()) + 86400 * 30,
                }
            )
        except ClientError as exc:
            logger.warning("ConversationStore.append failed (conv=%s): %s", conversation_id, exc)

    def turn_count(self, conversation_id: str) -> int:
        """Number of stored turns for this conversation."""
        if not self._available:
            return len(self._mem.get(conversation_id, []))
        try:
            resp = self._table.query(
                KeyConditionExpression=Key("conversation_id").eq(conversation_id),
                Select="COUNT",
            )
            return resp.get("Count", 0)
        except ClientError:
            return 0
