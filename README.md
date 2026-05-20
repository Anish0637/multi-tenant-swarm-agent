# Multi-Tenant Swarm Agent Platform

Production-grade multi-tenant agent orchestration system with comprehensive access control (RBAC/ABAC/CBAC), MCP server integration, and AWS EC2/ECR deployment.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│           Supervisor Agent (Orchestrator)               │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  HR Agent    │  │ Finance Agent│  │ Medical Agent│  │
│  │  (Tenant A)  │  │  (Tenant B)  │  │  (Tenant C)  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
├─────────────────────────────────────────────────────────┤
│  MCP Server (Tool Registry & Discovery)                 │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │RBAC/ABAC/   │  │ Registry │  │ Access Control   │   │
│  │CBAC Layer   │  │ Service  │  │ Enforcement      │   │
│  └─────────────┘  └──────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────┘
         ↓
    AWS Infrastructure
    ├── EC2 (t3.medium)
    ├── ECR (Container Registry)
    └── CloudWatch (Monitoring)
```

## 📋 Components

### Agents
- **Supervisor Agent**: Orchestrates task distribution, monitoring, and failover
- **HR Agent**: Handles HR-specific tasks, policies, and workflows
- **Finance Agent**: Manages financial operations, compliance, and reporting
- **Medical Agent**: Processes medical data with strict compliance (HIPAA)

### MCP Server
- Tool registration and discovery
- Agent lifecycle management
- Health checks and metrics
- Request/response marshalling

### Access Control
- **RBAC**: Role-based policies (Admin, Manager, User)
- **ABAC**: Attribute-based rules (Tenant, Department, Clearance)
- **CBAC**: Context-based enforcement (Time, Location, Device)

### Registry & Discovery
- Service discovery with health checks
- Agent capability registry
- Load balancing and failover

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- AWS CLI configured
- Terraform 1.5+
- GitHub Actions enabled

### Local Development

```bash
# Clone the repository
git clone https://github.com/Anish0637/multi-tenant-swarm-agent.git
cd multi-tenant-swarm-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env

# Run tests
pytest tests/

# Start locally
python -m agents.supervisor
```

### Docker Deployment

```bash
# Build images
docker-compose build

# Run locally
docker-compose up

# Push to ECR
./scripts/push-to-ecr.sh
```

### AWS Deployment

```bash
# Initialize Terraform
cd terraform
terraform init

# Plan deployment
terraform plan -var="region=us-east-1" -var="instance_type=t3.medium"

# Apply
terraform apply

# Deploy via GitHub Actions (automatic on merge to main)
git push origin main
```

## 📁 Project Structure

```
├── agents/                      # Agent implementations
│   ├── supervisor.py           # Orchestrator agent
│   ├── hr_agent.py            # HR-specific agent
│   ├── finance_agent.py        # Finance-specific agent
│   ├── medical_agent.py        # Medical-specific agent
│   └── base_agent.py           # Base agent class
├── mcp_server/                 # MCP server implementation
│   ├── server.py               # Main MCP server
│   ├── tools.py                # Tool definitions
│   └── handlers.py             # Request handlers
├── registry/                   # Service discovery
│   ├── registry.py             # Registry service
│   ├── discovery.py            # Service discovery
│   └── health_check.py         # Health monitoring
├── access_control/             # Access control framework
│   ├── rbac.py                # Role-based access control
│   ├── abac.py                # Attribute-based access control
│   ├── cbac.py                # Context-based access control
│   ├── policies.py             # Policy definitions
│   └── enforcer.py             # Policy enforcement
├── config/                     # Configuration files
│   ├── agent_config.yaml       # Agent configurations
│   ├── access_policies.yaml    # Access policies
│   └── terraform.tfvars        # Terraform variables
├── terraform/                  # Infrastructure as Code
│   ├── main.tf                # Main infrastructure
│   ├── ec2.tf                 # EC2 instances
│   ├── ecr.tf                 # ECR registry
│   ├── iam.tf                 # IAM roles and policies
│   └── variables.tf           # Terraform variables
├── docker/                     # Docker configurations
│   ├── Dockerfile.agent        # Agent container
│   ├── Dockerfile.mcp          # MCP server container
│   └── docker-compose.yml      # Local development
├── .github/workflows/          # GitHub Actions CI/CD
│   ├── build-and-test.yml     # Build and test
│   ├── push-to-ecr.yml        # Push to ECR
│   └── deploy-to-ec2.yml      # Deploy to EC2
├── tests/                      # Test suite
│   ├── test_agents.py          # Agent tests
│   ├── test_access_control.py  # Access control tests
│   ├── test_mcp_server.py      # MCP server tests
│   └── test_registry.py        # Registry tests
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## 🔐 Security Features

- Multi-layer access control (RBAC/ABAC/CBAC)
- Tenant isolation and data partitioning
- Encrypted communication (TLS/mTLS)
- Audit logging for all operations
- IAM-based AWS resource access
- Container security scanning
- Secret management with AWS Secrets Manager

## 📊 Monitoring & Logging

- CloudWatch integration
- Structured logging (JSON format)
- Distributed tracing with X-Ray
- Custom metrics and dashboards
- Alerts for failures and anomalies

## 🔄 CI/CD Pipeline

GitHub Actions automates:
1. **Build**: Unit tests, linting, type checking
2. **Test**: Integration tests with test agents
3. **Push**: Build Docker images, tag with commit SHA
4. **Deploy**: Automatic EC2 deployment on main branch merge

## 📝 Configuration

### Agent Configuration
Edit `config/agent_config.yaml` to configure agents:

```yaml
agents:
  supervisor:
    name: Supervisor Agent
    type: supervisor
    model: gpt-4
  hr:
    name: HR Agent
    type: hr
    tenant: hr_department
  finance:
    name: Finance Agent
    type: finance
    tenant: finance_department
  medical:
    name: Medical Agent
    type: medical
    tenant: medical_department
```

### Access Policies
Edit `config/access_policies.yaml` to define roles and policies.

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=agents --cov=mcp_server --cov=access_control

# Run specific test file
pytest tests/test_agents.py -v
```

## 🚨 Troubleshooting

See [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common issues.

## 📚 Documentation

- [Architecture & Deployment](docs/ARCHITECTURE.md)
- [Access Control Guide](docs/ACCESS_CONTROL.md)
- [MCP Server Documentation](docs/MCP_SERVER.md)
- [Deployment Guide](docs/DEPLOYMENT.md)

## 🤝 Contributing

1. Create feature branch: `git checkout -b feature/your-feature`
2. Make changes and test: `pytest`
3. Commit: `git commit -m "Add feature"`
4. Push: `git push origin feature/your-feature`
5. Create Pull Request

## 📄 License

MIT License - see LICENSE file

## 👨‍💼 Author

Created by Anish Kumar - [GitHub Profile](https://github.com/Anish0637)

---

**Last Updated**: May 2026
