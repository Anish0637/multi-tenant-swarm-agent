# AWS Deployment Guide — Multi-Tenant Swarm Agent

## Architecture Overview

```
Internet
   │
   ▼
[Route53]  app.yourdomain.com / api.yourdomain.com
   │
   ▼
[Public ALB]  ──── HTTPS 443 (TLS from ACM)
   │                │
   ├─ /api/*  ──────▼
   │        [ECS Fargate: Public API]   port 8000
   │               │  (forwards to MCP Server)
   ▼               │
[ECS Fargate: Streamlit Webapp]  port 8501
                   │
                   ▼
          [Internal ALB]  port 9000
                   │
                   ▼
        [ECS Fargate: MCP Server]  port 8000
          ┌────────┴──────────┐
          ▼                   ▼
   [HR Agent]          [Finance Agent]
   [Medical Agent]     [Supervisor Agent]
          │
          ▼
   [AWS Services]
   CloudWatch | Secrets Manager | ECR | DynamoDB (optional)
```

## What You Get After Deployment

| URL | What it is |
|-----|-----------|
| `https://app.yourdomain.com` | Streamlit web UI |
| `https://app.yourdomain.com/api/tasks` | REST API — submit tasks |
| `https://app.yourdomain.com/api/agents` | List available agents |
| `https://app.yourdomain.com/docs` | Interactive Swagger UI |
| `https://app.yourdomain.com/api/health` | Health check (no auth) |

---

## Prerequisites

```bash
# Install tools
brew install awscli terraform docker

# Configure AWS credentials
aws configure
# AWS Access Key ID: <your-key>
# AWS Secret Access Key: <your-secret>
# Default region: us-east-1
# Default output: json

# Verify
aws sts get-caller-identity
```

---

## Step 1 — Store Secrets in AWS Secrets Manager

```bash
# Create the secret (run once)
aws secretsmanager create-secret \
  --name "swarm-agent/prod" \
  --secret-string '{
    "OPENAI_API_KEY": "sk-your-openai-key",
    "API_KEYS": "sk-prod-key-1,sk-prod-key-2",
    "MCP_INTERNAL_API_KEY": "sk-internal-only-key"
  }' \
  --region us-east-1

# Update later
aws secretsmanager update-secret \
  --secret-id "swarm-agent/prod" \
  --secret-string '{"OPENAI_API_KEY": "sk-new-key", ...}'
```

---

## Step 2 — Push Docker Images to ECR

```bash
# Set your AWS account ID and region
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION=us-east-1

# Authenticate Docker to ECR
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Build + push MCP Server
docker build -f docker/Dockerfile.mcp -t mcp-server .
docker tag mcp-server:latest \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/mcp-server:latest
docker push \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/mcp-server:latest

# Build + push Agents image
docker build -f docker/Dockerfile.agent -t swarm-agents .
docker tag swarm-agents:latest \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/multi-tenant-swarm-agent:latest
docker push \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/multi-tenant-swarm-agent:latest

# Build + push Public API
docker build -f docker/Dockerfile.api -t swarm-api .
docker tag swarm-api:latest \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/multi-tenant-swarm-agent:api
docker push \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/multi-tenant-swarm-agent:api

# Build + push Webapp
docker build -f docker/Dockerfile.webapp -t swarm-webapp .
docker tag swarm-webapp:latest \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/multi-tenant-swarm-agent:webapp
docker push \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/multi-tenant-swarm-agent:webapp
```

---

## Step 3 — Deploy with Terraform

```bash
cd terraform/

# Initialize
terraform init

# Preview what will be created
terraform plan \
  -var="aws_region=us-east-1" \
  -var="domain_name=yourdomain.com" \
  -var="environment=production"

# Deploy (takes ~10 minutes)
terraform apply \
  -var="aws_region=us-east-1" \
  -var="domain_name=yourdomain.com" \
  -var="environment=production" \
  -auto-approve
```

**Resources created:**
- VPC + subnets (public/private) + NAT Gateway
- ECS Cluster (Fargate) with 6 services
- 2 Application Load Balancers (public + internal)
- ACM TLS certificate
- Route53 DNS records
- ECR repositories
- CloudWatch log groups + alarms
- IAM roles

---

## Step 4 — Verify Deployment

```bash
# Get public URL from Terraform outputs
terraform output public_url
# → https://app.yourdomain.com

# Health check
curl https://app.yourdomain.com/api/health
# → {"status":"healthy","mcp_server":"healthy","api_version":"1.0.0",...}

# List agents
curl -H "X-API-Key: sk-prod-key-1" \
  https://app.yourdomain.com/api/agents

# Submit a task
curl -X POST https://app.yourdomain.com/api/tasks \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk-prod-key-1" \
  -d '{
    "agent_type": "hr",
    "task_type": "employee_onboarding",
    "tenant_id": "acme",
    "payload": {
      "employee_name": "Jane Doe",
      "department": "Engineering",
      "start_date": "2026-06-01"
    }
  }'
# → {"task_id": "abc-123", "status": "accepted", "poll_url": "/api/tasks/abc-123"}

# Poll for result
curl -H "X-API-Key: sk-prod-key-1" \
  https://app.yourdomain.com/api/tasks/abc-123
# → {"task_id": "abc-123", "status": "completed", "result": {...}}
```

---

## REST API Reference

### Authentication
All `/api/*` endpoints (except `/api/health`) require:
```
X-API-Key: <your-api-key>
```

### Submit a Task
```
POST /api/tasks
```
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `agent_type` | string | ✅ | `hr`, `finance`, `medical`, `supervisor` |
| `task_type` | string | ✅ | e.g. `employee_onboarding`, `expense_report` |
| `tenant_id` | string | ✅ | Your tenant identifier (alphanumeric) |
| `payload` | object | ✅ | Task-specific data |
| `priority` | int 1-10 | ❌ | Default: 5 |

**Response (202 Accepted):**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "accepted",
  "agent_type": "hr",
  "submitted_at": "2026-05-20T10:00:00Z",
  "poll_url": "/api/tasks/550e8400..."
}
```

### Poll Task Status
```
GET /api/tasks/{task_id}
```
**Response:**
```json
{
  "task_id": "550e8400...",
  "status": "completed",
  "result": { ... },
  "execution_time_ms": 1234
}
```

### Task Types by Agent

**HR Agent (`agent_type: "hr"`)**
| `task_type` | Payload fields |
|------------|----------------|
| `employee_onboarding` | `employee_name`, `department`, `start_date`, `position`, `salary` |
| `leave_request` | `employee_id`, `leave_type`, `start_date`, `end_date`, `reason` |
| `performance_review` | `employee_id`, `rating`, `feedback`, `goals` |
| `salary_adjustment` | `employee_id`, `new_salary`, `effective_date`, `reason` |

**Finance Agent (`agent_type: "finance"`)**
| `task_type` | Payload fields |
|------------|----------------|
| `expense_report` | `report_id`, `employee_id`, `amount`, `category`, `date`, `description` |
| `budget_planning` | `department`, `fiscal_year`, `budget_amount`, `items` |
| `invoice_processing` | `invoice_id`, `vendor_id`, `amount`, `due_date`, `description` |
| `financial_report` | `report_type`, `start_date`, `end_date`, `department` |

**Medical Agent (`agent_type: "medical"`)**
| `task_type` | Payload fields |
|------------|----------------|
| `appointment_scheduling` | `patient_id`, `doctor_id`, `appointment_date`, `appointment_time`, `reason` |
| `patient_records` | `patient_id`, `record_type`, `date_range` |
| `prescription` | `patient_id`, `medication_name`, `dosage`, `frequency`, `duration`, `doctor_id` |
| `health_report` | `patient_id`, `report_type`, `period_start`, `period_end` |

---

## Web App (Streamlit UI)

Access at: **`https://app.yourdomain.com`**

The webapp provides:
- Visual task submission form
- Real-time task status polling
- Agent selection and tenant switcher
- Task history view

---

## Monitoring & Logs

```bash
# View MCP server logs
aws logs tail /ecs/mcp-server --follow --region us-east-1

# View HR agent logs
aws logs tail /ecs/swarm-agents --follow --filter-pattern "hr-agent"

# View API logs
aws logs tail /ecs/webapp --follow

# CloudWatch Metrics dashboard
# Go to: AWS Console → CloudWatch → Dashboards → SwarmAgent
```

---

## Teardown

```bash
cd terraform/
terraform destroy \
  -var="aws_region=us-east-1" \
  -var="domain_name=yourdomain.com" \
  -auto-approve
```

> **Note:** ECR images and S3 buckets with `force_destroy=false` will NOT be deleted automatically. Remove manually if desired.

---

## Cost Estimate (us-east-1, monthly)

| Resource | Config | Est. Cost |
|----------|--------|-----------|
| ECS Fargate | 6 tasks × 0.5 vCPU × 1 GB | ~$55 |
| ALB (×2) | ~1000 req/day | ~$35 |
| NAT Gateway | ~10 GB/month | ~$50 |
| ACM | HTTPS cert | Free |
| CloudWatch | Logs + Metrics | ~$5 |
| Route53 | 2 records | ~$1 |
| ECR | 4 images × 500 MB | ~$2 |
| Secrets Manager | 1 secret | ~$0.40 |
| **Total** | | **~$148/month** |

Scale down (1 task per service, t3.micro NAT alt) → ~$80/month.
