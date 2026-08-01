#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
export RESTAURANT_BACKEND_IMAGE="${P5_BACKEND_IMAGE:-restaurant-pos-dev-backend:phase5-tenant-gate}"
ARTIFACT_ROOT="${P5_ARTIFACT_ROOT:-/private/tmp/restaurant-p5-artifacts}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_LEGACY_HEAD="6b7c8d9e0f12"
EXPECTED_PLATFORM_HEAD="p1platform0003"
EXPECTED_RESTAURANT_HEAD="p1restaurant0003"
TARGET_LEGACY_HEAD="p5tenant0007"
TARGET_PLATFORM_HEAD="p5platform0009"
TARGET_RESTAURANT_HEAD="p5restaurant0006"
LEGACY_PREFIX="restaurant_p5_tenant_"
PLATFORM_PREFIX="restaurant_p5_platform_"
RESTAURANT_PREFIX="restaurant_p5_ops_"
ASSUME_YES=0
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
      /private/tmp/restaurant-p5-tenant.*|/tmp/restaurant-p5-tenant.*)
        rm -rf "$TEMP_DIR"
        ;;
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
      (SELECT count(*) FROM companies), chr(58),
      (SELECT count(*) FROM users), chr(58),
      (SELECT count(*) FROM branches)
    )
  '
}

platform_fingerprint() {
  psql_boundary PLATFORM_POSTGRES_DB '
    SELECT concat(
      (SELECT version_num FROM alembic_version), chr(58),
      (SELECT count(*) FROM companies), chr(58),
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
      (SELECT count(*) FROM stock_movements)
    )
  '
}

printf 'Starting isolated Phase 5 tenant lifecycle gate...\n'
docker compose -f "$COMPOSE_FILE" up -d postgres redis >/dev/null
tries=0
until docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1))
  [[ "$tries" -lt 30 ]] || fail "postgres service did not become ready"
  sleep 1
done

[[ "$(psql_boundary POSTGRES_DB 'SELECT version_num FROM alembic_version')" = "$EXPECTED_LEGACY_HEAD" ]] || fail "unexpected live legacy head"
[[ "$(psql_boundary PLATFORM_POSTGRES_DB 'SELECT version_num FROM alembic_version')" = "$EXPECTED_PLATFORM_HEAD" ]] || fail "unexpected live Platform head"
[[ "$(psql_boundary RESTAURANT_POSTGRES_DB 'SELECT version_num FROM alembic_version')" = "$EXPECTED_RESTAURANT_HEAD" ]] || fail "unexpected live Restaurant head"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
database_suffix="$(date -u +%Y%m%d%H%M%S)$$"
LEGACY_DATABASE="${LEGACY_PREFIX}${database_suffix}"
PLATFORM_DATABASE="${PLATFORM_PREFIX}${database_suffix}"
RESTAURANT_DATABASE="${RESTAURANT_PREFIX}${database_suffix}"
artifact_dir="${ARTIFACT_ROOT%/}/p5-tenant-gate-01-${timestamp}"
mkdir -p "$artifact_dir"
TEMP_DIR="$(mktemp -d /private/tmp/restaurant-p5-tenant.XXXXXX 2>/dev/null || mktemp -d /tmp/restaurant-p5-tenant.XXXXXX)"

legacy_before="$(legacy_fingerprint)"
platform_before="$(platform_fingerprint)"
restaurant_before="$(restaurant_fingerprint)"
latest_image_before="$(docker image inspect restaurant-pos-dev-backend:latest --format '{{.Id}}')"

printf 'Cloning live sources into isolated databases...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$TEMP_DIR/legacy.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB"' > "$TEMP_DIR/platform.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$RESTAURANT_POSTGRES_DB"' > "$TEMP_DIR/restaurant.dump"
for database_name in "$LEGACY_DATABASE" "$PLATFORM_DATABASE" "$RESTAURANT_DATABASE"; do
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$database_name"
done
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$LEGACY_DATABASE" < "$TEMP_DIR/legacy.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$PLATFORM_DATABASE" < "$TEMP_DIR/platform.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$RESTAURANT_DATABASE" < "$TEMP_DIR/restaurant.dump"

printf 'Building tagged Phase 5 backend image...\n'
docker compose -f "$COMPOSE_FILE" build backend >/dev/null

printf 'Rehearsing legacy upgrade/downgrade/re-upgrade...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -e P5_TENANT_DATABASE_NAME="$LEGACY_DATABASE" backend sh -c '
  set -eu
  case "$P5_TENANT_DATABASE_NAME" in restaurant_p5_tenant_[0-9]*) ;; *) exit 2 ;; esac
  database_server="${DATABASE_URL%/*}"
  export DATABASE_URL="$database_server/$P5_TENANT_DATABASE_NAME"
  alembic upgrade p5tenant0007
  alembic downgrade p4feature0006
  alembic upgrade p5tenant0007
'

printf 'Rehearsing Platform upgrade/downgrade/re-upgrade...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -e P5_PLATFORM_DATABASE_NAME="$PLATFORM_DATABASE" backend sh -c '
  set -eu
  case "$P5_PLATFORM_DATABASE_NAME" in restaurant_p5_platform_[0-9]*) ;; *) exit 2 ;; esac
  database_server="${PLATFORM_DATABASE_URL%/*}"
  export PLATFORM_DATABASE_URL="$database_server/$P5_PLATFORM_DATABASE_NAME"
  alembic -c alembic-boundaries.ini -n platform upgrade p5platform0009
  alembic -c alembic-boundaries.ini -n platform downgrade p4platform0008
  alembic -c alembic-boundaries.ini -n platform upgrade p5platform0009
'

printf 'Rehearsing Restaurant upgrade/downgrade/re-upgrade...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -e P5_RESTAURANT_DATABASE_NAME="$RESTAURANT_DATABASE" backend sh -c '
  set -eu
  case "$P5_RESTAURANT_DATABASE_NAME" in restaurant_p5_ops_[0-9]*) ;; *) exit 2 ;; esac
  database_server="${RESTAURANT_DATABASE_URL%/*}"
  export RESTAURANT_DATABASE_URL="$database_server/$P5_RESTAURANT_DATABASE_NAME"
  alembic -c alembic-boundaries.ini -n restaurant upgrade p5restaurant0006
  alembic -c alembic-boundaries.ini -n restaurant downgrade p4restaurant0005
  alembic -c alembic-boundaries.ini -n restaurant upgrade p5restaurant0006
'

[[ "$(psql_database "$LEGACY_DATABASE" 'SELECT version_num FROM alembic_version')" = "$TARGET_LEGACY_HEAD" ]] || fail "legacy clone did not reach Phase 5 head"
[[ "$(psql_database "$PLATFORM_DATABASE" 'SELECT version_num FROM alembic_version')" = "$TARGET_PLATFORM_HEAD" ]] || fail "Platform clone did not reach Phase 5 head"
[[ "$(psql_database "$RESTAURANT_DATABASE" 'SELECT version_num FROM alembic_version')" = "$TARGET_RESTAURANT_HEAD" ]] || fail "Restaurant clone did not reach Phase 5 head"
for database_name in "$LEGACY_DATABASE" "$PLATFORM_DATABASE"; do
  [[ "$(psql_database "$database_name" "SELECT count(*) FROM information_schema.tables WHERE table_name IN ('platform_operators', 'platform_tenant_profiles')")" = "2" ]] || fail "Platform lifecycle tables are missing from $database_name"
  [[ "$(psql_database "$database_name" "SELECT count(*) FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'credential_version'")" = "1" ]] || fail "Company credential generation is missing from $database_name"
done
[[ "$(psql_database "$RESTAURANT_DATABASE" "SELECT count(*) FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'credential_version'")" = "1" ]] || fail "Restaurant Company credential projection column is missing"

printf 'Running full backend unit regression...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps -v "$PWD/backend/tests:/app/tests:ro" backend python -B -m unittest discover -s tests -p 'test_*.py'

printf 'Running Phase 5 Platform tenant lifecycle API smoke...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e P5_TENANT_DATABASE_NAME="$LEGACY_DATABASE" \
  -e IDENTITY_DATABASE=legacy \
  -e RESTAURANT_SERVICE_DATABASE=legacy \
  -e REFERENCE_PROJECTOR_ENABLED=false \
  -v "$PWD/backend/tests:/app/tests:ro" \
  backend sh -c '
    set -eu
    database_server="${DATABASE_URL%/*}"
    export DATABASE_URL="$database_server/$P5_TENANT_DATABASE_NAME"
    export PLATFORM_DATABASE_URL="$DATABASE_URL"
    export RESTAURANT_DATABASE_URL="$DATABASE_URL"
    python -m tests.smoke_platform_tenant_api
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
scope=P5-TENANT-LIFECYCLE-01
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
platform_tenant_api_smoke=passed
company_owner_bootstrap=passed
user_suspend_generation_gate=passed
device_suspend_generation_gate=passed
manual_feature_flag_gate=passed
onboarding_checklist_gate=passed
live_sources_unchanged=true
EOF

printf 'Phase 5 tenant lifecycle gate passed. Artifact: %s\n' "$artifact_dir/manifest.txt"
