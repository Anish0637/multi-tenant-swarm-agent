"""
Context-Based Access Control (CBAC) - Context-aware policies.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


logger = logging.getLogger(__name__)


class Context(BaseModel):
    """Request context"""
    timestamp: datetime
    source_ip: str
    location: str  # e.g., "office", "remote", "datacenter"
    device_type: str  # e.g., "desktop", "mobile", "tablet"
    network: str  # e.g., "corporate", "public", "vpn"
    time_zone: str


class CBACRule(BaseModel):
    """CBAC policy rule"""
    rule_id: str
    name: str
    context_conditions: Dict[str, Any]
    effect: str  # allow or deny
    priority: int = 0


class CBACEnforcer:
    """
    CBAC enforcer - checks context-based policies.
    """
    
    def __init__(self):
        """Initialize CBAC enforcer"""
        self.rules: Dict[str, CBACRule] = {}
        self._initialize_default_rules()
    
    def _initialize_default_rules(self) -> None:
        """Initialize default CBAC rules"""
        # Allow access during business hours from office network
        self.add_rule(
            CBACRule(
                rule_id="business_hours_office",
                name="Allow business hours access from office",
                context_conditions={
                    "hour": {">=": 9, "<=": 17},
                    "network": "corporate",
                    "location": "office",
                },
                effect="allow",
                priority=10
            )
        )
        
        # Allow VPN access during business hours
        self.add_rule(
            CBACRule(
                rule_id="business_hours_vpn",
                name="Allow business hours access via VPN",
                context_conditions={
                    "hour": {">=": 9, "<=": 17},
                    "network": "vpn",
                },
                effect="allow",
                priority=9
            )
        )
        
        # Deny after-hours access from public networks
        self.add_rule(
            CBACRule(
                rule_id="deny_afterhours_public",
                name="Deny after-hours access from public network",
                context_conditions={
                    "hour": {"<": 9, "|": ">": 17},
                    "network": "public",
                },
                effect="deny",
                priority=20
            )
        )
        
        # Deny mobile access to sensitive resources
        self.add_rule(
            CBACRule(
                rule_id="deny_mobile_sensitive",
                name="Deny mobile device access to sensitive resources",
                context_conditions={
                    "device_type": "mobile",
                    "resource_sensitivity": "high",
                },
                effect="deny",
                priority=15
            )
        )
    
    def add_rule(self, rule: CBACRule) -> None:
        """Add a CBAC rule"""
        self.rules[rule.rule_id] = rule
        logger.info(
            f"CBAC rule added: {rule.name}",
            extra={"rule_id": rule.rule_id}
        )
    
    def check_permission(
        self,
        context: Context,
        resource_sensitivity: str = "normal"
    ) -> bool:
        """
        Check if access is permitted based on context.
        
        Args:
            context: Request context
            resource_sensitivity: Resource sensitivity level
            
        Returns:
            True if permitted, False otherwise
        """
        hour = context.timestamp.hour
        day_of_week = context.timestamp.weekday()  # 0=Monday, 6=Sunday
        
        # Evaluate rules in priority order
        sorted_rules = sorted(
            self.rules.values(),
            key=lambda r: r.priority,
            reverse=True
        )
        
        for rule in sorted_rules:
            if self._evaluate_rule(rule, context, hour, day_of_week, resource_sensitivity):
                allowed = rule.effect == "allow"
                logger.info(
                    f"Context-based permission {'granted' if allowed else 'denied'} by rule {rule.rule_id}",
                    extra={
                        "rule_id": rule.rule_id,
                        "source_ip": context.source_ip,
                        "location": context.location,
                        "allowed": allowed
                    }
                )
                return allowed
        
        logger.warning(
            f"No matching context rules",
            extra={"source_ip": context.source_ip}
        )
        return False
    
    def _evaluate_rule(
        self,
        rule: CBACRule,
        context: Context,
        hour: int,
        day_of_week: int,
        resource_sensitivity: str
    ) -> bool:
        """
        Evaluate if rule conditions match.
        
        Args:
            rule: Rule to evaluate
            context: Request context
            hour: Hour of day
            day_of_week: Day of week (0=Monday)
            resource_sensitivity: Resource sensitivity
            
        Returns:
            True if all conditions match
        """
        for key, value in rule.context_conditions.items():
            if key == "hour":
                if not self._compare_values(hour, value):
                    return False
            elif key == "day_of_week":
                if not self._compare_values(day_of_week, value):
                    return False
            elif key == "location":
                if context.location != value:
                    return False
            elif key == "network":
                if context.network != value:
                    return False
            elif key == "device_type":
                if context.device_type != value:
                    return False
            elif key == "resource_sensitivity":
                if resource_sensitivity != value:
                    return False
        return True
    
    def _compare_values(self, actual: Any, expected: Any) -> bool:
        """Compare values with support for operators"""
        if isinstance(expected, dict):
            for op, op_value in expected.items():
                if op == ">=":
                    if not (actual >= op_value):
                        return False
                elif op == "<=":
                    if not (actual <= op_value):
                        return False
                elif op == ">":
                    if not (actual > op_value):
                        return False
                elif op == "<":
                    if not (actual < op_value):
                        return False
                elif op == "!=":
                    if not (actual != op_value):
                        return False
            return True
        else:
            return actual == expected
