# Multi-Tenant Swarm Agent Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│              GitHub Actions CI/CD Pipeline                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐    │
│  │Build & Test  │ │Push to ECR   │ │Deploy to EC2     │    │
│  └──────────────┘ └──────────────┘ └──────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│              AWS Infrastructure (us-east-1)                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ VPC (10.0.0.0/16)                                   │   │
│  │ ┌──────────────────────────────────────────────┐   │   │
│  │ │ Public Subnets (2)                           │   │   │
│  │ │ ┌─────────────┐  ┌─────────────┐             │   │   │
│  │ │ │EC2 Instance │  │EC2 Instance │ (t3.medium)│   │   │
│  │ │ │  (8000-8001)│  │  (8000-8001)│             │   │   │
│  │ │ └─────────────┘  └─────────────┘             │   │   │
│  │ └──────────────────────────────────────────────┘   │   │
│  │ ┌──────────────────────────────────────────────┐   │   │
│  │ │ ECR Repositories                             │   │   │
│  │ │ ├── multi-tenant-swarm-agent:latest          │   │   │
│  │ │ └── mcp-server:latest                        │   │   │
│  │ └──────────────────────────────────────────────┘   │   │
│  │ ┌──────────────────────────────────────────────┐   │   │
│  │ │ Security Groups                              │   │   │
│  │ │ ├── Port 8000: MCP Server                    │   │   │
│  │ │ ├── Port 8001: Registry/Agents               │   │   │
│  │ │ └── Port 22: SSH                             │   │   │
│  │ └──────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│           Multi-Tenant Swarm Agent Platform                 │
│                                                               │
│  ┌────────────────────────────────────────────────────┐    │
│  │    Supervisor Agent (Orchestrator)                │    │
│  │  - Task routing                                    │    │
│  │  - Agent lifecycle management                      │    │
│  │  - Health monitoring                               │    │
│  └────────────────────────────────────────────────────┘    │
│                         ↓                                    │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │  HR Agent    │ │Finance Agent │ │Medical Agent │        │
│  │              │ │              │ │              │        │
│  │- Leave       │ │- Invoicing   │ │- Patient     │        │
│  │- Recruitment│ │- Expenses    │ │  Data        │        │
│  │- Payroll    │ │- Budget      │ │- Appt        │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
│                                                               │
│  ┌────────────────────────────────────────────────────┐    │
│  │            MCP Server (Tool Registry)              │    │
│  │  - Tool definitions & discovery                    │    │
│  │  - Request/response marshalling                    │    │
│  │  - Agent lifecycle API                             │    │
│  └────────────────────────────────────────────────────┘    │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Access Control Layer                               │   │
│  │  ┌──────────────┐ ┌──────────┐ ┌───────────────┐   │   │
│  │  │RBAC          │ │ABAC      │ │CBAC           │   │   │
│  │  │(Role-based)  │ │(Attr-    │ │(Context-based)│   │   │
│  │  │              │ │ based)   │ │               │   │   │
│  │  └──────────────┘ └──────────┘ └───────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Service Registry & Discovery                      │    │
│  │  - Agent registration                              │    │
│  │  - Health checks                                   │    │
│  │  - Load balancing                                  │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. Supervisor Agent
- **Role**: Orchestrates task distribution and agent lifecycle
- **Responsibilities**:
  - Routes tasks to appropriate sub-agents
  - Manages agent failover and recovery
  - Monitors system health
  - Handles load balancing

### 2. Tenant-Specific Agents
- **HR Agent**: Handles HR operations (leave, recruitment, payroll)
- **Finance Agent**: Manages financial operations (invoicing, expenses, budgets)
- **Medical Agent**: Processes medical data with HIPAA compliance

### 3. MCP Server
- **Protocol**: Model Context Protocol
- **Features**:
  - Tool registration and discovery
  - Agent lifecycle management
  - Health checks and metrics
  - Request/response handling

### 4. Access Control

#### RBAC (Role-Based Access Control)
- **Roles**: Admin, Manager, User, Guest
- **Permissions**: Read, Write, Delete, Manage, Execute
- **Use Case**: Simple permission model for user roles

#### ABAC (Attribute-Based Access Control)
- **Subject Attributes**: Department, Clearance Level, Job Title
- **Resource Attributes**: Sensitivity, Owner, Type
- **Use Case**: Fine-grained access based on attributes

#### CBAC (Context-Based Access Control)
- **Context Factors**: Time, Location, Device, Network, IP
- **Rules**: Time-based, location-based, device-based restrictions
- **Use Case**: Dynamic access based on request context

### 5. Service Registry
- **Functions**:
  - Agent discovery and registration
  - Health monitoring and heartbeats
  - Capability matching
  - Load balancing

## Data Flow

### Task Submission
```
User Request
    ↓
RBAC Check (Role Permission)
    ↓
ABAC Check (Attribute Match)
    ↓
CBAC Check (Context Validation)
    ↓
MCP Server (Tool Invocation)
    ↓
Supervisor Agent (Routing)
    ↓
Sub-Agent (Task Execution)
    ↓
Task Result → Response
```

## Multi-Tenancy

- **Tenant Isolation**: Each tenant has isolated agents and data
- **Policy Enforcement**: RBAC/ABAC/CBAC per tenant
- **Resource Separation**: Separate configurations and storage
- **Audit Logging**: Per-tenant audit trails

## Deployment Architecture

### Local Development
```bash
docker-compose up
```
- Runs all agents locally
- MCP server on port 8000
- Agent APIs on ports 8001+

### AWS Production
```
EC2 Instances (t3.medium)
    ↓
ECR (Container Registry)
    ↓
Auto-scaling Group (optional)
    ↓
CloudWatch (Monitoring)
    ↓
CloudWatch Logs (Logging)
```

## Security Measures

1. **Network Security**:
   - VPC isolation
   - Security groups
   - NACLs

2. **IAM Security**:
   - EC2 instance roles
   - ECR access policies
   - Secret management

3. **Application Security**:
   - Multi-layer access control
   - HIPAA compliance for medical data
   - Encrypted communications
   - Audit logging

4. **Container Security**:
   - ECR image scanning
   - Non-root execution
   - Minimal base images

## Monitoring & Observability

- **Metrics**: CPU, Memory, Task count
- **Logs**: Structured JSON logs
- **Traces**: X-Ray integration
- **Alerts**: CloudWatch alarms
