#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_ROOT="${P2_SCOPE_BACKUP_ROOT:-backups}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSUME_YES=0
EXPECTED_LEGACY_HEAD="6b7c8d9e0f12"
EXPECTED_PLATFORM_HEAD="p1platform0003"
TARGET_LEGACY_HEAD="p2scope0001"
TARGET_PLATFORM_HEAD="p2platform0004"
LEGACY_PREFIX="restaurant_p2_scope_"
PLATFORM_PREFIX="restaurant_p2_platform_"
LEGACY_DATABASE=""
PLATFORM_DATABASE=""
TEMP_DIR=""

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

drop_temporary_database() {
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
  [[ -z "$LEGACY_DATABASE" ]] || drop_temporary_database "$LEGACY_DATABASE" "$LEGACY_PREFIX"
  [[ -z "$PLATFORM_DATABASE" ]] || drop_temporary_database "$PLATFORM_DATABASE" "$PLATFORM_PREFIX"
  if [[ -n "$TEMP_DIR" ]]; then
    case "$TEMP_DIR" in
      /private/tmp/restaurant-p2-scope.*|/tmp/restaurant-p2-scope.*)
        rm -rf "$TEMP_DIR"
        ;;
    esac
  fi
}

trap cleanup EXIT HUP INT TERM

cd "$PROJECT_DIR"

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --yes)
      ASSUME_YES=1
      shift
      ;;
    --backup-root)
      [[ "$#" -ge 2 ]] || fail "--backup-root requires a path"
      BACKUP_ROOT="$2"
      shift 2
      ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[[ "$ASSUME_YES" = "1" ]] \
  || fail "this rehearsal creates and drops isolated temporary databases; pass --yes"
[[ -f "$COMPOSE_FILE" ]] || fail "compose file not found: $COMPOSE_FILE"

psql_boundary() {
  database_env="$1"
  query="$2"
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
    case "$1" in
      POSTGRES_DB) database_name="$POSTGRES_DB" ;;
      PLATFORM_POSTGRES_DB) database_name="$PLATFORM_POSTGRES_DB" ;;
      *) exit 2 ;;
    esac
    psql -U "$POSTGRES_USER" -d "$database_name" -tAc "$2"
  ' sh "$database_env" "$query" | tr -d '[:space:]'
}

psql_database() {
  database_name="$1"
  query="$2"
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
    psql -U "$POSTGRES_USER" -d "$1" -tAc "$2"
  ' sh "$database_name" "$query" | tr -d '[:space:]'
}

legacy_fingerprint() {
  psql_boundary POSTGRES_DB '
    SELECT concat(
      (SELECT version_num FROM alembic_version), chr(58),
      (SELECT count(*) FROM companies), chr(58),
      (SELECT count(*) FROM brands), chr(58),
      (SELECT count(*) FROM branches), chr(58),
      (SELECT count(*) FROM users), chr(58),
      (SELECT count(*) FROM roles), chr(58),
      (SELECT count(*) FROM dining_sessions), chr(58),
      (SELECT count(*) FROM sale_orders)
    )
  '
}

platform_fingerprint() {
  psql_boundary PLATFORM_POSTGRES_DB '
    SELECT concat(
      (SELECT version_num FROM alembic_version), chr(58),
      (SELECT schema_contract_version FROM database_boundary_metadata WHERE boundary_name = '\''platform_core'\''), chr(58),
      (SELECT count(*) FROM companies), chr(58),
      (SELECT count(*) FROM brands), chr(58),
      (SELECT count(*) FROM branches), chr(58),
      (SELECT count(*) FROM users), chr(58),
      (SELECT count(*) FROM roles)
    )
  '
}

printf 'Starting local PostgreSQL and Redis services...\n'
docker compose -f "$COMPOSE_FILE" up -d postgres redis >/dev/null
tries=0
until docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1))
  [[ "$tries" -lt 30 ]] || fail "postgres service did not become ready"
  sleep 1
done

legacy_head="$(psql_boundary POSTGRES_DB 'SELECT version_num FROM alembic_version')"
platform_head="$(psql_boundary PLATFORM_POSTGRES_DB 'SELECT version_num FROM alembic_version')"
[[ "$legacy_head" = "$EXPECTED_LEGACY_HEAD" ]] || fail "unexpected legacy head: $legacy_head"
[[ "$platform_head" = "$EXPECTED_PLATFORM_HEAD" ]] || fail "unexpected Platform head: $platform_head"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
database_suffix="$(date -u +%Y%m%d%H%M%S)$$"
LEGACY_DATABASE="${LEGACY_PREFIX}${database_suffix}"
PLATFORM_DATABASE="${PLATFORM_PREFIX}${database_suffix}"
artifact_dir="${BACKUP_ROOT%/}/p2-scope-assignments-02-${timestamp}"
mkdir -p "$artifact_dir"
TEMP_DIR="$(mktemp -d /private/tmp/restaurant-p2-scope.XXXXXX 2>/dev/null \
  || mktemp -d /tmp/restaurant-p2-scope.XXXXXX)"

legacy_before="$(legacy_fingerprint)"
platform_before="$(platform_fingerprint)"

printf 'Cloning legacy and Platform sources into isolated databases...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$TEMP_DIR/legacy.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB"' > "$TEMP_DIR/platform.dump"
for database_name in "$LEGACY_DATABASE" "$PLATFORM_DATABASE"; do
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$database_name"
done
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$LEGACY_DATABASE" \
  < "$TEMP_DIR/legacy.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$PLATFORM_DATABASE" \
  < "$TEMP_DIR/platform.dump"

printf 'Building current backend image...\n'
docker compose -f "$COMPOSE_FILE" build backend >/dev/null

printf 'Rehearsing legacy upgrade, downgrade, and re-upgrade...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e P2_LEGACY_DATABASE_NAME="$LEGACY_DATABASE" \
  backend sh -c '
    set -eu
    case "$P2_LEGACY_DATABASE_NAME" in restaurant_p2_scope_[0-9]*) ;; *) exit 2 ;; esac
    database_server="${DATABASE_URL%/*}"
    export DATABASE_URL="$database_server/$P2_LEGACY_DATABASE_NAME"
    alembic upgrade p2scope0001
    alembic downgrade 6b7c8d9e0f12
    alembic upgrade p2scope0001
  '
[[ "$(psql_database "$LEGACY_DATABASE" 'SELECT version_num FROM alembic_version')" = "$TARGET_LEGACY_HEAD" ]] \
  || fail "legacy temporary database did not reach $TARGET_LEGACY_HEAD"
[[ "$(psql_database "$LEGACY_DATABASE" "SELECT count(*) FROM information_schema.columns WHERE table_name = 'roles' AND column_name = 'allowed_scope_types'")" = "1" ]] \
  || fail "legacy role scope column is missing"
[[ "$(psql_database "$LEGACY_DATABASE" "SELECT count(*) FROM information_schema.tables WHERE table_name = 'staff_role_assignments'")" = "1" ]] \
  || fail "legacy assignment table is missing"

printf 'Rehearsing Platform upgrade, downgrade, and re-upgrade...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e P2_PLATFORM_DATABASE_NAME="$PLATFORM_DATABASE" \
  backend sh -c '
    set -eu
    case "$P2_PLATFORM_DATABASE_NAME" in restaurant_p2_platform_[0-9]*) ;; *) exit 2 ;; esac
    database_server="${PLATFORM_DATABASE_URL%/*}"
    export PLATFORM_DATABASE_URL="$database_server/$P2_PLATFORM_DATABASE_NAME"
    alembic -c alembic-boundaries.ini -n platform upgrade p2platform0004
    alembic -c alembic-boundaries.ini -n platform downgrade p1platform0003
    alembic -c alembic-boundaries.ini -n platform upgrade p2platform0004
  '
[[ "$(psql_database "$PLATFORM_DATABASE" 'SELECT version_num FROM alembic_version')" = "$TARGET_PLATFORM_HEAD" ]] \
  || fail "Platform temporary database did not reach $TARGET_PLATFORM_HEAD"
[[ "$(psql_database "$PLATFORM_DATABASE" "SELECT schema_contract_version FROM database_boundary_metadata WHERE boundary_name = 'platform_core'")" = "2" ]] \
  || fail "Platform schema contract version is not 2"
[[ "$(psql_database "$PLATFORM_DATABASE" "SELECT count(*) FROM information_schema.tables WHERE table_name = 'staff_role_assignments'")" = "1" ]] \
  || fail "Platform assignment table is missing"

printf 'Running isolated assignment and authorization API matrix...\n'
scope_output="$(docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e P2_SCOPE_DATABASE_NAME="$LEGACY_DATABASE" \
  -e P2_PLATFORM_DATABASE_NAME="$PLATFORM_DATABASE" \
  -e IDENTITY_DATABASE=legacy \
  -e RESTAURANT_SERVICE_DATABASE=legacy \
  -e REFERENCE_PROJECTOR_ENABLED=false \
  -v "$PWD/backend/tests:/app/tests:ro" \
  backend sh -c '
    set -eu
    case "$P2_SCOPE_DATABASE_NAME" in restaurant_p2_scope_[0-9]*) ;; *) exit 2 ;; esac
    case "$P2_PLATFORM_DATABASE_NAME" in restaurant_p2_platform_[0-9]*) ;; *) exit 2 ;; esac
    database_server="${DATABASE_URL%/*}"
    platform_server="${PLATFORM_DATABASE_URL%/*}"
    export DATABASE_URL="$database_server/$P2_SCOPE_DATABASE_NAME"
    export PLATFORM_DATABASE_URL="$platform_server/$P2_PLATFORM_DATABASE_NAME"
    export RESTAURANT_DATABASE_URL="$DATABASE_URL"
    export PYTHONPATH=/app
    python /app/tests/smoke_staff_scope_api.py
  ')"
printf '%s\n' "$scope_output"
for assertion in \
  p2_scope_company_brand_branch=ok \
  p2_scope_station_isolation=ok \
  p2_scope_multi_role_union=ok \
  p2_scope_audit_revoke=ok \
  p2_scope_kitchen_boundary=ok; do
  printf '%s\n' "$scope_output" | grep -F "$assertion" >/dev/null \
    || fail "missing API assertion: $assertion"
done

legacy_after="$(legacy_fingerprint)"
platform_after="$(platform_fingerprint)"
[[ "$legacy_after" = "$legacy_before" ]] || fail "live legacy fingerprint changed"
[[ "$platform_after" = "$platform_before" ]] || fail "live Platform fingerprint changed"

cat > "$artifact_dir/manifest.txt" <<EOF
scope_id=P2-SCOPE-ASSIGNMENTS-02
rehearsal_status=verified
snapshot_timestamp_utc=$timestamp
source_legacy_head=$legacy_head
source_platform_head=$platform_head
temporary_legacy_head=$TARGET_LEGACY_HEAD
temporary_platform_head=$TARGET_PLATFORM_HEAD
platform_schema_contract_version=2
legacy_upgrade_downgrade_reupgrade=true
platform_upgrade_downgrade_reupgrade=true
company_brand_branch_matrix=true
station_ticket_isolation=true
multi_role_context_union=true
assignment_audit_revoke=true
kitchen_privilege_boundary=true
runtime_identity_database=legacy
runtime_restaurant_service_database=legacy
runtime_reference_projector_enabled=false
live_legacy_fingerprint_before=$legacy_before
live_legacy_fingerprint_after=$legacy_after
live_platform_fingerprint_before=$platform_before
live_platform_fingerprint_after=$platform_after
temporary_database_cleanup=automatic
EOF

printf 'Phase 2 scope assignment rehearsal passed: %s\n' "$artifact_dir"
