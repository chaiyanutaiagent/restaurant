#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_ROOT="${WP8_ARTIFACT_ROOT:-/private/tmp/restaurant-wp8-artifacts}"
CANARY_PROJECT="${WP8_RETAIL_COMPOSE_PROJECT:-restaurant-wp8-retail-canary}"
CANARY_PASSWORD="${WP8_RETAIL_ADMIN_PASSWORD:-}"
BACKEND_IMAGE="${WP8_RETAIL_BACKEND_IMAGE:-restaurant-pos-dev-backend:wp8-retail-canary}"
ASSUME_YES=0

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

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

[[ "$ASSUME_YES" = "1" ]] \
  || fail "this gate replaces only its isolated Compose volumes; pass --yes"
[[ "$CANARY_PROJECT" == restaurant-wp8-retail* ]] \
  || fail "WP8 Compose project must start with restaurant-wp8-retail"
[[ ${#CANARY_PASSWORD} -ge 16 ]] \
  || fail "WP8_RETAIL_ADMIN_PASSWORD must be at least 16 characters"

cd "$PROJECT_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
artifact_dir="${ARTIFACT_ROOT%/}/wp8-retail-cutover-${timestamp}"
mkdir -p "$artifact_dir"

export COMPOSE_PROJECT_NAME="$CANARY_PROJECT"
export COMPOSE_FILE="docker-compose.yml:docker-compose.uat.yml"
export P5_UAT_ADMIN_PASSWORD="$CANARY_PASSWORD"
export RESTAURANT_BACKEND_IMAGE="$BACKEND_IMAGE"
export IDENTITY_DATABASE=platform_core
export RESTAURANT_SERVICE_DATABASE=legacy
export RETAIL_SERVICE_DATABASE=retail
export REFERENCE_PROJECTOR_ENABLED=true
export REFERENCE_PROJECTOR_POLL_SECONDS=60
export RETAIL_REFERENCE_PROJECTOR_ENABLED=true
export RETAIL_REFERENCE_PROJECTOR_POLL_SECONDS=60
export SHARED_REPORTING_PROJECTOR_ENABLED=false
export TAKEAWAY_SERVICE_DATABASE=disabled
export TAKEAWAY_FEATURE_ENABLED=false
export COMPANY_KITCHEN_WRITES_ENABLED=false
export COMPANY_DISTRIBUTION_WRITES_ENABLED=false

cleanup() {
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

printf 'Preparing isolated WP8 Retail stack %s...\n' "$CANARY_PROJECT"
docker compose down -v --remove-orphans >/dev/null 2>&1 || true
docker compose build backend 2>&1 | tee "$artifact_dir/backend-build.log"
docker compose up -d postgres redis

tries=0
until docker compose exec -T postgres sh -c \
  'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1))
  [[ "$tries" -lt 45 ]] || fail "isolated WP8 PostgreSQL did not become ready"
  sleep 1
done

printf 'Migrating the Legacy boundary-bootstrap baseline...\n'
docker compose run --rm --no-deps backend sh -c '
  base_url="${DATABASE_URL%/*}"
  export PLATFORM_DATABASE_URL="${base_url}/${PLATFORM_POSTGRES_DB:-restaurant_platform_core_db}"
  export RESTAURANT_DATABASE_URL="${base_url}/${RESTAURANT_POSTGRES_DB:-restaurant_ops_db}"
  export RETAIL_DATABASE_URL="${base_url}/${RETAIL_POSTGRES_DB:-retail_ops_db}"
  exec alembic upgrade 6b7c8d9e0f12
' 2>&1 | tee "$artifact_dir/legacy-boundary-baseline-migration.log"

printf 'Creating the established Platform/Restaurant snapshots from Legacy...\n'
docker compose exec -T postgres sh -c \
  'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  >"$artifact_dir/legacy-boundary-bootstrap.dump"
docker compose exec -T postgres sh -c \
  'pg_restore --no-owner -U "$POSTGRES_USER" -d "${PLATFORM_POSTGRES_DB:-restaurant_platform_core_db}"' \
  <"$artifact_dir/legacy-boundary-bootstrap.dump"
docker compose exec -T postgres sh -c \
  'pg_restore --no-owner -U "$POSTGRES_USER" -d "${RESTAURANT_POSTGRES_DB:-restaurant_ops_db}"' \
  <"$artifact_dir/legacy-boundary-bootstrap.dump"
docker compose exec -T postgres sh -c '
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" \
    -d "${PLATFORM_POSTGRES_DB:-restaurant_platform_core_db}" \
    -c "ALTER TABLE alembic_version RENAME TO legacy_alembic_version; ALTER TABLE legacy_alembic_version RENAME CONSTRAINT alembic_version_pkc TO legacy_alembic_version_pkc"
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" \
    -d "${RESTAURANT_POSTGRES_DB:-restaurant_ops_db}" \
    -c "ALTER TABLE alembic_version RENAME TO legacy_alembic_version; ALTER TABLE legacy_alembic_version RENAME CONSTRAINT alembic_version_pkc TO legacy_alembic_version_pkc"
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" \
    -d "${PLATFORM_POSTGRES_DB:-restaurant_platform_core_db}" \
    -f /opt/restaurant/platform-control-plane-prune.psql
' 2>&1 | tee "$artifact_dir/boundary-bootstrap.log"

docker compose run --rm --no-deps backend sh -c '
  base_url="${DATABASE_URL%/*}"
  export PLATFORM_DATABASE_URL="${base_url}/${PLATFORM_POSTGRES_DB:-restaurant_platform_core_db}"
  export RESTAURANT_DATABASE_URL="${base_url}/${RESTAURANT_POSTGRES_DB:-restaurant_ops_db}"
  export RETAIL_DATABASE_URL="${base_url}/${RETAIL_POSTGRES_DB:-retail_ops_db}"
  exec alembic -c alembic-boundaries.ini -n platform upgrade head
' 2>&1 | tee "$artifact_dir/platform-migration.log"
docker compose run --rm --no-deps backend sh -c '
  base_url="${DATABASE_URL%/*}"
  export PLATFORM_DATABASE_URL="${base_url}/${PLATFORM_POSTGRES_DB:-restaurant_platform_core_db}"
  export RESTAURANT_DATABASE_URL="${base_url}/${RESTAURANT_POSTGRES_DB:-restaurant_ops_db}"
  export RETAIL_DATABASE_URL="${base_url}/${RETAIL_POSTGRES_DB:-retail_ops_db}"
  exec alembic -c alembic-boundaries.ini -n restaurant upgrade head
' 2>&1 | tee "$artifact_dir/restaurant-migration.log"
docker compose run --rm --no-deps backend sh -c '
  base_url="${DATABASE_URL%/*}"
  export PLATFORM_DATABASE_URL="${base_url}/${PLATFORM_POSTGRES_DB:-restaurant_platform_core_db}"
  export RESTAURANT_DATABASE_URL="${base_url}/${RESTAURANT_POSTGRES_DB:-restaurant_ops_db}"
  export RETAIL_DATABASE_URL="${base_url}/${RETAIL_POSTGRES_DB:-retail_ops_db}"
  exec alembic -c alembic-boundaries.ini -n retail upgrade head
' 2>&1 | tee "$artifact_dir/retail-migration.log"

printf 'Advancing Legacy to the current application head...\n'
docker compose run --rm --no-deps backend sh -c '
  base_url="${DATABASE_URL%/*}"
  export PLATFORM_DATABASE_URL="${base_url}/${PLATFORM_POSTGRES_DB:-restaurant_platform_core_db}"
  export RESTAURANT_DATABASE_URL="${base_url}/${RESTAURANT_POSTGRES_DB:-restaurant_ops_db}"
  export RETAIL_DATABASE_URL="${base_url}/${RETAIL_POSTGRES_DB:-retail_ops_db}"
  exec alembic upgrade head
' 2>&1 | tee "$artifact_dir/legacy-current-migration.log"

printf 'Verifying Retail v2 downgrade and re-upgrade...\n'
docker compose run --rm --no-deps backend sh -c '
  base_url="${DATABASE_URL%/*}"
  export PLATFORM_DATABASE_URL="${base_url}/${PLATFORM_POSTGRES_DB:-restaurant_platform_core_db}"
  export RESTAURANT_DATABASE_URL="${base_url}/${RESTAURANT_POSTGRES_DB:-restaurant_ops_db}"
  export RETAIL_DATABASE_URL="${base_url}/${RETAIL_POSTGRES_DB:-retail_ops_db}"
  alembic -c alembic-boundaries.ini -n retail downgrade p7retail0001
  exec alembic -c alembic-boundaries.ini -n retail upgrade head
' 2>&1 | tee "$artifact_dir/retail-downgrade-reupgrade.log"

printf 'Taking pre-canary boundary backups...\n'
docker compose exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' >"$artifact_dir/legacy-before-canary.sql"
docker compose exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" "${PLATFORM_POSTGRES_DB:-restaurant_platform_core_db}"' \
  >"$artifact_dir/platform-before-canary.sql"
docker compose exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" "${RETAIL_POSTGRES_DB:-retail_ops_db}"' \
  >"$artifact_dir/retail-before-canary.sql"
shasum -a 256 "$artifact_dir"/*-before-canary.sql >"$artifact_dir/backup-sha256.txt"

printf 'Running selective migration and Retail-database canary...\n'
docker compose run --rm --no-deps \
  -e PYTHONPATH=/app \
  -e WP8_RETAIL_PROJECT_NAME="$CANARY_PROJECT" \
  -e WP8_RETAIL_SMOKE_PASSWORD="$CANARY_PASSWORD" \
  backend sh -c '
    base_url="${DATABASE_URL%/*}"
    export PLATFORM_DATABASE_URL="${base_url}/${PLATFORM_POSTGRES_DB:-restaurant_platform_core_db}"
    export RESTAURANT_DATABASE_URL="${base_url}/${RESTAURANT_POSTGRES_DB:-restaurant_ops_db}"
    export RETAIL_DATABASE_URL="${base_url}/${RETAIL_POSTGRES_DB:-retail_ops_db}"
    exec python tests/smoke_wp8_retail_cutover.py
  ' 2>&1 | tee "$artifact_dir/retail-cutover-canary.log"

printf 'Running read-only rollback-route canary...\n'
docker compose run --rm --no-deps \
  -e PYTHONPATH=/app \
  -e WP8_RETAIL_PROJECT_NAME="$CANARY_PROJECT" \
  -e WP8_RETAIL_SMOKE_PASSWORD="$CANARY_PASSWORD" \
  -e RETAIL_SERVICE_DATABASE=legacy \
  backend sh -c '
    base_url="${DATABASE_URL%/*}"
    export PLATFORM_DATABASE_URL="${base_url}/${PLATFORM_POSTGRES_DB:-restaurant_platform_core_db}"
    export RESTAURANT_DATABASE_URL="${base_url}/${RESTAURANT_POSTGRES_DB:-restaurant_ops_db}"
    export RETAIL_DATABASE_URL="${base_url}/${RETAIL_POSTGRES_DB:-retail_ops_db}"
    exec python tests/smoke_wp8_retail_rollback.py
  ' 2>&1 | tee "$artifact_dir/retail-rollback-canary.log"

{
  printf 'scope=WP8-RETAIL-SELECTIVE-MIGRATION-01\n'
  printf 'timestamp=%s\n' "$timestamp"
  printf 'compose_project=%s\n' "$CANARY_PROJECT"
  printf 'retail_schema_contract=2\n'
  printf 'retail_migration_downgrade_reupgrade=passed\n'
  printf 'pre_canary_boundary_backups=passed\n'
  printf 'platform_reference_projection=exact\n'
  printf 'retail_selective_copy_replay=exact\n'
  printf 'retail_cutover_canary=passed\n'
  printf 'sale_refund_void_stock_report=passed\n'
  printf 'shared_erp_retail_projection=passed\n'
  printf 'legacy_write_isolation=passed\n'
  printf 'retail_rollback_route=passed\n'
  printf 'physical_scanner_printer_offline_uat=deferred_by_owner\n'
  printf 'uat_activated=false\n'
  printf 'production_activated=false\n'
} >"$artifact_dir/manifest.txt"

printf 'WP8 Retail local canary passed. Artifact: %s\n' "$artifact_dir/manifest.txt"
