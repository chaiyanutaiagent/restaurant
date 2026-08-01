#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ARTIFACT_ROOT="${P3_OFFLINE_ARTIFACT_ROOT:-/private/tmp/restaurant-p3-artifacts}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LEGACY_PREFIX="restaurant_p3_offline_"
PLATFORM_PREFIX="restaurant_p3_offline_platform_"
LEGACY_DATABASE=""
PLATFORM_DATABASE=""
TEMP_DIR=""
ASSUME_YES=0

fail() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

drop_temporary_database() {
  local database_name="$1" expected_prefix="$2"
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
  [[ -z "$LEGACY_DATABASE" ]] || drop_temporary_database "$LEGACY_DATABASE" "$LEGACY_PREFIX"
  [[ -z "$PLATFORM_DATABASE" ]] || drop_temporary_database "$PLATFORM_DATABASE" "$PLATFORM_PREFIX"
  if [[ -n "$TEMP_DIR" ]]; then
    case "$TEMP_DIR" in
      /private/tmp/restaurant-p3-offline.*|/tmp/restaurant-p3-offline.*) rm -rf "$TEMP_DIR" ;;
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
  local database_env="$1" query="$2"
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
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$1" -tAc "$2"' sh "$1" "$2" | tr -d '[:space:]'
}

legacy_fingerprint() {
  psql_boundary POSTGRES_DB 'SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT count(*) FROM companies), chr(58), (SELECT count(*) FROM branches), chr(58), (SELECT count(*) FROM users), chr(58), (SELECT count(*) FROM audit_logs))'
}
platform_fingerprint() {
  psql_boundary PLATFORM_POSTGRES_DB 'SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT schema_contract_version FROM database_boundary_metadata WHERE boundary_name = '\''platform_core'\''), chr(58), (SELECT count(*) FROM companies), chr(58), (SELECT count(*) FROM users), chr(58), (SELECT count(*) FROM roles))'
}
restaurant_fingerprint() {
  psql_boundary RESTAURANT_POSTGRES_DB 'SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT schema_contract_version FROM database_boundary_metadata WHERE boundary_name = '\''restaurant'\''), chr(58), (SELECT count(*) FROM branches), chr(58), (SELECT count(*) FROM sale_orders), chr(58), (SELECT count(*) FROM payments))'
}

printf 'Starting local PostgreSQL and Redis services...\n'
docker compose -f "$COMPOSE_FILE" up -d postgres redis >/dev/null
tries=0
until docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1)); [[ "$tries" -lt 30 ]] || fail "postgres service did not become ready"; sleep 1
done
[[ "$(psql_boundary POSTGRES_DB 'SELECT version_num FROM alembic_version')" = "6b7c8d9e0f12" ]] || fail "unexpected legacy source head"
[[ "$(psql_boundary PLATFORM_POSTGRES_DB 'SELECT version_num FROM alembic_version')" = "p1platform0003" ]] || fail "unexpected Platform source head"
[[ "$(psql_boundary RESTAURANT_POSTGRES_DB 'SELECT version_num FROM alembic_version')" = "p1restaurant0003" ]] || fail "unexpected Restaurant source head"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
suffix="$(date -u +%Y%m%d%H%M%S)$$"
LEGACY_DATABASE="${LEGACY_PREFIX}${suffix}"
PLATFORM_DATABASE="${PLATFORM_PREFIX}${suffix}"
artifact_dir="${ARTIFACT_ROOT%/}/p3-offline-authorization-03-${timestamp}"
mkdir -p "$artifact_dir"
TEMP_DIR="$(mktemp -d /private/tmp/restaurant-p3-offline.XXXXXX 2>/dev/null || mktemp -d /tmp/restaurant-p3-offline.XXXXXX)"
legacy_before="$(legacy_fingerprint)"; platform_before="$(platform_fingerprint)"; restaurant_before="$(restaurant_fingerprint)"

printf 'Cloning Identity sources into isolated databases...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$TEMP_DIR/legacy.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB"' > "$TEMP_DIR/platform.dump"
for database_name in "$LEGACY_DATABASE" "$PLATFORM_DATABASE"; do
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$database_name"
done
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$LEGACY_DATABASE" < "$TEMP_DIR/legacy.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$PLATFORM_DATABASE" < "$TEMP_DIR/platform.dump"

printf 'Building backend and applying existing Phase 3 Identity migrations to clones...\n'
docker compose -f "$COMPOSE_FILE" build backend >/dev/null
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -e P3_OFFLINE_DATABASE_NAME="$LEGACY_DATABASE" backend sh -c '
  set -eu; case "$P3_OFFLINE_DATABASE_NAME" in restaurant_p3_offline_[0-9]*) ;; *) exit 2 ;; esac
  export DATABASE_URL="${DATABASE_URL%/*}/$P3_OFFLINE_DATABASE_NAME"; alembic upgrade p3device0003
'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -e P3_OFFLINE_PLATFORM_DATABASE_NAME="$PLATFORM_DATABASE" backend sh -c '
  set -eu; case "$P3_OFFLINE_PLATFORM_DATABASE_NAME" in restaurant_p3_offline_platform_[0-9]*) ;; *) exit 2 ;; esac
  export PLATFORM_DATABASE_URL="${PLATFORM_DATABASE_URL%/*}/$P3_OFFLINE_PLATFORM_DATABASE_NAME"
  alembic -c alembic-boundaries.ini -n platform upgrade p3platform0006
'
[[ "$(psql_database "$LEGACY_DATABASE" 'SELECT version_num FROM alembic_version')" = "p3device0003" ]] || fail "legacy clone migration failed"
[[ "$(psql_database "$PLATFORM_DATABASE" 'SELECT version_num FROM alembic_version')" = "p3platform0006" ]] || fail "Platform clone migration failed"

printf 'Running signed offline authorization API gate...\n'
smoke_output=""
if ! smoke_output="$(docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e P3_OFFLINE_DATABASE_NAME="$LEGACY_DATABASE" \
  -e P3_OFFLINE_PLATFORM_DATABASE_NAME="$PLATFORM_DATABASE" \
  -e IDENTITY_DATABASE=legacy -e RESTAURANT_SERVICE_DATABASE=legacy -e REFERENCE_PROJECTOR_ENABLED=false \
  -v "$PWD/backend/tests:/app/tests:ro" backend sh -c '
    set -eu
    export DATABASE_URL="${DATABASE_URL%/*}/$P3_OFFLINE_DATABASE_NAME"
    export PLATFORM_DATABASE_URL="${PLATFORM_DATABASE_URL%/*}/$P3_OFFLINE_PLATFORM_DATABASE_NAME"
    export PYTHONPATH=/app
    python /app/tests/smoke_offline_authorization_api.py
  ' 2>&1)"; then
  printf '%s\n' "$smoke_output"; fail "offline authorization API gate failed"
fi
printf '%s\n' "$smoke_output"
printf '%s\n' "$smoke_output" | grep -F 'p3_offline_authorization_api=ok' >/dev/null || fail "offline authorization smoke assertion is missing"

legacy_after="$(legacy_fingerprint)"; platform_after="$(platform_fingerprint)"; restaurant_after="$(restaurant_fingerprint)"
[[ "$legacy_after" = "$legacy_before" ]] || fail "live legacy fingerprint changed"
[[ "$platform_after" = "$platform_before" ]] || fail "live Platform fingerprint changed"
[[ "$restaurant_after" = "$restaurant_before" ]] || fail "live Restaurant fingerprint changed"
cat > "$artifact_dir/manifest.txt" <<EOF
scope_id=P3-OFFLINE-AUTHORIZATION-03
rehearsal_status=verified
snapshot_timestamp_utc=$timestamp
signed_expiring_authorization=true
staff_company_branch_shift_location_binding=true
counter_device_binding=true
per_order_needs_review=true
legacy_durable_queue_preserved=true
revocation_timing_enforced=true
new_schema_migration=false
live_legacy_fingerprint_before=$legacy_before
live_legacy_fingerprint_after=$legacy_after
live_platform_fingerprint_before=$platform_before
live_platform_fingerprint_after=$platform_after
live_restaurant_fingerprint_before=$restaurant_before
live_restaurant_fingerprint_after=$restaurant_after
temporary_database_cleanup=automatic
EOF
printf 'Phase 3 offline authorization rehearsal passed: %s\n' "$artifact_dir"
