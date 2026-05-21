#!/usr/bin/env bash
# .github/scripts/deploy-ecs.sh
# Rolls out a new image tag to every ECS service using direct AWS CLI calls.
# Usage: deploy-ecs.sh --cluster <name> --env <production|staging> --tag <sha>

set -euo pipefail

# ── Parse args ──────────────────────────────────────────────────────────────
CLUSTER=""
ENV=""
TAG=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --cluster) CLUSTER="$2"; shift 2 ;;
    --env)     ENV="$2";     shift 2 ;;
    --tag)     TAG="$2";     shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

[[ -z "$CLUSTER" || -z "$ENV" || -z "$TAG" ]] && { echo "Missing required args"; exit 1; }

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID}"
ECR_BASE="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Deploying tag: $TAG  →  cluster: $CLUSTER  ($ENV)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Helper: update one ECS service ──────────────────────────────────────────
deploy_service() {
  local SERVICE="$1"
  local TASK_FAMILY="$2"
  local IMAGE="$3"
  local CONTAINER="$4"

  echo ""
  echo "▶  Updating $SERVICE ..."

  # 1. Fetch current task definition JSON
  TASK_DEF=$(aws ecs describe-task-definition \
    --task-definition "$TASK_FAMILY" \
    --query 'taskDefinition' \
    --output json)

  # 2. Swap image tag, strip read-only fields
  # Note: use -c to avoid the pipe+heredoc stdin conflict (heredoc overrides pipe)
  NEW_TASK_DEF=$(echo "$TASK_DEF" | \
    CONTAINER_NAME="$CONTAINER" IMAGE_TAG="$TAG" python3 -c '
import json, sys, os
td = json.load(sys.stdin)
container = os.environ["CONTAINER_NAME"]
tag = os.environ["IMAGE_TAG"]
for c in td["containerDefinitions"]:
    if c["name"] == container:
        base = c["image"].rsplit(":", 1)[0]
        c["image"] = f"{base}:{tag}"
for key in ["taskDefinitionArn","revision","status","requiresAttributes",
            "compatibilities","registeredAt","registeredBy"]:
    td.pop(key, None)
print(json.dumps(td))
')

  # 3. Register new task definition revision
  NEW_REVISION=$(aws ecs register-task-definition \
    --cli-input-json "$NEW_TASK_DEF" \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

  echo "   New revision: $NEW_REVISION"

  # 4. Update service to use the new revision
  aws ecs update-service \
    --cluster  "$CLUSTER" \
    --service  "$SERVICE" \
    --task-definition "$NEW_REVISION" \
    --force-new-deployment \
    --output json | python3 -c "
import json,sys
d=json.load(sys.stdin)['service']
print(f'   desired={d[\"desiredCount\"]}  running={d[\"runningCount\"]}  status={d[\"status\"]}')
"

  echo "   ✅ $SERVICE update triggered"
}

# ── Deploy each service ──────────────────────────────────────────────────────
deploy_service "mcp-server"      "mcp-server"     "$ECR_BASE/mcp-server:$TAG"                        "mcp-server"
deploy_service "public-api"      "public-api"     "$ECR_BASE/multi-tenant-swarm-agent:api-$TAG"      "public-api"
deploy_service "webapp"          "webapp"         "$ECR_BASE/multi-tenant-swarm-agent:webapp-$TAG"   "webapp"
deploy_service "hr-agent"        "hr-agent"       "$ECR_BASE/multi-tenant-swarm-agent:$TAG"          "hr-agent"
deploy_service "finance-agent"   "finance-agent"  "$ECR_BASE/multi-tenant-swarm-agent:$TAG"          "finance-agent"
deploy_service "medical-agent"   "medical-agent"  "$ECR_BASE/multi-tenant-swarm-agent:$TAG"          "medical-agent"

# ── Wait for services to stabilize ──────────────────────────────────────────
echo ""
echo "⏳  Waiting for services to stabilize (up to 10 min)..."

SERVICES="mcp-server public-api webapp hr-agent finance-agent medical-agent"

aws ecs wait services-stable \
  --cluster "$CLUSTER" \
  --services $SERVICES

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ All services stable — tag $TAG deployed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Print final service status ───────────────────────────────────────────────
aws ecs describe-services \
  --cluster "$CLUSTER" \
  --services $SERVICES \
  --query 'services[*].{Service:serviceName,Status:status,Desired:desiredCount,Running:runningCount,Pending:pendingCount}' \
  --output table
