#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
export RESTAURANT_BACKEND_IMAGE="${P4_BACKEND_IMAGE:-restaurant-pos-dev-backend:phase4-core-gate}"
ARTIFACT_ROOT="${P4_ARTIFACT_ROOT:-/private/tmp/restaurant-p4-artifacts}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSUME_YES=0
EXPECTED_LEGACY_HEAD="6b7c8d9e0f12"
EXPECTED_PLATFORM_HEAD="p1platform0003"
EXPECTED_RESTAURANT_HEAD="p1restaurant0003"
TARGET_LEGACY_HEAD="p4feature0006"
TARGET_PLATFORM_HEAD="p4platform0008"
TARGET_RESTAURANT_HEAD="p4restaurant0005"
LEGACY_PREFIX="restaurant_p4_core_"
PLATFORM_PREFIX="restaurant_p4_platform_"
RESTAURANT_PREFIX="restaurant_p4_ops_"
LEGACY_DATABASE=""
PLATFORM_DATABASE=""
RESTAURANT_DATABASE=""
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
  [[ -z "$RESTAURANT_DATABASE" ]] || drop_temporary_database "$RESTAURANT_DATABASE" "$RESTAURANT_PREFIX"
  if [[ -n "$TEMP_DIR" ]]; then
    case "$TEMP_DIR" in
      /private/tmp/restaurant-p4-core.*|/tmp/restaurant-p4-core.*)
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
[[ -f "$COMPOSE_FILE" ]] || fail "compose file not found: $COMPOSE_FILE"

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
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
    psql -U "$POSTGRES_USER" -d "$1" -tAc "$2"
  ' sh "$database_name" "$query" | tr -d '[:space:]'
}

legacy_fingerprint() {
  psql_boundary POSTGRES_DB '
    SELECT concat(
      (SELECT version_num FROM alembic_version), chr(58),
      (SELECT count(*) FROM sale_orders), chr(58),
      (SELECT count(*) FROM payments), chr(58),
      (SELECT count(*) FROM stock_movements), chr(58),
      (SELECT count(*) FROM journal_entries)
    )
  '
}

platform_fingerprint() {
  psql_boundary PLATFORM_POSTGRES_DB '
    SELECT concat(
      (SELECT version_num FROM alembic_version), chr(58),
      (SELECT count(*) FROM companies), chr(58),
      (SELECT count(*) FROM brands), chr(58),
      (SELECT count(*) FROM users), chr(58),
      (SELECT count(*) FROM roles)
    )
  '
}

restaurant_fingerprint() {
  psql_boundary RESTAURANT_POSTGRES_DB '
    SELECT concat(
      (SELECT version_num FROM alembic_version), chr(58),
      (SELECT count(*) FROM sale_orders), chr(58),
      (SELECT count(*) FROM payments), chr(58),
      (SELECT count(*) FROM stock_movements), chr(58),
      (SELECT count(*) FROM journal_entries)
    )
  '
}

printf 'Starting isolated Phase 4 migration gate...\n'
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
restaurant_head="$(psql_boundary RESTAURANT_POSTGRES_DB 'SELECT version_num FROM alembic_version')"
[[ "$legacy_head" = "$EXPECTED_LEGACY_HEAD" ]] || fail "unexpected legacy head: $legacy_head"
[[ "$platform_head" = "$EXPECTED_PLATFORM_HEAD" ]] || fail "unexpected Platform head: $platform_head"
[[ "$restaurant_head" = "$EXPECTED_RESTAURANT_HEAD" ]] || fail "unexpected Restaurant head: $restaurant_head"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
database_suffix="$(date -u +%Y%m%d%H%M%S)$$"
LEGACY_DATABASE="${LEGACY_PREFIX}${database_suffix}"
PLATFORM_DATABASE="${PLATFORM_PREFIX}${database_suffix}"
RESTAURANT_DATABASE="${RESTAURANT_PREFIX}${database_suffix}"
artifact_dir="${ARTIFACT_ROOT%/}/p4-core-gate-06-${timestamp}"
mkdir -p "$artifact_dir"
TEMP_DIR="$(mktemp -d /private/tmp/restaurant-p4-core.XXXXXX 2>/dev/null \
  || mktemp -d /tmp/restaurant-p4-core.XXXXXX)"

legacy_before="$(legacy_fingerprint)"
platform_before="$(platform_fingerprint)"
restaurant_before="$(restaurant_fingerprint)"
latest_image_before="$(docker image inspect restaurant-pos-dev-backend:latest --format '{{.Id}}')"

printf 'Cloning legacy, Platform, and Restaurant sources...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$TEMP_DIR/legacy.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB"' > "$TEMP_DIR/platform.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$RESTAURANT_POSTGRES_DB"' > "$TEMP_DIR/restaurant.dump"
for database_name in "$LEGACY_DATABASE" "$PLATFORM_DATABASE" "$RESTAURANT_DATABASE"; do
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$database_name"
done
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$LEGACY_DATABASE" < "$TEMP_DIR/legacy.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$PLATFORM_DATABASE" < "$TEMP_DIR/platform.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$RESTAURANT_DATABASE" < "$TEMP_DIR/restaurant.dump"

printf 'Building tagged Phase 4 backend image...\n'
docker compose -f "$COMPOSE_FILE" build backend >/dev/null

printf 'Rehearsing legacy upgrade/downgrade/re-upgrade...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e P4_CORE_DATABASE_NAME="$LEGACY_DATABASE" \
  backend sh -c '
    set -eu
    case "$P4_CORE_DATABASE_NAME" in restaurant_p4_core_[0-9]*) ;; *) exit 2 ;; esac
    database_server="${DATABASE_URL%/*}"
    export DATABASE_URL="$database_server/$P4_CORE_DATABASE_NAME"
    alembic upgrade p4feature0006
    alembic downgrade 6b7c8d9e0f12
    alembic upgrade p4feature0006
  '

printf 'Rehearsing Platform upgrade/downgrade/re-upgrade...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e P4_PLATFORM_DATABASE_NAME="$PLATFORM_DATABASE" \
  backend sh -c '
    set -eu
    case "$P4_PLATFORM_DATABASE_NAME" in restaurant_p4_platform_[0-9]*) ;; *) exit 2 ;; esac
    database_server="${PLATFORM_DATABASE_URL%/*}"
    export PLATFORM_DATABASE_URL="$database_server/$P4_PLATFORM_DATABASE_NAME"
    alembic -c alembic-boundaries.ini -n platform upgrade p4platform0008
    alembic -c alembic-boundaries.ini -n platform downgrade p1platform0003
    alembic -c alembic-boundaries.ini -n platform upgrade p4platform0008
  '

printf 'Rehearsing Restaurant upgrade/downgrade/re-upgrade...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e P4_RESTAURANT_DATABASE_NAME="$RESTAURANT_DATABASE" \
  backend sh -c '
    set -eu
    case "$P4_RESTAURANT_DATABASE_NAME" in restaurant_p4_ops_[0-9]*) ;; *) exit 2 ;; esac
    database_server="${RESTAURANT_DATABASE_URL%/*}"
    export RESTAURANT_DATABASE_URL="$database_server/$P4_RESTAURANT_DATABASE_NAME"
    alembic -c alembic-boundaries.ini -n restaurant upgrade p4restaurant0005
    alembic -c alembic-boundaries.ini -n restaurant downgrade p1restaurant0003
    alembic -c alembic-boundaries.ini -n restaurant upgrade p4restaurant0005
  '

[[ "$(psql_database "$LEGACY_DATABASE" 'SELECT version_num FROM alembic_version')" = "$TARGET_LEGACY_HEAD" ]] \
  || fail "legacy rehearsal did not reach $TARGET_LEGACY_HEAD"
[[ "$(psql_database "$PLATFORM_DATABASE" 'SELECT version_num FROM alembic_version')" = "$TARGET_PLATFORM_HEAD" ]] \
  || fail "Platform rehearsal did not reach $TARGET_PLATFORM_HEAD"
[[ "$(psql_database "$RESTAURANT_DATABASE" 'SELECT version_num FROM alembic_version')" = "$TARGET_RESTAURANT_HEAD" ]] \
  || fail "Restaurant rehearsal did not reach $TARGET_RESTAURANT_HEAD"

for database_name in "$LEGACY_DATABASE" "$RESTAURANT_DATABASE"; do
  [[ "$(psql_database "$database_name" "SELECT count(*) FROM information_schema.tables WHERE table_name = 'operational_outbox_events'")" = "1" ]] \
    || fail "operational outbox is missing from $database_name"
  [[ "$(psql_database "$database_name" "SELECT count(*) FROM pg_constraint WHERE conname = 'uq_journal_entries_source_posting'")" = "1" ]] \
    || fail "journal source uniqueness is missing from $database_name"
  [[ "$(psql_database "$database_name" "SELECT count(*) FROM information_schema.table_constraints WHERE table_name = 'operational_outbox_events' AND constraint_type = 'FOREIGN KEY'")" = "0" ]] \
    || fail "operational outbox contains a cross-domain foreign key in $database_name"
done
for database_name in "$LEGACY_DATABASE" "$PLATFORM_DATABASE"; do
  [[ "$(psql_database "$database_name" "SELECT count(*) FROM information_schema.tables WHERE table_name = 'brand_module_entitlements'")" = "1" ]] \
    || fail "Brand entitlements are missing from $database_name"
done

printf 'Running full backend unit regression...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -v "$PWD/backend/tests:/app/tests:ro" \
  backend \
  python -B -m unittest discover -s tests -p 'test_*.py'

printf 'Running sale handoff, staff scope, production, and recipe API smokes...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e P4_CORE_DATABASE_NAME="$LEGACY_DATABASE" \
  -e P2_SCOPE_DATABASE_NAME="$LEGACY_DATABASE" \
  -e IDENTITY_DATABASE=legacy \
  -e RESTAURANT_SERVICE_DATABASE=legacy \
  -e REFERENCE_PROJECTOR_ENABLED=false \
  -v "$PWD/backend/tests:/app/tests:ro" \
  backend sh -c '
    set -eu
    database_server="${DATABASE_URL%/*}"
    export DATABASE_URL="$database_server/$P4_CORE_DATABASE_NAME"
    export PLATFORM_DATABASE_URL="$DATABASE_URL"
    export RESTAURANT_DATABASE_URL="$DATABASE_URL"
    python -m tests.smoke_sale_handoff_api
    python -m tests.smoke_staff_scope_api
    python -m tests.smoke_production_batch_api
    python -m tests.smoke_recipe_inventory_api
  '

legacy_after="$(legacy_fingerprint)"
platform_after="$(platform_fingerprint)"
restaurant_after="$(restaurant_fingerprint)"
latest_image_after="$(docker image inspect restaurant-pos-dev-backend:latest --format '{{.Id}}')"
[[ "$legacy_before" = "$legacy_after" ]] || fail "live legacy source changed: $legacy_before -> $legacy_after"
[[ "$platform_before" = "$platform_after" ]] || fail "live Platform source changed: $platform_before -> $platform_after"
[[ "$restaurant_before" = "$restaurant_after" ]] || fail "live Restaurant source changed: $restaurant_before -> $restaurant_after"
[[ "$latest_image_before" = "$latest_image_after" ]] || fail "latest backend image changed"

cat > "$artifact_dir/manifest.txt" <<EOF
scope=P4-PHASE-GATE-06
timestamp=$timestamp
legacy_source=$legacy_before
platform_source=$platform_before
restaurant_source=$restaurant_before
legacy_target_head=$TARGET_LEGACY_HEAD
platform_target_head=$TARGET_PLATFORM_HEAD
restaurant_target_head=$TARGET_RESTAURANT_HEAD
backend_image=$RESTAURANT_BACKEND_IMAGE
latest_backend_image=$latest_image_after
unit_regression=passed
sale_handoff_smoke=passed
staff_scope_smoke=passed
production_flag_smoke=passed
recipe_costing_smoke=passed
live_sources_unchanged=true
EOF

printf 'Phase 4 core gate passed. Artifact: %s\n' "$artifact_dir/manifest.txt"
