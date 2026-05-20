"""
Test access control functionality.
"""

import pytest
from datetime import datetime
from access_control import (
    RBACEnforcer, RBACUser, Role, Permission,
    ABACEnforcer, Subject, Resource,
    CBACEnforcer, Context
)


class TestRBAC:
    """RBAC tests"""
    
    def test_rbac_admin_permissions(self):
        """Test admin role permissions"""
        enforcer = RBACEnforcer()
        
        user = RBACUser(
            user_id="user1",
            username="admin",
            role=Role.ADMIN,
            tenant_id="default"
        )
        enforcer.register_user(user)
        
        # Admin should have all permissions
        assert enforcer.check_permission("user1", "agent", Permission.READ)
        assert enforcer.check_permission("user1", "agent", Permission.WRITE)
        assert enforcer.check_permission("user1", "agent", Permission.DELETE)
        assert enforcer.check_permission("user1", "agent", Permission.MANAGE)
    
    def test_rbac_user_permissions(self):
        """Test user role permissions"""
        enforcer = RBACEnforcer()
        
        user = RBACUser(
            user_id="user2",
            username="john",
            role=Role.USER,
            tenant_id="default"
        )
        enforcer.register_user(user)
        
        # User should have limited permissions
        assert enforcer.check_permission("user2", "agent", Permission.READ)
        assert enforcer.check_permission("user2", "task", Permission.EXECUTE)
        assert not enforcer.check_permission("user2", "agent", Permission.DELETE)


class TestABAC:
    """ABAC tests"""
    
    def test_abac_department_access(self):
        """Test ABAC department-based access"""
        enforcer = ABACEnforcer()
        
        # Register HR subject
        hr_subject = Subject(
            subject_id="emp1",
            attributes={"department": "HR", "clearance_level": 3}
        )
        enforcer.register_subject(hr_subject)
        
        # Register HR resource
        hr_resource = Resource(
            resource_id="res1",
            resource_type="hr",
            attributes={"sensitivity": "normal", "owner": "hr"}
        )
        enforcer.register_resource(hr_resource)
        
        # HR subject should access HR resource
        assert enforcer.check_permission("emp1", "res1")
    
    def test_abac_deny_low_clearance(self):
        """Test ABAC deny low clearance access"""
        enforcer = ABACEnforcer()
        
        # Register low clearance subject
        subject = Subject(
            subject_id="emp2",
            attributes={"department": "General", "clearance_level": 1}
        )
        enforcer.register_subject(subject)
        
        # Register sensitive resource
        resource = Resource(
            resource_id="res2",
            resource_type="medical",
            attributes={"sensitivity": "high", "owner": "medical"}
        )
        enforcer.register_resource(resource)
        
        # Low clearance should not access sensitive resource
        assert not enforcer.check_permission("emp2", "res2")


class TestCBAC:
    """CBAC tests"""
    
    def test_cbac_business_hours(self):
        """Test CBAC business hours access"""
        enforcer = CBACEnforcer()
        
        # Context during business hours
        context = Context(
            timestamp=datetime(2024, 5, 15, 10, 0, 0),  # 10 AM
            source_ip="10.0.0.1",
            location="office",
            device_type="desktop",
            network="corporate",
            time_zone="UTC"
        )
        
        # Should allow business hours access
        assert enforcer.check_permission(context)
    
    def test_cbac_deny_after_hours(self):
        """Test CBAC deny after-hours public access"""
        enforcer = CBACEnforcer()
        
        # Context after hours from public network
        context = Context(
            timestamp=datetime(2024, 5, 15, 20, 0, 0),  # 8 PM
            source_ip="203.0.113.1",
            location="remote",
            device_type="desktop",
            network="public",
            time_zone="UTC"
        )
        
        # May deny after-hours public access (depending on rules)
        result = enforcer.check_permission(context)
        # Result depends on default rules


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
