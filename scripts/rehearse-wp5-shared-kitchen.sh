#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
export RESTAURANT_BACKEND_IMAGE="${WP5_KITCHEN_BACKEND_IMAGE:-restaurant-pos-dev-backend:wp5-kitchen-gate}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATABASE_PREFIX="restaurant_wp5_kitchen_"
KITCHEN_DATABASE=""
TEMP_DIR=""

fail() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

cleanup() {
  if [[ -n "$KITCHEN_DATABASE" ]]; then
    case "$KITCHEN_DATABASE" in
      ${DATABASE_PREFIX}[0-9]*)
        docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
          psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
            -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '\''$1'\'' AND pid <> pg_backend_pid()" >/dev/null
          dropdb --if-exists -U "$POSTGRES_USER" "$1"
        ' sh "$KITCHEN_DATABASE" >/dev/null 2>&1 || true
        ;;
    esac
  fi
  if [[ -n "$TEMP_DIR" ]]; then
    case "$TEMP_DIR" in
      /private/tmp/restaurant-wp5-kitchen.*|/tmp/restaurant-wp5-kitchen.*) rm -rf "$TEMP_DIR" ;;
    esac
  fi
}
trap cleanup EXIT HUP INT TERM

cd "$PROJECT_DIR"
[[ "${1:-}" = "--yes" ]] || fail "this rehearsal creates and drops one isolated legacy clone; pass --yes"

docker compose -f "$COMPOSE_FILE" up -d postgres redis >/dev/null
tries=0
until docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1))
  [[ "$tries" -lt 30 ]] || fail "postgres service did not become ready"
  sleep 1
done

timestamp="$(date -u +%Y%m%d%H%M%S)"
KITCHEN_DATABASE="${DATABASE_PREFIX}${timestamp}$$"
TEMP_DIR="$(mktemp -d /private/tmp/restaurant-wp5-kitchen.XXXXXX 2>/dev/null || mktemp -d /tmp/restaurant-wp5-kitchen.XXXXXX)"

before_fingerprint="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT count(*) FROM companies), chr(58), (SELECT count(*) FROM brands), chr(58), (SELECT count(*) FROM stock_movements), chr(58), COALESCE(to_regclass('\''company_kitchens'\'')::text, '\''absent'\''))"
' | tr -d '[:space:]')"

printf 'Backing up and restoring the legacy ERP database into an isolated WP5 database...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$TEMP_DIR/legacy.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$KITCHEN_DATABASE"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$KITCHEN_DATABASE" < "$TEMP_DIR/legacy.dump"

printf 'Building WP5 and rehearsing upgrade, stock smoke, downgrade, and re-upgrade...\n'
docker compose -f "$COMPOSE_FILE" build backend >/dev/null
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e WP5_KITCHEN_DATABASE_NAME="$KITCHEN_DATABASE" \
  -e IDENTITY_DATABASE=legacy \
  -e RESTAURANT_SERVICE_DATABASE=legacy \
  -e REFERENCE_PROJECTOR_ENABLED=false \
  -e SHARED_REPORTING_PROJECTOR_ENABLED=false \
  -e TAKEAWAY_FEATURE_ENABLED=false \
  -e COMPANY_KITCHEN_WRITES_ENABLED=true \
  -v "$PWD/backend/tests:/app/tests:ro" \
  backend sh -c '
    set -eu
    case "$WP5_KITCHEN_DATABASE_NAME" in restaurant_wp5_kitchen_[0-9]*) ;; *) exit 2 ;; esac
    database_server="${DATABASE_URL%/*}"
    export DATABASE_URL="$database_server/$WP5_KITCHEN_DATABASE_NAME"
    export PLATFORM_DATABASE_URL="$DATABASE_URL"
    export RESTAURANT_DATABASE_URL="$DATABASE_URL"
    alembic upgrade p13kitchen0015
    python -m tests.smoke_shared_kitchen
    alembic downgrade p12route0014
    test "$(alembic current | tr -d "[:space:]")" = "p12route0014"
    python -c "from sqlalchemy import create_engine, inspect; from app.config import settings; assert not inspect(create_engine(settings.database_url_sync)).has_table('\''company_kitchens'\'')"
    alembic upgrade p13kitchen0015
    python -m tests.smoke_shared_kitchen
    test "$(alembic current | tr -d "[:space:]")" = "p13kitchen0015(head)"
  '

after_fingerprint="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT count(*) FROM companies), chr(58), (SELECT count(*) FROM brands), chr(58), (SELECT count(*) FROM stock_movements), chr(58), COALESCE(to_regclass('\''company_kitchens'\'')::text, '\''absent'\''))"
' | tr -d '[:space:]')"
[[ "$before_fingerprint" = "$after_fingerprint" ]] || fail "live legacy source changed: $before_fingerprint -> $after_fingerprint"

printf 'WP5 shared-kitchen rehearsal passed; the live legacy source remained unchanged.\n'
