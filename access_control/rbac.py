"""
Role-Based Access Control (RBAC) - Simple role-based permissions.
"""

import logging
from enum import Enum
from typing import Dict, List, Set

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Role(str, Enum):
    """Role enumeration"""

    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    GUEST = "guest"


class Permission(str, Enum):
    """Permission enumeration"""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    MANAGE = "manage"
    EXECUTE = "execute"


class RBACUser(BaseModel):
    """User with role information"""

    user_id: str
    username: str
    role: Role
    tenant_id: str
    active: bool = True


class RBACPolicy(BaseModel):
    """RBAC policy"""

    role: Role
    resource: str  # e.g., "agent", "task", "user"
    permissions: Set[Permission]


class RBACEnforcer:
    """
    RBAC enforcer - checks role-based access.
    """

    def __init__(self):
        """Initialize RBAC enforcer"""
        self.policies: Dict[str, List[RBACPolicy]] = self._initialize_default_policies()
        self.users: Dict[str, RBACUser] = {}

    def _initialize_default_policies(self) -> Dict[str, List[RBACPolicy]]:
        """Initialize default role policies"""
        return {
            Role.ADMIN.value: [
                RBACPolicy(
                    role=Role.ADMIN,
                    resource="agent",
                    permissions={
                        Permission.READ,
                        Permission.WRITE,
                        Permission.DELETE,
                        Permission.MANAGE,
                    },
                ),
                RBACPolicy(
                    role=Role.ADMIN,
                    resource="task",
                    permissions={
                        Permission.READ,
                        Permission.WRITE,
                        Permission.DELETE,
                        Permission.EXECUTE,
                    },
                ),
                RBACPolicy(
                    role=Role.ADMIN,
                    resource="user",
                    permissions={
                        Permission.READ,
                        Permission.WRITE,
                        Permission.DELETE,
                        Permission.MANAGE,
                    },
                ),
            ],
            Role.MANAGER.value: [
                RBACPolicy(
                    role=Role.MANAGER,
                    resource="agent",
                    permissions={Permission.READ, Permission.EXECUTE},
                ),
                RBACPolicy(
                    role=Role.MANAGER,
                    resource="task",
                    permissions={Permission.READ, Permission.WRITE, Permission.EXECUTE},
                ),
                RBACPolicy(role=Role.MANAGER, resource="user", permissions={Permission.READ}),
            ],
            Role.USER.value: [
                RBACPolicy(role=Role.USER, resource="agent", permissions={Permission.READ}),
                RBACPolicy(
                    role=Role.USER,
                    resource="task",
                    permissions={Permission.READ, Permission.EXECUTE},
                ),
            ],
            Role.GUEST.value: [
                RBACPolicy(role=Role.GUEST, resource="agent", permissions={Permission.READ}),
            ],
        }

    def register_user(self, user: RBACUser) -> None:
        """Register a user"""
        self.users[user.user_id] = user
        logger.info(
            f"User {user.username} registered with role {user.role}",
            extra={"user_id": user.user_id, "role": user.role.value},
        )

    def check_permission(self, user_id: str, resource: str, permission: Permission) -> bool:
        """
        Check if user has permission for resource.

        Args:
            user_id: User ID
            resource: Resource name
            permission: Permission to check

        Returns:
            True if permitted, False otherwise
        """
        user = self.users.get(user_id)
        if not user:
            logger.warning(f"User {user_id} not found")
            return False

        if not user.active:
            logger.warning(f"User {user_id} is inactive")
            return False

        policies = self.policies.get(user.role.value, [])
        for policy in policies:
            if policy.resource == resource and permission in policy.permissions:
                logger.info(
                    f"Permission granted",
                    extra={
                        "user_id": user_id,
                        "resource": resource,
                        "permission": permission.value,
                    },
                )
                return True

        logger.warning(
            f"Permission denied",
            extra={
                "user_id": user_id,
                "resource": resource,
                "permission": permission.value,
                "role": user.role.value,
            },
        )
        return False
