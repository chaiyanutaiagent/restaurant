#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_ROOT="${PHASE1_GATE_BACKUP_ROOT:-backups}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSUME_YES=0
EXPECTED_LEGACY_HEAD="6b7c8d9e0f12"
EXPECTED_PLATFORM_HEAD="p1platform0003"
EXPECTED_RESTAURANT_HEAD="p1restaurant0003"
GATE_DATABASE_PREFIX="restaurant_p1_gate_"
GATE_DATABASE=""
TEMP_DIR=""

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

cleanup() {
  if [[ -n "$GATE_DATABASE" ]]; then
    case "$GATE_DATABASE" in
      ${GATE_DATABASE_PREFIX}[0-9]*)
        docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
          psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
            -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '\''$1'\'' AND pid <> pg_backend_pid()" >/dev/null
          dropdb --if-exists -U "$POSTGRES_USER" "$1"
        ' sh "$GATE_DATABASE" >/dev/null 2>&1 || true
        ;;
    esac
  fi
  if [[ -n "$TEMP_DIR" ]]; then
    case "$TEMP_DIR" in
      /private/tmp/restaurant-p1-gate.*|/tmp/restaurant-p1-gate.*)
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

[[ "$ASSUME_YES" = "1" ]] || fail "this gate creates and drops an isolated temporary database; pass --yes"
[[ -f "$COMPOSE_FILE" ]] || fail "compose file not found: $COMPOSE_FILE"

source_fingerprint() {
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "
      SELECT concat(
        (SELECT count(*) FROM companies), chr(58),
        (SELECT count(*) FROM brands), chr(58),
        (SELECT count(*) FROM branches), chr(58),
        (SELECT count(*) FROM users), chr(58),
        (SELECT count(*) FROM dining_tables), chr(58),
        (SELECT count(*) FROM dining_sessions), chr(58),
        (SELECT count(*) FROM sale_orders)
      )
    "
  ' | tr -d '[:space:]'
}

psql_boundary_value() {
  database_env_name="$1"
  query="$2"
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
    case "$1" in
      POSTGRES_DB) database_name="$POSTGRES_DB" ;;
      PLATFORM_POSTGRES_DB) database_name="$PLATFORM_POSTGRES_DB" ;;
      RESTAURANT_POSTGRES_DB) database_name="$RESTAURANT_POSTGRES_DB" ;;
      *) exit 2 ;;
    esac
    psql -U "$POSTGRES_USER" -d "$database_name" -tAc "$2"
  ' sh "$database_env_name" "$query" | tr -d '[:space:]'
}

printf 'Starting local database boundary services...\n'
docker compose -f "$COMPOSE_FILE" up -d postgres redis >/dev/null
tries=0
until docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1))
  [[ "$tries" -lt 30 ]] || fail "postgres service did not become ready"
  sleep 1
done

legacy_head="$(psql_boundary_value POSTGRES_DB 'SELECT version_num FROM alembic_version')"
platform_head="$(psql_boundary_value PLATFORM_POSTGRES_DB 'SELECT version_num FROM alembic_version')"
restaurant_head="$(psql_boundary_value RESTAURANT_POSTGRES_DB 'SELECT version_num FROM alembic_version')"
[[ "$legacy_head" = "$EXPECTED_LEGACY_HEAD" ]] || fail "unexpected legacy head: $legacy_head"
[[ "$platform_head" = "$EXPECTED_PLATFORM_HEAD" ]] || fail "unexpected Platform head: $platform_head"
[[ "$restaurant_head" = "$EXPECTED_RESTAURANT_HEAD" ]] || fail "unexpected Restaurant head: $restaurant_head"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
database_timestamp="$(date -u +%Y%m%d%H%M%S)"
GATE_DATABASE="${GATE_DATABASE_PREFIX}${database_timestamp}"
gate_dir="${BACKUP_ROOT%/}/p1-phase-gate-08-${timestamp}"
mkdir -p "$gate_dir"
TEMP_DIR="$(mktemp -d /private/tmp/restaurant-p1-gate.XXXXXX 2>/dev/null || mktemp -d /tmp/restaurant-p1-gate.XXXXXX)"

source_before="$(source_fingerprint)"
printf 'Cloning legacy source into isolated gate database %s...\n' "$GATE_DATABASE"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$TEMP_DIR/legacy-source.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$GATE_DATABASE"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$GATE_DATABASE" \
  < "$TEMP_DIR/legacy-source.dump"

printf 'Building the current backend and running the tenant isolation matrix...\n'
docker compose -f "$COMPOSE_FILE" build backend >/dev/null
gate_output="$(docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e P1_GATE_DATABASE_NAME="$GATE_DATABASE" \
  -e IDENTITY_DATABASE=legacy \
  -e RESTAURANT_SERVICE_DATABASE=legacy \
  -e REFERENCE_PROJECTOR_ENABLED=false \
  -v "$PWD/backend/tests:/app/tests:ro" \
  backend sh -c '
    set -eu
    case "$P1_GATE_DATABASE_NAME" in restaurant_p1_gate_[0-9]*) ;; *) exit 2 ;; esac
    database_server="${DATABASE_URL%/*}"
    export DATABASE_URL="$database_server/$P1_GATE_DATABASE_NAME"
    export PLATFORM_DATABASE_URL="$DATABASE_URL"
    export RESTAURANT_DATABASE_URL="$DATABASE_URL"
    export PYTHONPATH=/app
    python /app/tests/smoke_phase1_gate_api.py
  ')"
printf '%s\n' "$gate_output"
for assertion in \
  phase1_tenant_isolation=ok \
  phase1_branch_assignment=ok \
  phase1_business_type_guard=ok \
  phase1_legacy_routes=ok; do
  printf '%s\n' "$gate_output" | grep -F "$assertion" >/dev/null \
    || fail "missing gate assertion: $assertion"
done
retained_data="$(printf '%s\n' "$gate_output" | sed -n 's/^retained_data=//p')"
[[ -n "$retained_data" ]] || fail "retained data evidence is missing"

source_after="$(source_fingerprint)"
[[ "$source_after" = "$source_before" ]] \
  || fail "live legacy row-count fingerprint changed during isolated gate"

printf 'Backing up and restore-drilling both physical boundary targets...\n'
boundary_output="$(scripts/backup-local-database-boundary.sh "$gate_dir/boundary")"
printf '%s\n' "$boundary_output"
boundary_backup_dir="$(printf '%s\n' "$boundary_output" | sed -n 's/^Boundary backup completed: //p')"
[[ -n "$boundary_backup_dir" ]] || fail "could not resolve boundary backup directory"
BOUNDARY_DRILL_SUFFIX="p1gate08_${database_timestamp}" \
BOUNDARY_DRILL_CLEANUP=1 \
  scripts/restore-local-database-boundary-drill.sh "$boundary_backup_dir"

cat > "$gate_dir/manifest.txt" <<EOF
scope_id=P1-PHASE-GATE-08
gate_status=verified
snapshot_timestamp_utc=$timestamp
legacy_migration_head=$legacy_head
platform_migration_head=$platform_head
restaurant_migration_head=$restaurant_head
temporary_gate_database=$GATE_DATABASE
temporary_gate_database_cleanup=automatic
live_source_fingerprint_before=$source_before
live_source_fingerprint_after=$source_after
tenant_isolation=true
branch_assignment_isolation=true
business_type_guard=true
canonical_bkk01_data_retained=true
canonical_bkk01_retained_data=$retained_data
legacy_routes=true
boundary_backup=$boundary_backup_dir
boundary_restore_drill=true
EOF

printf 'Phase 1 gate rehearsal passed: %s\n' "$gate_dir"
