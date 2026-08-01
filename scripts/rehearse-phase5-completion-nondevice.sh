#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_ROOT="${P5_ARTIFACT_ROOT:-/private/tmp/restaurant-p5-artifacts}"
COMPLETION_PROJECT="${P5_COMPLETION_COMPOSE_PROJECT:-restaurant-p5-completion04}"
COMPLETION_PASSWORD="${P5_COMPLETION_ADMIN_PASSWORD:-}"
API_PORT="${P5_COMPLETION_API_PORT:-18002}"
BACKEND_IMAGE="${P5_COMPLETION_BACKEND_IMAGE:-restaurant-pos-dev-backend:phase5-completion-nondevice}"
ASSUME_YES=0

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --yes) ASSUME_YES=1; shift ;;
    --artifact-root)
      [[ "$#" -ge 2 ]] || fail "--artifact-root requires a path"
      ARTIFACT_ROOT="$2"
      shift 2
      ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[[ "$ASSUME_YES" = "1" ]] || fail "this gate replaces only its isolated Compose volumes; pass --yes"
[[ "$COMPLETION_PROJECT" == restaurant-p5-completion* ]] \
  || fail "completion Compose project must start with restaurant-p5-completion"
[[ ${#COMPLETION_PASSWORD} -ge 16 ]] \
  || fail "P5_COMPLETION_ADMIN_PASSWORD must be at least 16 characters"

cd "$PROJECT_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
artifact_dir="${ARTIFACT_ROOT%/}/p5-completion-nondevice-04-${timestamp}"
mkdir -p "$artifact_dir"

export COMPOSE_PROJECT_NAME="$COMPLETION_PROJECT"
export COMPOSE_FILE="docker-compose.yml:docker-compose.uat.yml"
export P5_UAT_ADMIN_PASSWORD="$COMPLETION_PASSWORD"
export RESTAURANT_API_PORT="$API_PORT"
export RESTAURANT_BACKEND_IMAGE="$BACKEND_IMAGE"

cleanup() {
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

printf 'Preparing isolated non-device completion stack %s...\n' "$COMPLETION_PROJECT"
docker compose down -v --remove-orphans >/dev/null 2>&1 || true
docker compose build backend
docker compose up -d postgres redis

tries=0
until docker compose exec -T postgres sh -c \
  'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1))
  [[ "$tries" -lt 45 ]] || fail "isolated completion PostgreSQL did not become ready"
  sleep 1
done

docker compose run --rm backend alembic upgrade head
docker compose up -d backend
tries=0
until curl -fsS "http://127.0.0.1:${API_PORT}/health/ready" \
  >"$artifact_dir/health-ready.json"; do
  tries=$((tries + 1))
  [[ "$tries" -lt 60 ]] || fail "isolated completion backend did not become ready"
  sleep 1
done

printf 'Running backend and role-scope regression...\n'
docker compose exec -T backend python -m unittest discover -s tests -p 'test_*.py' \
  2>&1 | tee "$artifact_dir/backend-regression.log"
INTERNAL_BASE_URL=http://127.0.0.1:8000 \
  scripts/fnb-permission-smoke.sh 2>&1 | tee "$artifact_dir/owner-role-permission-smoke.log"
docker compose exec -T -e PYTHONPATH=/app backend python -m tests.smoke_role_presets_api \
  2>&1 | tee "$artifact_dir/role-presets-smoke.log"
docker compose exec -T -e PYTHONPATH=/app backend python -m tests.smoke_approval_api \
  2>&1 | tee "$artifact_dir/pos-approval-smoke.log"

printf 'Running explicit retail_pos compatibility regression...\n'
docker compose exec -T \
  -e PYTHONPATH=/app \
  -e P5_COMPLETION_PROJECT_NAME="$COMPLETION_PROJECT" \
  backend python tests/smoke_retail_pos_compatibility_api.py \
  2>&1 | tee "$artifact_dir/retail-pos-compatibility-smoke.log"

printf 'Running frontend and repository regression...\n'
npm --prefix frontend run type-check 2>&1 | tee "$artifact_dir/frontend-typecheck.log"
npm --prefix frontend run build 2>&1 | tee "$artifact_dir/frontend-build.log"
scripts/pre-git-safety-check.sh 2>&1 | tee "$artifact_dir/repository-safety.log"

cat >"$artifact_dir/manifest.txt" <<EOF
scope=P5-COMPLETION-NONDEVICE-04
timestamp=$timestamp
compose_project=$COMPLETION_PROJECT
backend_image=$BACKEND_IMAGE
backend_regression=passed
company_owner_restaurant_api_security=passed
manager_cashier_kitchen_security=passed
role_preset_policy_regression=passed
pos_approval_regression=passed
retail_pos_context=passed
retail_pos_sale_payment_stock_accounting_outbox=passed
retail_pos_idempotency=passed
retail_pos_report_reconciliation=passed
retail_pos_shift_cash_reconciliation=passed
retail_pos_restaurant_boundary=passed
retail_pos_platform_boundary=passed
frontend_typecheck_build=passed
repository_safety_scan=passed
physical_device_uat=deferred_by_owner_until_hardware_arrives
visual_uat=deferred_by_owner_until_hardware_arrives
owner_completion_signoff=pending
production_activated=false
phase6_started=false
EOF

printf 'Non-device Restaurant completion gate passed. Artifact: %s\n' "$artifact_dir/manifest.txt"
