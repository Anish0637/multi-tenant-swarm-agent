#!/usr/bin/env bash
# .github/scripts/smoke-test.sh
# Fast health + API smoke test run after every deploy.
# Usage: smoke-test.sh <base-url>   e.g. http://my-alb-123.us-east-1.elb.amazonaws.com

set -euo pipefail

BASE_URL="${1:-http://localhost}"
API_KEY="${SMOKE_TEST_API_KEY:-sk-prod-demo-key-12345678}"
MAX_WAIT=120   # seconds to wait for health to go green
INTERVAL=5

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Smoke test: $BASE_URL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

fail() { echo "❌  $1"; exit 1; }
pass() { echo "✅  $1"; }

# ── 1. Wait for /api/health ──────────────────────────────────────────────────
echo ""
echo "1/4  Waiting for /api/health ..."
elapsed=0
until curl -sf "$BASE_URL/api/health" -o /dev/null; do
  sleep $INTERVAL
  elapsed=$((elapsed + INTERVAL))
  [[ $elapsed -ge $MAX_WAIT ]] && fail "/api/health did not respond within ${MAX_WAIT}s"
  echo "     ... still waiting (${elapsed}s)"
done

HEALTH=$(curl -sf "$BASE_URL/api/health")
echo "$HEALTH" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('status') == 'healthy', f'status={d.get(\"status\")}'
print(f'     status={d[\"status\"]}  mcp_server={d.get(\"mcp_server\",\"unknown\")}')
" || fail "Health response unexpected: $HEALTH"
pass "/api/health → healthy"

# ── 2. List agents (authenticated) ──────────────────────────────────────────
echo ""
echo "2/4  GET /api/agents ..."
AGENTS=$(curl -sf -H "X-API-Key: $API_KEY" "$BASE_URL/api/agents")
COUNT=$(echo "$AGENTS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
[[ "$COUNT" -ge 4 ]] || fail "Expected ≥4 agents, got $COUNT"
pass "/api/agents → $COUNT agents returned"

# ── 3. Submit a task ─────────────────────────────────────────────────────────
echo ""
echo "3/4  POST /api/tasks ..."
RESPONSE=$(curl -sf -X POST "$BASE_URL/api/tasks" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "agent_type": "hr",
    "task_type": "employee_onboarding",
    "tenant_id": "smoketest",
    "payload": {"employee_name": "CI Bot", "department": "Engineering", "start_date": "2026-06-01"}
  }')

TASK_ID=$(echo "$RESPONSE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('status') == 'accepted', f'Expected accepted, got {d}'
print(d['task_id'])
") || fail "Task submit failed: $RESPONSE"
pass "Task submitted → $TASK_ID"

# ── 4. Poll task status ───────────────────────────────────────────────────────
echo ""
echo "4/4  Polling /api/tasks/$TASK_ID ..."
elapsed=0
FINAL_STATUS=""
until [[ "$FINAL_STATUS" == "completed" || "$FINAL_STATUS" == "failed" ]]; do
  sleep $INTERVAL
  elapsed=$((elapsed + INTERVAL))
  [[ $elapsed -ge 60 ]] && fail "Task did not complete within 60s"

  POLL=$(curl -sf -H "X-API-Key: $API_KEY" "$BASE_URL/api/tasks/$TASK_ID")
  FINAL_STATUS=$(echo "$POLL" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  echo "     ... status=$FINAL_STATUS (${elapsed}s)"
done

[[ "$FINAL_STATUS" == "completed" ]] || fail "Task ended with status=$FINAL_STATUS"
pass "Task completed successfully"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ All smoke tests passed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
