#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
export RESTAURANT_BACKEND_IMAGE="${SAAS_USAGE_BACKEND_IMAGE:-restaurant-pos-dev-backend:saas-usage-gate}"
ARTIFACT_ROOT="${SAAS_USAGE_ARTIFACT_ROOT:-/private/tmp/restaurant-saas-artifacts}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_LEGACY_HEAD="6b7c8d9e0f12"
EXPECTED_PLATFORM_HEAD="p1platform0003"
TARGET_LEGACY_HEAD="p7usage0009"
TARGET_PLATFORM_HEAD="p7platform0011"
LEGACY_PREFIX="restaurant_saas_usage_"
PLATFORM_PREFIX="restaurant_saas_usage_platform_"
ASSUME_YES=0
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
      /private/tmp/restaurant-saas-usage.*|/tmp/restaurant-saas-usage.*) rm -rf "$TEMP_DIR" ;;
    esac
  fi
}

trap cleanup EXIT HUP INT TERM

cd "$PROJECT_DIR"
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

[[ "$ASSUME_YES" = "1" ]] || fail "this rehearsal creates and drops isolated temporary databases; pass --yes"
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

fingerprint() {
  database_env="$1"
  psql_boundary "$database_env" '
    SELECT concat(
      (SELECT version_num FROM alembic_version), chr(58),
      (SELECT count(*) FROM companies), chr(58),
      (SELECT count(*) FROM users), chr(58),
      (SELECT count(*) FROM audit_logs)
    )
  '
}

printf 'Starting isolated SaaS Platform usage gate...\n'
docker compose -f "$COMPOSE_FILE" up -d postgres redis >/dev/null
tries=0
until docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1))
  [[ "$tries" -lt 30 ]] || fail "postgres service did not become ready"
  sleep 1
done

[[ "$(psql_boundary POSTGRES_DB 'SELECT version_num FROM alembic_version')" = "$EXPECTED_LEGACY_HEAD" ]] || fail "unexpected live legacy head"
[[ "$(psql_boundary PLATFORM_POSTGRES_DB 'SELECT version_num FROM alembic_version')" = "$EXPECTED_PLATFORM_HEAD" ]] || fail "unexpected live Platform head"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
database_suffix="$(date -u +%Y%m%d%H%M%S)$$"
LEGACY_DATABASE="${LEGACY_PREFIX}${database_suffix}"
PLATFORM_DATABASE="${PLATFORM_PREFIX}${database_suffix}"
artifact_dir="${ARTIFACT_ROOT%/}/saas-tenant-usage-03-${timestamp}"
mkdir -p "$artifact_dir"
TEMP_DIR="$(mktemp -d /private/tmp/restaurant-saas-usage.XXXXXX 2>/dev/null || mktemp -d /tmp/restaurant-saas-usage.XXXXXX)"

legacy_before="$(fingerprint POSTGRES_DB)"
platform_before="$(fingerprint PLATFORM_POSTGRES_DB)"

printf 'Cloning live identity sources into isolated databases...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$TEMP_DIR/legacy.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB"' > "$TEMP_DIR/platform.dump"
for database_name in "$LEGACY_DATABASE" "$PLATFORM_DATABASE"; do
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$database_name"
done
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$LEGACY_DATABASE" < "$TEMP_DIR/legacy.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$PLATFORM_DATABASE" < "$TEMP_DIR/platform.dump"

printf 'Building isolated SaaS usage backend image...\n'
docker compose -f "$COMPOSE_FILE" build backend >/dev/null

printf 'Rehearsing legacy usage upgrade/downgrade/re-upgrade...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -e SAAS_USAGE_DATABASE_NAME="$LEGACY_DATABASE" backend sh -c '
  set -eu
  case "$SAAS_USAGE_DATABASE_NAME" in restaurant_saas_usage_[0-9]*) ;; *) exit 2 ;; esac
  database_server="${DATABASE_URL%/*}"
  export DATABASE_URL="$database_server/$SAAS_USAGE_DATABASE_NAME"
  alembic upgrade p7usage0009
  alembic downgrade p6auth0008
  alembic upgrade p7usage0009
'

printf 'Rehearsing Platform-core usage upgrade/downgrade/re-upgrade...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -e SAAS_USAGE_PLATFORM_DATABASE_NAME="$PLATFORM_DATABASE" backend sh -c '
  set -eu
  case "$SAAS_USAGE_PLATFORM_DATABASE_NAME" in restaurant_saas_usage_platform_[0-9]*) ;; *) exit 2 ;; esac
  database_server="${PLATFORM_DATABASE_URL%/*}"
  export PLATFORM_DATABASE_URL="$database_server/$SAAS_USAGE_PLATFORM_DATABASE_NAME"
  alembic -c alembic-boundaries.ini -n platform upgrade p7platform0011
  alembic -c alembic-boundaries.ini -n platform downgrade p6platform0010
  alembic -c alembic-boundaries.ini -n platform upgrade p7platform0011
'

[[ "$(psql_database "$LEGACY_DATABASE" 'SELECT version_num FROM alembic_version')" = "$TARGET_LEGACY_HEAD" ]] || fail "legacy clone did not reach SaaS usage head"
[[ "$(psql_database "$PLATFORM_DATABASE" 'SELECT version_num FROM alembic_version')" = "$TARGET_PLATFORM_HEAD" ]] || fail "Platform clone did not reach SaaS usage head"
for database_name in "$LEGACY_DATABASE" "$PLATFORM_DATABASE"; do
  [[ "$(psql_database "$database_name" "SELECT count(*) FROM information_schema.tables WHERE table_name = 'platform_tenant_usage_snapshots'")" = "1" ]] || fail "Platform usage snapshot table is missing from $database_name"
  [[ "$(psql_database "$database_name" "SELECT count(*) FROM information_schema.columns WHERE table_name = 'platform_tenant_usage_snapshots'")" = "15" ]] || fail "Platform usage snapshot schema is incomplete in $database_name"
done

printf 'Running focused Platform tests...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -v "$PWD/backend/tests:/app/tests:ro" backend python -B -m unittest discover -s tests -p 'test_platform*.py'

printf 'Running isolated Platform usage API smoke...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e SAAS_USAGE_DATABASE_NAME="$LEGACY_DATABASE" \
  -e IDENTITY_DATABASE=legacy \
  -e RESTAURANT_SERVICE_DATABASE=legacy \
  -e REFERENCE_PROJECTOR_ENABLED=false \
  -v "$PWD/backend/tests:/app/tests:ro" \
  backend sh -c '
    set -eu
    database_server="${DATABASE_URL%/*}"
    export DATABASE_URL="$database_server/$SAAS_USAGE_DATABASE_NAME"
    export PLATFORM_DATABASE_URL="$DATABASE_URL"
    export RESTAURANT_DATABASE_URL="$DATABASE_URL"
    python -m tests.smoke_platform_usage_api
  '

legacy_after="$(fingerprint POSTGRES_DB)"
platform_after="$(fingerprint PLATFORM_POSTGRES_DB)"
[[ "$legacy_before" = "$legacy_after" ]] || fail "live legacy source changed: $legacy_before -> $legacy_after"
[[ "$platform_before" = "$platform_after" ]] || fail "live Platform source changed: $platform_before -> $platform_after"

cat > "$artifact_dir/manifest.txt" <<EOF
scope=SAAS-PREP-TENANT-USAGE-03
timestamp=$timestamp
legacy_source=$legacy_before
platform_source=$platform_before
legacy_target_head=$TARGET_LEGACY_HEAD
platform_target_head=$TARGET_PLATFORM_HEAD
focused_platform_tests=passed
platform_usage_api_smoke=passed
aggregate_only_gate=passed
snapshot_idempotency_gate=passed
company_isolation_gate=passed
live_sources_unchanged=true
temporary_database_cleanup=automatic
EOF

printf 'SaaS Platform usage gate passed. Artifact: %s\n' "$artifact_dir/manifest.txt"
