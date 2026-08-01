#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ARTIFACT_ROOT="${P4_REPORT_ARTIFACT_ROOT:-/private/tmp/restaurant-p4-artifacts}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
P4_BACKEND_IMAGE="${P4_BACKEND_IMAGE:-restaurant-pos-dev-backend:phase4-report-scope}"
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
  || fail "this rehearsal creates and drops isolated temporary databases; pass --yes"
[[ -f "$PROJECT_DIR/$COMPOSE_FILE" ]] || fail "compose file not found: $COMPOSE_FILE"

cd "$PROJECT_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
artifact_dir="${ARTIFACT_ROOT%/}/p4-report-scope-01-${timestamp}"
mkdir -p "$artifact_dir"

if docker ps --format '{{.Names}}' | grep -Fx 'restaurant-pos-dev-backend-1' >/dev/null; then
  fail "main backend must remain stopped during the Phase 4 report gate"
fi
legacy_safe_image_before="$(docker image inspect restaurant-pos-dev-backend:latest --format '{{.Id}}')"

printf 'Running reusable Company/Brand/Branch assignment and approval rehearsal...\n'
child_output="$(
  RESTAURANT_BACKEND_IMAGE="$P4_BACKEND_IMAGE" \
    scripts/rehearse-phase2-approval-sessions.sh \
      --yes \
      --backup-root "$ARTIFACT_ROOT" 2>&1
)"
printf '%s\n' "$child_output"
printf '%s\n' "$child_output" \
  | grep -F 'p4_report_scope=ok company=true brand=true branch=true shift=true' >/dev/null \
  || fail "Phase 4 report API assertion is missing"
child_artifact="$(
  printf '%s\n' "$child_output" \
    | sed -n 's/^Phase 2 approval session rehearsal passed: //p' \
    | tail -n 1
)"
[[ -f "$child_artifact/manifest.txt" ]] \
  || fail "assignment/approval child manifest is missing"

printf 'Running complete backend regression on the isolated Phase 4 image...\n'
export RESTAURANT_BACKEND_IMAGE="$P4_BACKEND_IMAGE"
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

legacy_safe_image_after="$(docker image inspect restaurant-pos-dev-backend:latest --format '{{.Id}}')"
[[ "$legacy_safe_image_after" = "$legacy_safe_image_before" ]] \
  || fail "legacy-safe backend latest image changed during the Phase 4 report gate"
if docker ps --format '{{.Names}}' | grep -Fx 'restaurant-pos-dev-backend-1' >/dev/null; then
  fail "main backend started during the Phase 4 report gate"
fi

cleanup_query="SELECT count(*) FROM pg_database WHERE datname ~ '^restaurant_p2_approval(_platform|_ops)?_[0-9]+'"
remaining_temporary_databases="$(
  docker compose -f "$COMPOSE_FILE" exec -T \
    -e P4_CLEANUP_QUERY="$cleanup_query" \
    postgres sh -c \
      'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "$P4_CLEANUP_QUERY"' \
    | tr -d '[:space:]'
)"
[[ "$remaining_temporary_databases" = "0" ]] \
  || fail "Phase 4 report temporary databases remain: $remaining_temporary_databases"

cat > "$artifact_dir/manifest.txt" <<EOF
scope_id=P4-REPORT-SCOPE-01
rehearsal_status=verified
snapshot_timestamp_utc=$timestamp
source_commit=$(git rev-parse --short HEAD)
company_aggregate_report=true
company_selected_branch_report=true
brand_consolidated_report=true
brand_assignment_isolation=true
brand_generic_current_branch_only=true
branch_query_isolation=true
branch_consolidated_report_denied=true
shift_branch_isolation=true
shift_pdf_branch_isolation=true
existing_report_contract_preserved=true
new_schema_migration=false
live_fingerprints_unchanged=true
temporary_database_cleanup=true
backend_test_count=$test_count
frontend_type_check=true
frontend_production_build=true
runtime_identity_database=legacy
runtime_restaurant_service_database=legacy
runtime_reference_projector_enabled=false
main_backend_started=false
legacy_safe_latest_image_unchanged=true
legacy_safe_latest_image_id=$legacy_safe_image_after
phase4_backend_image=$P4_BACKEND_IMAGE
assignment_approval_manifest=$child_artifact/manifest.txt
production_activation=false
EOF

printf 'Phase 4 report scope rehearsal passed: %s\n' "$artifact_dir"
