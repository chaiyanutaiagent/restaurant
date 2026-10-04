#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
export RESTAURANT_BACKEND_IMAGE="${SAAS_OPERATIONS_BACKEND_IMAGE:-restaurant-pos-dev-backend:saas-operations-gate}"
ARTIFACT_ROOT="${SAAS_OPERATIONS_ARTIFACT_ROOT:-/private/tmp/restaurant-saas-artifacts}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_LEGACY_HEAD="6b7c8d9e0f12"
EXPECTED_PLATFORM_HEAD="p1platform0003"
EXPECTED_RESTAURANT_HEAD="p1restaurant0003"
TARGET_LEGACY_HEAD="p9ops0011"
TARGET_PLATFORM_HEAD="p9platform0013"
LEGACY_PREFIX="restaurant_saas_operations_"
PLATFORM_PREFIX="restaurant_saas_operations_platform_"
OPS_PREFIX="restaurant_saas_operations_ops_"
ASSUME_YES=0
LEGACY_DATABASE=""
PLATFORM_DATABASE=""
OPS_DATABASE=""
TEMP_DIR=""

fail() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

drop_database() {
  database_name="$1"
  expected_prefix="$2"
  case "$database_name" in
    ${expected_prefix}[0-9]*)
      docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
        psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
          -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '\''$1'\'' AND pid <> pg_backend_pid()" >/dev/null
        dropdb --if-exists -U "$POSTGRES_USER" "$1"
      ' sh "$database_name" >/dev/null 2>&1 || true
      ;;
  esac
}

cleanup() {
  [[ -z "$LEGACY_DATABASE" ]] || drop_database "$LEGACY_DATABASE" "$LEGACY_PREFIX"
  [[ -z "$PLATFORM_DATABASE" ]] || drop_database "$PLATFORM_DATABASE" "$PLATFORM_PREFIX"
  [[ -z "$OPS_DATABASE" ]] || drop_database "$OPS_DATABASE" "$OPS_PREFIX"
  if [[ -n "$TEMP_DIR" ]]; then
    case "$TEMP_DIR" in
      /private/tmp/restaurant-saas-operations.*|/tmp/restaurant-saas-operations.*) rm -rf "$TEMP_DIR" ;;
    esac
  fi
}
trap cleanup EXIT HUP INT TERM

cd "$PROJECT_DIR"
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --yes) ASSUME_YES=1; shift ;;
    --artifact-root) [[ "$#" -ge 2 ]] || fail "--artifact-root requires a path"; ARTIFACT_ROOT="$2"; shift 2 ;;
    *) fail "unknown argument: $1" ;;
  esac
done
[[ "$ASSUME_YES" = "1" ]] || fail "this rehearsal creates and drops isolated temporary databases; pass --yes"

psql_boundary() {
  database_env="$1"
  query="$2"
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
    case "$1" in
      POSTGRES_DB) database_name="$POSTGRES_DB" ;;
      PLATFORM_POSTGRES_DB) database_name="$PLATFORM_POSTGRES_DB" ;;
      RESTAURANT_POSTGRES_DB) database_name="$RESTAURANT_POSTGRES_DB" ;;
      *) exit 2 ;;
    esac
    psql -U "$POSTGRES_USER" -d "$database_name" -tAc "$2"
  ' sh "$database_env" "$query" | tr -d '[:space:]'
}

psql_database() {
  database_name="$1"
  query="$2"
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$1" -tAc "$2"' sh "$database_name" "$query" | tr -d '[:space:]'
}

fingerprint() {
  database_env="$1"
  psql_boundary "$database_env" 'SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT count(*) FROM companies), chr(58), (SELECT count(*) FROM users))'
}

printf 'Starting isolated SaaS operations gate...\n'
docker compose -f "$COMPOSE_FILE" up -d postgres redis >/dev/null
tries=0
until docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1)); [[ "$tries" -lt 30 ]] || fail "postgres service did not become ready"; sleep 1
done
[[ "$(psql_boundary POSTGRES_DB 'SELECT version_num FROM alembic_version')" = "$EXPECTED_LEGACY_HEAD" ]] || fail "unexpected live legacy head"
[[ "$(psql_boundary PLATFORM_POSTGRES_DB 'SELECT version_num FROM alembic_version')" = "$EXPECTED_PLATFORM_HEAD" ]] || fail "unexpected live Platform head"
[[ "$(psql_boundary RESTAURANT_POSTGRES_DB 'SELECT version_num FROM alembic_version')" = "$EXPECTED_RESTAURANT_HEAD" ]] || fail "unexpected live Restaurant head"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
suffix="$(date -u +%Y%m%d%H%M%S)$$"
LEGACY_DATABASE="${LEGACY_PREFIX}${suffix}"
PLATFORM_DATABASE="${PLATFORM_PREFIX}${suffix}"
OPS_DATABASE="${OPS_PREFIX}${suffix}"
artifact_dir="${ARTIFACT_ROOT%/}/saas-operations-05-${timestamp}"
backup_root="$artifact_dir/backups"
mkdir -p "$artifact_dir" "$backup_root"
TEMP_DIR="$(mktemp -d /private/tmp/restaurant-saas-operations.XXXXXX 2>/dev/null || mktemp -d /tmp/restaurant-saas-operations.XXXXXX)"

legacy_before="$(fingerprint POSTGRES_DB)"
platform_before="$(fingerprint PLATFORM_POSTGRES_DB)"
restaurant_before="$(fingerprint RESTAURANT_POSTGRES_DB)"

printf 'Cloning three database boundaries...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$TEMP_DIR/legacy.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB"' > "$TEMP_DIR/platform.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$RESTAURANT_POSTGRES_DB"' > "$TEMP_DIR/restaurant.dump"
for database_name in "$LEGACY_DATABASE" "$PLATFORM_DATABASE" "$OPS_DATABASE"; do
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$database_name"
done
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$LEGACY_DATABASE" < "$TEMP_DIR/legacy.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$PLATFORM_DATABASE" < "$TEMP_DIR/platform.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$OPS_DATABASE" < "$TEMP_DIR/restaurant.dump"

printf 'Building isolated operations backend image...\n'
docker compose -f "$COMPOSE_FILE" build backend >/dev/null

printf 'Rehearsing operations migrations...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -e SAAS_OPERATIONS_DATABASE_NAME="$LEGACY_DATABASE" backend sh -c '
  set -eu; database_server="${DATABASE_URL%/*}"; export DATABASE_URL="$database_server/$SAAS_OPERATIONS_DATABASE_NAME"
  alembic upgrade p9ops0011; alembic downgrade p8member0010; alembic upgrade p9ops0011
'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -e SAAS_OPERATIONS_PLATFORM_DATABASE_NAME="$PLATFORM_DATABASE" backend sh -c '
  set -eu; database_server="${PLATFORM_DATABASE_URL%/*}"; export PLATFORM_DATABASE_URL="$database_server/$SAAS_OPERATIONS_PLATFORM_DATABASE_NAME"
  alembic -c alembic-boundaries.ini -n platform upgrade p9platform0013
  alembic -c alembic-boundaries.ini -n platform downgrade p8platform0012
  alembic -c alembic-boundaries.ini -n platform upgrade p9platform0013
'
[[ "$(psql_database "$LEGACY_DATABASE" 'SELECT version_num FROM alembic_version')" = "$TARGET_LEGACY_HEAD" ]] || fail "legacy clone did not reach operations head"
[[ "$(psql_database "$PLATFORM_DATABASE" 'SELECT version_num FROM alembic_version')" = "$TARGET_PLATFORM_HEAD" ]] || fail "Platform clone did not reach operations head"

printf 'Running focused Platform tests and protected API smoke...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -v "$PWD/backend/tests:/app/tests:ro" backend python -B -m unittest discover -s tests -p 'test_platform*.py'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e SAAS_OPERATIONS_DATABASE_NAME="$LEGACY_DATABASE" \
  -e IDENTITY_DATABASE=legacy -e RESTAURANT_SERVICE_DATABASE=legacy -e REFERENCE_PROJECTOR_ENABLED=false \
  -v "$PWD/backend/tests:/app/tests:ro" backend sh -c '
    set -eu; database_server="${DATABASE_URL%/*}"; export DATABASE_URL="$database_server/$SAAS_OPERATIONS_DATABASE_NAME"
    export PLATFORM_DATABASE_URL="$DATABASE_URL" RESTAURANT_DATABASE_URL="$DATABASE_URL"
    python -m tests.smoke_platform_operations_api
  '

company_id="$(psql_database "$LEGACY_DATABASE" 'SELECT id FROM companies ORDER BY created_at LIMIT 1')"
[[ -n "$company_id" ]] || fail "isolated legacy clone has no Company fixture"
printf 'Creating and restore-drilling an isolated three-boundary backup...\n'
backup_output="$(P5_LEGACY_DATABASE_NAME="$LEGACY_DATABASE" P5_PLATFORM_DATABASE_NAME="$PLATFORM_DATABASE" P5_RESTAURANT_DATABASE_NAME="$OPS_DATABASE" P5_TENANT_BACKUP_ROOT="$backup_root" scripts/backup-tenant-boundaries.sh --company-id "$company_id" --reason "SaaS operations isolated recovery gate")"
printf '%s\n' "$backup_output"
backup_dir="$(printf '%s\n' "$backup_output" | sed -n 's/^Tenant boundary backup completed: //p')"
[[ -n "$backup_dir" ]] || fail "could not resolve isolated backup directory"
P5_TENANT_DRILL_CLEANUP=1 scripts/restore-tenant-boundaries-drill.sh --yes "$backup_dir"
restore_evidence="$(find "$backup_dir" -maxdepth 1 -type f -name 'recovery-evidence-*.txt' | sort | tail -n 1)"
[[ -n "$restore_evidence" ]] || fail "restore evidence is missing"

printf '{"status":"ok","version":"test"}\n' > "$artifact_dir/health-ready.json"
RESILIENCE_HEALTH_SOURCE_FILE="$artifact_dir/health-ready.json" \
RESILIENCE_ALLOW_OFFLINE_HEALTH=1 \
RESILIENCE_BACKUP_ROOT="$backup_root" \
RESILIENCE_RESTORE_EVIDENCE_FILE="$restore_evidence" \
RESILIENCE_EVIDENCE_FILE="$artifact_dir/resilience.json" \
scripts/monitor-production-resilience.sh

printf 'Importing sanitized scheduler evidence...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e SAAS_OPERATIONS_DATABASE_NAME="$LEGACY_DATABASE" \
  -e IDENTITY_DATABASE=legacy -e REFERENCE_PROJECTOR_ENABLED=false \
  -v "$artifact_dir:/evidence:ro" backend sh -c '
    set -eu; database_server="${DATABASE_URL%/*}"; export DATABASE_URL="$database_server/$SAAS_OPERATIONS_DATABASE_NAME"
    export PLATFORM_DATABASE_URL="$DATABASE_URL" RESTAURANT_DATABASE_URL="$DATABASE_URL"
    python -m app.utils.capture_platform_operations --evidence-file /evidence/resilience.json
  ' > "$artifact_dir/scheduler-import.json"

[[ "$(psql_database "$LEGACY_DATABASE" 'SELECT count(*) FROM platform_operations_snapshots')" -ge "3" ]] || fail "scheduler evidence was not stored"
[[ "$(psql_database "$LEGACY_DATABASE" "SELECT count(*) FROM platform_operations_snapshots WHERE component_checks::text ~ '/secure|postgresql://|password=' OR alert_codes::text ~ '/secure|postgresql://|password='")" = "0" ]] || fail "operations table contains sensitive evidence"

legacy_after="$(fingerprint POSTGRES_DB)"
platform_after="$(fingerprint PLATFORM_POSTGRES_DB)"
restaurant_after="$(fingerprint RESTAURANT_POSTGRES_DB)"
[[ "$legacy_before" = "$legacy_after" ]] || fail "live legacy source changed"
[[ "$platform_before" = "$platform_after" ]] || fail "live Platform source changed"
[[ "$restaurant_before" = "$restaurant_after" ]] || fail "live Restaurant source changed"

cat > "$artifact_dir/manifest.txt" <<EOF
scope=SAAS-PREP-OPERATIONS-05
timestamp=$timestamp
legacy_source=$legacy_before
platform_source=$platform_before
restaurant_source=$restaurant_before
legacy_target_head=$TARGET_LEGACY_HEAD
platform_target_head=$TARGET_PLATFORM_HEAD
focused_platform_tests=passed
operations_api_smoke=passed
public_health_sanitization_gate=passed
evidence_allowlist_and_idempotency_gate=passed
three_boundary_backup=$backup_dir
isolated_restore_drill=passed
scheduler_evidence_import=passed
live_sources_unchanged=true
temporary_database_cleanup=automatic
EOF
chmod 600 "$artifact_dir/manifest.txt" "$artifact_dir/resilience.json" "$artifact_dir/scheduler-import.json"
printf 'SaaS operations gate passed. Artifact: %s\n' "$artifact_dir/manifest.txt"
