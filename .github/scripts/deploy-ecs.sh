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

# ── Guard: required secrets must be non-empty for production ────────────────
if [[ "$ENV" == "production" ]]; then
  [[ -z "${MCP_INTERNAL_API_KEY:-}" ]] && { echo "ERROR: MCP_INTERNAL_API_KEY secret is not set in GitHub Actions — add it under repo Settings → Secrets"; exit 1; }
  [[ -z "${API_KEYS:-}" ]]             && { echo "ERROR: API_KEYS secret is not set in GitHub Actions — add it under repo Settings → Secrets"; exit 1; }
fi

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
  local ENV_OVERRIDES="${5:-}"  # optional JSON object {"KEY":"value",...}

  echo ""
  echo "▶  Updating $SERVICE ..."

  # 1. Fetch current task definition JSON
  TASK_DEF=$(aws ecs describe-task-definition \
    --task-definition "$TASK_FAMILY" \
    --query 'taskDefinition' \
    --output json)

  # 2. Swap image (use the explicit IMAGE arg), optionally upsert env vars, strip read-only fields
  # Note: use -c to avoid the pipe+heredoc stdin conflict (heredoc overrides pipe)
  NEW_TASK_DEF=$(echo "$TASK_DEF" | \
    CONTAINER_NAME="$CONTAINER" NEW_IMAGE="$IMAGE" ENV_OVERRIDES="$ENV_OVERRIDES" python3 -c '
import json, sys, os
td = json.load(sys.stdin)
container = os.environ["CONTAINER_NAME"]
new_image = os.environ["NEW_IMAGE"]
env_overrides_str = os.environ.get("ENV_OVERRIDES", "")
env_overrides = json.loads(env_overrides_str) if env_overrides_str else {}
for c in td["containerDefinitions"]:
    if c["name"] == container:
        c["image"] = new_image
        if env_overrides:
            existing = {e["name"]: e["value"] for e in c.get("environment", [])}
            existing.update(env_overrides)
            c["environment"] = [{"name": k, "value": v} for k, v in existing.items()]
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
# Env-var overrides injected from CI secrets
PUBLIC_API_ENV="{\"MCP_INTERNAL_API_KEY\":\"${MCP_INTERNAL_API_KEY:-}\",\"API_KEYS\":\"${API_KEYS:-}\"}"
MCP_SERVER_ENV="{\"MCP_INTERNAL_API_KEY\":\"${MCP_INTERNAL_API_KEY:-}\",\"API_KEYS\":\"${API_KEYS:-}\"}"
WEBAPP_ENV="{\"MCP_INTERNAL_API_KEY\":\"${MCP_INTERNAL_API_KEY:-}\"}"

deploy_service "mcp-server"      "mcp-server"     "$ECR_BASE/mcp-server:$TAG"                        "mcp-server"   "$MCP_SERVER_ENV"
deploy_service "public-api"      "public-api"     "$ECR_BASE/multi-tenant-swarm-agent:api-$TAG"      "public-api"   "$PUBLIC_API_ENV"
deploy_service "webapp"          "webapp"         "$ECR_BASE/multi-tenant-swarm-agent:webapp-$TAG"   "webapp"       "$WEBAPP_ENV"
deploy_service "hr-agent"        "hr-agent"       "$ECR_BASE/multi-tenant-swarm-agent:$TAG"          "hr-agent"
deploy_service "finance-agent"   "finance-agent"  "$ECR_BASE/multi-tenant-swarm-agent:$TAG"          "finance-agent"
deploy_service "medical-agent"   "medical-agent"  "$ECR_BASE/multi-tenant-swarm-agent:$TAG"          "medical-agent"

# ── Wait for services to stabilize ──────────────────────────────────────────
# aws ecs wait services-stable is limited to 40×15 s = 10 min and exits 255 on
# timeout.  We replace it with a custom poll that waits up to 20 min, prints
# per-service status, and exits non-zero with a clear message on real failure.
echo ""
echo "⏳  Waiting for services to stabilize (up to 20 min)..."

SERVICES="mcp-server public-api webapp hr-agent finance-agent medical-agent"

MAX_WAIT=1200   # 20 minutes
INTERVAL=20     # poll every 20 s
ELAPSED=0

until [[ $ELAPSED -ge $MAX_WAIT ]]; do
  # Query all services in one call
  STATUS_JSON=$(aws ecs describe-services \
    --cluster "$CLUSTER" \
    --services $SERVICES \
    --query 'services[*].{name:serviceName,desired:desiredCount,running:runningCount,pending:pendingCount,rollout:deployments[0].rolloutState}' \
    --output json)

  # Count how many are fully stable (PRIMARY rollout COMPLETED, running==desired, pending==0)
  STABLE=$(echo "$STATUS_JSON" | python3 -c "
import json, sys
svcs = json.load(sys.stdin)
stable = sum(1 for s in svcs
             if s.get('rollout') == 'COMPLETED'
             and s['running'] == s['desired']
             and s['pending'] == 0)
print(stable)
")

  TOTAL=$(echo "$STATUS_JSON" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")

  echo "  [${ELAPSED}s]  ${STABLE}/${TOTAL} services stable"

  # Print one-line status per service for visibility
  echo "$STATUS_JSON" | python3 -c "
import json, sys
for s in json.load(sys.stdin):
    icon = '✅' if (s.get('rollout')=='COMPLETED' and s['running']==s['desired'] and s['pending']==0) else '⏳'
    print(f\"    {icon}  {s['name']:20s}  desired={s['desired']}  running={s['running']}  pending={s['pending']}  rollout={s.get('rollout','?')}\")
"

  if [[ "$STABLE" == "$TOTAL" ]]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  ✅ All services stable — tag $TAG deployed"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    break
  fi

  sleep "$INTERVAL"
  ELAPSED=$(( ELAPSED + INTERVAL ))
done

if [[ $ELAPSED -ge $MAX_WAIT && "$STABLE" != "$TOTAL" ]]; then
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  ⚠️  Timeout after ${MAX_WAIT}s — ${STABLE}/${TOTAL} stable."
  echo "  Deploy was triggered but services may still be converging."
  echo "  Check ECS console for task failure reasons."
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  exit 1
fi

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
