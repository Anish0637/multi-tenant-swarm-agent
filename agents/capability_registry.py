"""
Self-registering capability registry.

Domain agents call CapabilityRegistry.register() in their __init__ so the
Supervisor can resolve task_type → domain without a hard-coded lookup table.
Adding a new domain agent requires zero changes to the Supervisor.
"""

import logging
from typing import Dict, Iterable, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DOMAIN = "hr"


class CapabilityRegistry:
    """
    Module-level singleton that maps task_type → domain agent name.

    Registration is idempotent; last writer wins for a given task_type.
    Thread-safe for reads (GIL); registrations happen at import time.
    """

    _registry: Dict[str, str] = {}   # task_type (lowercase) → domain

    @classmethod
    def register(cls, domain: str, task_types: Iterable[str]) -> None:
        """Register all task_types for a domain."""
        for tt in task_types:
            cls._registry[tt.lower()] = domain
        logger.debug("Capabilities registered — domain='%s' types=%s",
                     domain, list(task_types))

    @classmethod
    def resolve(cls, task_type: str,
                explicit_domain: Optional[str] = None) -> str:
        """
        Return the domain responsible for task_type.

        Priority
        --------
        1. explicit_domain — from task.context["agent_type"] / state metadata
        2. Exact match in registry
        3. Prefix scan (e.g. "process_leave" matches "process_leave")
        4. _DEFAULT_DOMAIN ("hr") as final fallback
        """
        if explicit_domain in ("hr", "finance", "medical", "supervisor"):
            return explicit_domain

        tt = task_type.lower()

        if tt in cls._registry:
            return cls._registry[tt]

        # Prefix scan — supports compound task types like "hr_leave_annual"
        for registered_tt, domain in cls._registry.items():
            if tt.startswith(registered_tt):
                return domain

        return _DEFAULT_DOMAIN

    @classmethod
    def all_capabilities(cls) -> Dict[str, str]:
        """Return a snapshot of the full registry (task_type → domain)."""
        return dict(cls._registry)

    @classmethod
    def reset(cls) -> None:
        """Clear the registry. Intended for unit tests only."""
        cls._registry.clear()
