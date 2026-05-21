"""
Structured immutable audit log.

Writes JSON-line audit records to a dedicated 'audit' Python logger that is
intentionally separate from the application debug logger.

For HIPAA / SOC2 compliance, route the 'audit' logger to a write-once
CloudWatch log group (e.g. /ecs/swarm-agent/audit) that has a resource policy
preventing deletion.  The log format is JSON Lines so it is directly queryable
via CloudWatch Logs Insights.

Each record is a flat JSON object — no nested structures — to maximise
queryability.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# ── dedicated audit logger (never propagates to root) ───────────────────────

_audit_logger = logging.getLogger("audit")
if not _audit_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _audit_logger.addHandler(_handler)
    _audit_logger.setLevel(logging.INFO)
    _audit_logger.propagate = False   # don't double-log via root


# ── public API ───────────────────────────────────────────────────────────────

def log_access(
    *,
    event: str,
    user_id: str,
    tenant_id: str,
    resource: str,
    action: str,
    outcome: str,                        # "allowed" | "denied" | "success" | "failure"
    correlation_id: str = "",
    agent_type: str = "",
    task_type: str = "",
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Write one immutable audit record.

    Parameters
    ----------
    event         Short label, e.g. "task_submitted", "task_routed", "task_completed"
    user_id       Authenticated user / service identity
    tenant_id     Multi-tenant scope
    resource      What was accessed, e.g. "hr_agent", "task"
    action        What was attempted, e.g. "execute", "read"
    outcome       Result: "allowed" | "denied" | "success" | "failure"
    correlation_id  Propagated from the inbound HTTP X-Correlation-ID header
    agent_type    Domain agent (hr | finance | medical | supervisor)
    task_type     Specific task variant
    details       Arbitrary extra fields (kept flat for CloudWatch queryability)
    """
    record: Dict[str, Any] = {
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "event":          event,
        "user_id":        user_id,
        "tenant_id":      tenant_id,
        "resource":       resource,
        "action":         action,
        "outcome":        outcome,
        "correlation_id": correlation_id,
        "agent_type":     agent_type,
        "task_type":      task_type,
    }
    if details:
        record.update(details)

    _audit_logger.info(json.dumps(record, default=str))
