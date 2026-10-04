#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
export RESTAURANT_BACKEND_IMAGE="${SAAS_ROUTING_BACKEND_IMAGE:-restaurant-pos-dev-backend:saas-tenant-routing-gate}"
ARTIFACT_ROOT="${SAAS_ROUTING_ARTIFACT_ROOT:-/private/tmp/restaurant-saas-artifacts}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_LEGACY_HEAD="6b7c8d9e0f12"
EXPECTED_PLATFORM_HEAD="p1platform0003"
EXPECTED_RESTAURANT_HEAD="p1restaurant0003"
TARGET_LEGACY_HEAD="p12route0014"
TARGET_PLATFORM_HEAD="p12platform0016"
TARGET_RESTAURANT_HEAD="p6restaurant0007"
LEGACY_PREFIX="restaurant_saas_routing_"
PLATFORM_PREFIX="restaurant_saas_routing_platform_"
RESTAURANT_PREFIX="restaurant_saas_routing_restaurant_"
ASSUME_YES=0
LEGACY_DATABASE=""
PLATFORM_DATABASE=""
RESTAURANT_DATABASE=""

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
  [[ -z "$RESTAURANT_DATABASE" ]] || drop_database "$RESTAURANT_DATABASE" "$RESTAURANT_PREFIX"
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

printf 'Starting isolated SaaS Tenant routing gate...\n'
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
RESTAURANT_DATABASE="${RESTAURANT_PREFIX}${suffix}"
artifact_dir="${ARTIFACT_ROOT%/}/saas-tenant-routing-09-${timestamp}"
mkdir -p "$artifact_dir"

legacy_before="$(psql_boundary POSTGRES_DB 'SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT count(*) FROM companies))')"
platform_before="$(psql_boundary PLATFORM_POSTGRES_DB 'SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT count(*) FROM companies))')"
restaurant_before="$(psql_boundary RESTAURANT_POSTGRES_DB 'SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT count(*) FROM companies))')"

printf 'Cloning three database boundaries...\n'
for pair in \
  "POSTGRES_DB:$LEGACY_DATABASE" \
  "PLATFORM_POSTGRES_DB:$PLATFORM_DATABASE" \
  "RESTAURANT_POSTGRES_DB:$RESTAURANT_DATABASE"; do
  source_env="${pair%%:*}"
  target_database="${pair#*:}"
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
    case "$1" in
      POSTGRES_DB) source_database="$POSTGRES_DB" ;;
      PLATFORM_POSTGRES_DB) source_database="$PLATFORM_POSTGRES_DB" ;;
      RESTAURANT_POSTGRES_DB) source_database="$RESTAURANT_POSTGRES_DB" ;;
      *) exit 2 ;;
    esac
    pg_dump -Fc -U "$POSTGRES_USER" -d "$source_database"
  ' sh "$source_env" > "$artifact_dir/${source_env}.dump"
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$target_database"
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$target_database" < "$artifact_dir/${source_env}.dump"
  rm "$artifact_dir/${source_env}.dump"
done

printf 'Building isolated routing backend image...\n'
docker compose -f "$COMPOSE_FILE" build backend >/dev/null

printf 'Rehearsing legacy, Platform, and Restaurant slug migrations...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -e SAAS_ROUTING_DATABASE_NAME="$LEGACY_DATABASE" backend sh -c '
  set -eu; database_server="${DATABASE_URL%/*}"; export DATABASE_URL="$database_server/$SAAS_ROUTING_DATABASE_NAME"
  alembic upgrade p12route0014; alembic downgrade p11privacy0013; alembic upgrade p12route0014
'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -e SAAS_ROUTING_PLATFORM_DATABASE_NAME="$PLATFORM_DATABASE" backend sh -c '
  set -eu; database_server="${PLATFORM_DATABASE_URL%/*}"; export PLATFORM_DATABASE_URL="$database_server/$SAAS_ROUTING_PLATFORM_DATABASE_NAME"
  alembic -c alembic-boundaries.ini -n platform upgrade p12platform0016
  alembic -c alembic-boundaries.ini -n platform downgrade p11platform0015
  alembic -c alembic-boundaries.ini -n platform upgrade p12platform0016
'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -e SAAS_ROUTING_RESTAURANT_DATABASE_NAME="$RESTAURANT_DATABASE" backend sh -c '
  set -eu; database_server="${RESTAURANT_DATABASE_URL%/*}"; export RESTAURANT_DATABASE_URL="$database_server/$SAAS_ROUTING_RESTAURANT_DATABASE_NAME"
  alembic -c alembic-boundaries.ini -n restaurant upgrade p6restaurant0007
  alembic -c alembic-boundaries.ini -n restaurant downgrade p5restaurant0006
  alembic -c alembic-boundaries.ini -n restaurant upgrade p6restaurant0007
'
[[ "$(psql_database "$LEGACY_DATABASE" 'SELECT version_num FROM alembic_version')" = "$TARGET_LEGACY_HEAD" ]] || fail "legacy clone did not reach routing head"
[[ "$(psql_database "$PLATFORM_DATABASE" 'SELECT version_num FROM alembic_version')" = "$TARGET_PLATFORM_HEAD" ]] || fail "Platform clone did not reach routing head"
[[ "$(psql_database "$RESTAURANT_DATABASE" 'SELECT version_num FROM alembic_version')" = "$TARGET_RESTAURANT_HEAD" ]] || fail "Restaurant clone did not reach routing head"
for database_name in "$LEGACY_DATABASE" "$PLATFORM_DATABASE" "$RESTAURANT_DATABASE"; do
  [[ "$(psql_database "$database_name" 'SELECT count(*) FROM companies WHERE business_slug IS NULL')" = "0" ]] || fail "Company slug backfill is incomplete"
  [[ "$(psql_database "$database_name" 'SELECT count(*) - count(DISTINCT business_slug) FROM companies')" = "0" ]] || fail "Company slug backfill is not unique"
done

printf 'Projecting and verifying the new Company reference field...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e SAAS_ROUTING_PLATFORM_DATABASE_NAME="$PLATFORM_DATABASE" \
  -e SAAS_ROUTING_RESTAURANT_DATABASE_NAME="$RESTAURANT_DATABASE" \
  backend sh -c '
    set -eu
    platform_server="${PLATFORM_DATABASE_URL%/*}"; restaurant_server="${RESTAURANT_DATABASE_URL%/*}"
    export PLATFORM_DATABASE_URL="$platform_server/$SAAS_ROUTING_PLATFORM_DATABASE_NAME"
    export RESTAURANT_DATABASE_URL="$restaurant_server/$SAAS_ROUTING_RESTAURANT_DATABASE_NAME"
    python -m app.utils.project_platform_references --seed-snapshot --drain --verify
  ' | tee "$artifact_dir/projection-parity.json"

printf 'Running full backend regression and isolated two-Tenant API smoke...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -v "$PWD/backend/tests:/app/tests:ro" backend python -B -m unittest discover -s tests -p 'test_*.py' 2>&1 | tee "$artifact_dir/backend-tests.log"
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e SAAS_ROUTING_DATABASE_NAME="$LEGACY_DATABASE" \
  -e IDENTITY_DATABASE=legacy -e RESTAURANT_SERVICE_DATABASE=legacy -e REFERENCE_PROJECTOR_ENABLED=false \
  -e SAAS_EMAIL_DELIVERY_MODE=console \
  -v "$PWD/backend/tests:/app/tests:ro" backend sh -c '
    set -eu; database_server="${DATABASE_URL%/*}"; export DATABASE_URL="$database_server/$SAAS_ROUTING_DATABASE_NAME"
    export PLATFORM_DATABASE_URL="$DATABASE_URL" RESTAURANT_DATABASE_URL="$DATABASE_URL"
    python -m tests.smoke_saas_tenant_routing_api
  ' | tee "$artifact_dir/api-smoke.log"

legacy_after="$(psql_boundary POSTGRES_DB 'SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT count(*) FROM companies))')"
platform_after="$(psql_boundary PLATFORM_POSTGRES_DB 'SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT count(*) FROM companies))')"
restaurant_after="$(psql_boundary RESTAURANT_POSTGRES_DB 'SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT count(*) FROM companies))')"
[[ "$legacy_before" = "$legacy_after" ]] || fail "live legacy source changed"
[[ "$platform_before" = "$platform_after" ]] || fail "live Platform source changed"
[[ "$restaurant_before" = "$restaurant_after" ]] || fail "live Restaurant source changed"

cat > "$artifact_dir/manifest.txt" <<EOF
scope=SAAS-PREP-TENANT-ROUTING-09
timestamp=$timestamp
legacy_source=$legacy_before
platform_source=$platform_before
restaurant_source=$restaurant_before
legacy_target_head=$TARGET_LEGACY_HEAD
platform_target_head=$TARGET_PLATFORM_HEAD
restaurant_target_head=$TARGET_RESTAURANT_HEAD
slug_backfill_unique_and_complete=passed
company_reference_projection_parity=passed
full_backend_tests=passed
two_tenant_slug_api_smoke=passed
frontend_evidence=recorded_in_scope_plan
live_sources_unchanged=true
temporary_database_cleanup=automatic
EOF
chmod 600 "$artifact_dir/manifest.txt" "$artifact_dir/projection-parity.json" "$artifact_dir/backend-tests.log" "$artifact_dir/api-smoke.log"
printf 'SaaS Tenant routing gate passed. Artifact: %s\n' "$artifact_dir/manifest.txt"
