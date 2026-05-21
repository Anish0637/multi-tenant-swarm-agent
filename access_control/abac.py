"""
Attribute-Based Access Control (ABAC) - Attribute-based policies.
"""

import logging
from typing import Any, Dict, List

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Attribute(BaseModel):
    """Attribute definition"""

    name: str
    value: Any
    type: str  # string, integer, boolean, list


class Subject(BaseModel):
    """Subject (user/principal) with attributes"""

    subject_id: str
    attributes: Dict[str, Any]  # e.g., {"department": "HR", "clearance_level": 3}


class Resource(BaseModel):
    """Resource with attributes"""

    resource_id: str
    resource_type: str
    attributes: Dict[str, Any]  # e.g., {"sensitivity": "high", "owner": "finance"}


class ABACRule(BaseModel):
    """ABAC policy rule"""

    rule_id: str
    name: str
    conditions: List[Dict[str, Any]]  # e.g., [{"subject.department": "HR"}, {"resource.owner": "finance"}]
    effect: str  # allow or deny
    priority: int = 0


class ABACEnforcer:
    """
    ABAC enforcer - checks attribute-based policies.
    """

    def __init__(self):
        """Initialize ABAC enforcer"""
        self.rules: Dict[str, ABACRule] = {}
        self.subjects: Dict[str, Subject] = {}
        self.resources: Dict[str, Resource] = {}
        self._initialize_default_rules()

    def _initialize_default_rules(self) -> None:
        """Initialize default ABAC rules"""
        # HR department can access HR resources
        self.add_rule(
            ABACRule(
                rule_id="hr_access_hr_resources",
                name="HR team access to HR resources",
                conditions=[
                    {"subject.department": "HR"},
                    {"resource.resource_type": "hr"},
                ],
                effect="allow",
                priority=10,
            )
        )

        # Finance department can access finance resources
        self.add_rule(
            ABACRule(
                rule_id="finance_access_finance_resources",
                name="Finance team access to finance resources",
                conditions=[
                    {"subject.department": "Finance"},
                    {"resource.resource_type": "finance"},
                ],
                effect="allow",
                priority=10,
            )
        )

        # Medical department can access medical resources (high sensitivity)
        self.add_rule(
            ABACRule(
                rule_id="medical_access_medical_resources",
                name="Medical team access to medical resources",
                conditions=[
                    {"subject.department": "Medical"},
                    {"resource.resource_type": "medical"},
                    {"subject.clearance_level": {">=": 2}},
                ],
                effect="allow",
                priority=10,
            )
        )

        # Deny access to sensitive resources for low clearance
        self.add_rule(
            ABACRule(
                rule_id="deny_low_clearance_sensitive",
                name="Deny low clearance access to sensitive resources",
                conditions=[
                    {"resource.sensitivity": "high"},
                    {"subject.clearance_level": {"<": 2}},
                ],
                effect="deny",
                priority=20,
            )
        )

    def register_subject(self, subject: Subject) -> None:
        """Register a subject"""
        self.subjects[subject.subject_id] = subject
        logger.info(
            f"Subject {subject.subject_id} registered",
            extra={"subject_id": subject.subject_id},
        )

    def register_resource(self, resource: Resource) -> None:
        """Register a resource"""
        self.resources[resource.resource_id] = resource
        logger.info(
            f"Resource {resource.resource_id} registered",
            extra={"resource_id": resource.resource_id},
        )

    def add_rule(self, rule: ABACRule) -> None:
        """Add an ABAC rule"""
        self.rules[rule.rule_id] = rule
        logger.info(f"ABAC rule added: {rule.name}", extra={"rule_id": rule.rule_id})

    def check_permission(self, subject_id: str, resource_id: str, action: str = "access") -> bool:
        """
        Check if subject can access resource based on attributes.

        Args:
            subject_id: Subject ID
            resource_id: Resource ID
            action: Action to perform

        Returns:
            True if permitted, False otherwise
        """
        subject = self.subjects.get(subject_id)
        resource = self.resources.get(resource_id)

        if not subject or not resource:
            logger.warning(
                f"Subject or resource not found",
                extra={"subject_id": subject_id, "resource_id": resource_id},
            )
            return False

        # Evaluate rules in priority order (higher priority first)
        sorted_rules = sorted(self.rules.values(), key=lambda r: r.priority, reverse=True)

        for rule in sorted_rules:
            if self._evaluate_rule(rule, subject, resource):
                allowed = rule.effect == "allow"
                logger.info(
                    f"Permission {'granted' if allowed else 'denied'} by rule {rule.rule_id}",
                    extra={
                        "subject_id": subject_id,
                        "resource_id": resource_id,
                        "rule_id": rule.rule_id,
                        "allowed": allowed,
                    },
                )
                return allowed

        logger.warning(
            f"No matching rules for subject-resource pair",
            extra={"subject_id": subject_id, "resource_id": resource_id},
        )
        return False

    def _evaluate_rule(self, rule: ABACRule, subject: Subject, resource: Resource) -> bool:
        """
        Evaluate if rule conditions match.

        Args:
            rule: Rule to evaluate
            subject: Subject
            resource: Resource

        Returns:
            True if all conditions match
        """
        for condition in rule.conditions:
            if not self._evaluate_condition(condition, subject, resource):
                return False
        return True

    def _evaluate_condition(self, condition: Dict[str, Any], subject: Subject, resource: Resource) -> bool:
        """Evaluate a single condition"""
        for key, value in condition.items():
            if key.startswith("subject."):
                attr_name = key.split(".")[1]
                # Check direct model field first, then attributes dict
                subject_value = getattr(subject, attr_name, None)
                if subject_value is None:
                    subject_value = subject.attributes.get(attr_name)
                if not self._compare_values(subject_value, value):
                    return False
            elif key.startswith("resource."):
                attr_name = key.split(".")[1]
                # Check direct model field first, then attributes dict
                resource_value = getattr(resource, attr_name, None)
                if resource_value is None:
                    resource_value = resource.attributes.get(attr_name)
                if not self._compare_values(resource_value, value):
                    return False
        return True

    def _compare_values(self, actual: Any, expected: Any) -> bool:
        """Compare values with support for operators"""
        if isinstance(expected, dict):
            # Handle comparison operators
            for op, op_value in expected.items():
                if op == ">=":
                    return actual >= op_value
                elif op == "<=":
                    return actual <= op_value
                elif op == ">":
                    return actual > op_value
                elif op == "<":
                    return actual < op_value
                elif op == "!=":
                    return actual != op_value
        else:
            return actual == expected
        return False
