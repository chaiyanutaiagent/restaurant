#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ARTIFACT_ROOT="${P2_GATE_ARTIFACT_ROOT:-/private/tmp/restaurant-p2-artifacts}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSUME_YES=0

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --yes)
      ASSUME_YES=1
      shift
      ;;
    --artifact-root)
      [[ "$#" -ge 2 ]] || fail "--artifact-root requires a path"
      ARTIFACT_ROOT="$2"
      shift 2
      ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[[ "$ASSUME_YES" = "1" ]] \
  || fail "this gate runs isolated migration rehearsals; pass --yes"
[[ -f "$PROJECT_DIR/$COMPOSE_FILE" ]] || fail "compose file not found: $COMPOSE_FILE"

cd "$PROJECT_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
artifact_dir="${ARTIFACT_ROOT%/}/p2-phase-gate-04-${timestamp}"
mkdir -p "$artifact_dir"

printf 'Running consolidated role, scope, approval, and boundary rehearsal...\n'
approval_output=""
if ! approval_output="$(
  COMPOSE_FILE="$COMPOSE_FILE" \
    scripts/rehearse-phase2-approval-sessions.sh \
      --yes \
      --backup-root "$ARTIFACT_ROOT" 2>&1
)"; then
  printf '%s\n' "$approval_output"
  fail "consolidated Phase 2 rehearsal failed"
fi
printf '%s\n' "$approval_output"
for assertion in \
  p2_scope_company_brand_branch=ok \
  p2_scope_station_isolation=ok \
  p2_scope_multi_role_union=ok \
  p2_scope_audit_revoke=ok \
  p2_scope_kitchen_boundary=ok; do
  printf '%s\n' "$approval_output" | grep -F "$assertion" >/dev/null \
    || fail "missing scope API assertion: $assertion"
done
printf '%s\n' "$approval_output" | grep -F 'role_presets=true' >/dev/null \
  || fail "role preset API assertion is missing"
printf '%s\n' "$approval_output" | grep -F 'restaurant_checkout=true' >/dev/null \
  || fail "Restaurant checkout approval assertion is missing"
printf '%s\n' "$approval_output" | grep -F 'Phase 2 approval session rehearsal passed:' >/dev/null \
  || fail "approval rehearsal did not report success"

printf 'Running complete backend regression...\n'
backend_output="$(
  docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
    -v "$PROJECT_DIR/backend/tests:/app/tests:ro" \
    backend python -m unittest discover -s /app/tests -p 'test_*.py' 2>&1
)"
printf '%s\n' "$backend_output"
test_count="$(
  printf '%s\n' "$backend_output" \
    | sed -n 's/^Ran \([0-9][0-9]*\) tests.*/\1/p' \
    | tail -n 1
)"
[[ -n "$test_count" ]] || fail "backend regression count is missing"
printf '%s\n' "$backend_output" | grep -Fx 'OK' >/dev/null \
  || fail "backend regression did not finish with OK"

printf 'Running frontend type-check and production build...\n'
npm --prefix frontend run type-check
npm --prefix frontend run build

approval_artifact="$(
  printf '%s\n' "$approval_output" \
    | sed -n 's/^Phase 2 approval session rehearsal passed: //p' \
    | tail -n 1
)"
[[ -f "$approval_artifact/manifest.txt" ]] || fail "approval manifest is missing"

cat > "$artifact_dir/manifest.txt" <<EOF
scope_id=P2-PHASE-GATE-04
gate_status=verified
snapshot_timestamp_utc=$timestamp
source_commit=$(git rev-parse --short HEAD)
role_preset_policy=2026-08-01.3
persona_matrix=company_owner,brand_manager,branch_manager,cashier,kitchen_staff
company_brand_branch_station_scope=true
kitchen_station_privilege_boundary=true
cashier_limit_requires_approval=true
approval_single_use_fingerprint_lockout=true
restaurant_checkout_discount=true
void_refund_stock_approval=true
approval_audit_evidence=true
legacy_platform_restaurant_rehearsal=true
backend_test_count=$test_count
frontend_type_check=true
frontend_production_build=true
visual_browser_clickthrough=deferred_no_browser_instance
runtime_identity_database=legacy
runtime_restaurant_service_database=legacy
runtime_reference_projector_enabled=false
combined_boundary_manifest=$approval_artifact/manifest.txt
EOF

printf 'Phase 2 gate passed: %s\n' "$artifact_dir"
