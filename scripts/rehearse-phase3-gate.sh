#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ARTIFACT_ROOT="${P3_GATE_ARTIFACT_ROOT:-/private/tmp/restaurant-p3-artifacts}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
P3_BACKEND_IMAGE="${P3_BACKEND_IMAGE:-restaurant-pos-dev-backend:phase3-gate}"
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
  || fail "this gate creates and drops isolated temporary databases; pass --yes"
[[ -f "$PROJECT_DIR/$COMPOSE_FILE" ]] || fail "compose file not found: $COMPOSE_FILE"

cd "$PROJECT_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
artifact_dir="${ARTIFACT_ROOT%/}/p3-phase-gate-06-${timestamp}"
mkdir -p "$artifact_dir"

if docker ps --format '{{.Names}}' | grep -Fx 'restaurant-pos-dev-backend-1' >/dev/null; then
  fail "main backend must remain stopped during the Phase 3 gate"
fi
legacy_safe_image_before="$(docker image inspect restaurant-pos-dev-backend:latest --format '{{.Id}}')"

run_child() {
  local label="$1"
  local script_path="$2"
  local success_marker="$3"
  local output=""
  printf 'Running %s rehearsal...\n' "$label"
  if ! output="$(
    P3_BACKEND_IMAGE="$P3_BACKEND_IMAGE" \
      COMPOSE_FILE="$COMPOSE_FILE" \
      "$script_path" --yes --artifact-root "$ARTIFACT_ROOT" 2>&1
  )"; then
    printf '%s\n' "$output"
    fail "$label rehearsal failed"
  fi
  printf '%s\n' "$output"
  printf '%s\n' "$output" | grep -F "$success_marker" >/dev/null \
    || fail "$label success assertion is missing"
  CHILD_OUTPUT="$output"
}

run_child \
  "device pairing and durable credential" \
  scripts/rehearse-phase3-device-pairing.sh \
  "Phase 3 device pairing rehearsal passed:"
pairing_output="$CHILD_OUTPUT"
printf '%s\n' "$pairing_output" | grep -F 'persistent_refresh=true' >/dev/null \
  || fail "persistent device refresh assertion is missing"
pairing_artifact="$(
  printf '%s\n' "$pairing_output" \
    | sed -n 's/^Phase 3 device pairing rehearsal passed: //p' \
    | tail -n 1
)"

run_child \
  "dedicated workspace and staff handover" \
  scripts/rehearse-phase3-device-workspaces.sh \
  "Phase 3 dedicated workspace rehearsal passed:"
workspace_output="$CHILD_OUTPUT"
for assertion in staff_handover=true staff_device_audit=true; do
  printf '%s\n' "$workspace_output" | grep -F "$assertion" >/dev/null \
    || fail "workspace assertion is missing: $assertion"
done
workspace_artifact="$(
  printf '%s\n' "$workspace_output" \
    | sed -n 's/^Phase 3 dedicated workspace rehearsal passed: //p' \
    | tail -n 1
)"

run_child \
  "offline authorization" \
  scripts/rehearse-phase3-offline-authorization.sh \
  "Phase 3 offline authorization rehearsal passed:"
offline_output="$CHILD_OUTPUT"
printf '%s\n' "$offline_output" | grep -F 'per_order_review=true' >/dev/null \
  || fail "offline per-order review assertion is missing"
offline_artifact="$(
  printf '%s\n' "$offline_output" \
    | sed -n 's/^Phase 3 offline authorization rehearsal passed: //p' \
    | tail -n 1
)"

for child_manifest in \
  "$pairing_artifact/manifest.txt" \
  "$workspace_artifact/manifest.txt" \
  "$offline_artifact/manifest.txt"; do
  [[ -f "$child_manifest" ]] || fail "child rehearsal manifest is missing: $child_manifest"
done

printf 'Running complete backend regression on the isolated Phase 3 image...\n'
export RESTAURANT_BACKEND_IMAGE="$P3_BACKEND_IMAGE"
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
  || fail "legacy-safe backend latest image changed during the Phase 3 gate"
if docker ps --format '{{.Names}}' | grep -Fx 'restaurant-pos-dev-backend-1' >/dev/null; then
  fail "main backend started during the Phase 3 gate"
fi

cleanup_query="SELECT count(*) FROM pg_database WHERE datname ~ '^restaurant_p3_(device|device_platform|workspace|workspace_platform|offline|offline_platform)_[0-9]+'"
remaining_temporary_databases="$(
  docker compose -f "$COMPOSE_FILE" exec -T \
    -e P3_CLEANUP_QUERY="$cleanup_query" \
    postgres sh -c \
      'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "$P3_CLEANUP_QUERY"' \
    | tr -d '[:space:]'
)"
[[ "$remaining_temporary_databases" = "0" ]] \
  || fail "Phase 3 temporary databases remain: $remaining_temporary_databases"

cat > "$artifact_dir/manifest.txt" <<EOF
scope_id=P3-PHASE-GATE-06
gate_status=verified_implementation_physical_tablet_deferred
snapshot_timestamp_utc=$timestamp
source_commit=$(git rev-parse --short HEAD)
identity_legacy_head=p3device0004
platform_head=p3platform0007
platform_schema_contract_version=5
device_pairing_branch_station_scope=true
device_refresh_hash_only=true
device_refresh_auto_renew=true
device_rotate_revoke_kill_switch=true
counter_staff_identity_gate=true
counter_staff_handover=true
counter_staff_device_audit=true
kitchen_station_scope=true
pickup_branch_scope=true
offline_signed_expiring_authorization=true
offline_per_order_review=true
legacy_paid_queue_preserved=true
live_fingerprints_unchanged=true
temporary_database_cleanup=true
backend_test_count=$test_count
frontend_type_check=true
frontend_production_build=true
browser_counter_pair_device_gate=verified_by_owner_visual_evidence
physical_tablet_android_uat=deferred_by_platform_owner
production_activation=false
runtime_identity_database=legacy
runtime_restaurant_service_database=legacy
runtime_reference_projector_enabled=false
main_backend_started=false
legacy_safe_latest_image_unchanged=true
legacy_safe_latest_image_id=$legacy_safe_image_after
phase3_gate_backend_image=$P3_BACKEND_IMAGE
pairing_manifest=$pairing_artifact/manifest.txt
workspace_manifest=$workspace_artifact/manifest.txt
offline_manifest=$offline_artifact/manifest.txt
EOF

printf 'Phase 3 gate passed: %s\n' "$artifact_dir"
