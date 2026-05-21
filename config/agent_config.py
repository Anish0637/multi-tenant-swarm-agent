"""
Configuration for agents.
"""

agents_config = {
    "supervisor": {
        "name": "Supervisor Agent",
        "type": "supervisor",
        "model": "gpt-4",
        "temperature": 0.7,
        "max_tokens": 2000,
    },
    "hr": {
        "name": "HR Agent",
        "type": "hr",
        "tenant_id": "hr",
        "model": "gpt-4",
        "temperature": 0.5,
        "max_tokens": 1500,
        "capabilities": [
            "process_leave",
            "handle_recruitment",
            "process_payroll",
            "fetch_employee_data",
        ],
    },
    "finance": {
        "name": "Finance Agent",
        "type": "finance",
        "tenant_id": "finance",
        "model": "gpt-4",
        "temperature": 0.3,
        "max_tokens": 1500,
        "capabilities": [
            "create_invoice",
            "process_expense",
            "track_budget",
            "generate_report",
        ],
    },
    "medical": {
        "name": "Medical Agent",
        "type": "medical",
        "tenant_id": "medical",
        "model": "gpt-4",
        "temperature": 0.2,
        "max_tokens": 1500,
        "capabilities": [
            "fetch_patient_data",
            "schedule_appointment",
            "process_prescription",
            "manage_medical_record",
        ],
    },
}

# Registry configuration
registry_config = {
    "heartbeat_timeout": 30,
    "health_check_interval": 10,
}

# MCP Server configuration
mcp_config = {
    "host": "0.0.0.0",
    "port": 8000,
    "debug": False,
    "workers": 4,
}

# Access control configuration
access_control_config = {
    "enable_rbac": True,
    "enable_abac": True,
    "enable_cbac": True,
    "enforce_multi_tenancy": True,
}

# Logging configuration
logging_config = {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": "/var/log/swarm-agent.log",
}
