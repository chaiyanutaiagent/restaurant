#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
export RESTAURANT_BACKEND_IMAGE="${WP6_DISTRIBUTION_BACKEND_IMAGE:-restaurant-pos-dev-backend:wp6-distribution-gate}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATABASE_PREFIX="restaurant_wp6_distribution_"
DISTRIBUTION_DATABASE=""
TEMP_DIR=""

fail() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

cleanup() {
  if [[ -n "$DISTRIBUTION_DATABASE" ]]; then
    case "$DISTRIBUTION_DATABASE" in
      ${DATABASE_PREFIX}[0-9]*)
        docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
          psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
            -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '\''$1'\'' AND pid <> pg_backend_pid()" >/dev/null
          dropdb --if-exists -U "$POSTGRES_USER" "$1"
        ' sh "$DISTRIBUTION_DATABASE" >/dev/null 2>&1 || true
        ;;
    esac
  fi
  if [[ -n "$TEMP_DIR" ]]; then
    case "$TEMP_DIR" in
      /private/tmp/restaurant-wp6-distribution.*|/tmp/restaurant-wp6-distribution.*) rm -rf "$TEMP_DIR" ;;
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
DISTRIBUTION_DATABASE="${DATABASE_PREFIX}${timestamp}$$"
TEMP_DIR="$(mktemp -d /private/tmp/restaurant-wp6-distribution.XXXXXX 2>/dev/null || mktemp -d /tmp/restaurant-wp6-distribution.XXXXXX)"

before_fingerprint="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT count(*) FROM companies), chr(58), (SELECT count(*) FROM transfer_orders), chr(58), (SELECT count(*) FROM stock_movements), chr(58), COALESCE(to_regclass('\''company_distribution_demands'\'')::text, '\''absent'\''))"
' | tr -d '[:space:]')"

printf 'Backing up and restoring the legacy ERP database into an isolated WP6 database...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$TEMP_DIR/legacy.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$DISTRIBUTION_DATABASE"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$DISTRIBUTION_DATABASE" < "$TEMP_DIR/legacy.dump"

printf 'Building WP6 and rehearsing upgrade, distribution smoke, downgrade, and re-upgrade...\n'
docker compose -f "$COMPOSE_FILE" build backend >/dev/null
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e WP6_DISTRIBUTION_DATABASE_NAME="$DISTRIBUTION_DATABASE" \
  -e IDENTITY_DATABASE=legacy \
  -e RESTAURANT_SERVICE_DATABASE=legacy \
  -e REFERENCE_PROJECTOR_ENABLED=false \
  -e SHARED_REPORTING_PROJECTOR_ENABLED=false \
  -e TAKEAWAY_FEATURE_ENABLED=false \
  -e COMPANY_KITCHEN_WRITES_ENABLED=false \
  -e COMPANY_DISTRIBUTION_WRITES_ENABLED=true \
  -v "$PWD/backend/tests:/app/tests:ro" \
  backend sh -c '
    set -eu
    case "$WP6_DISTRIBUTION_DATABASE_NAME" in restaurant_wp6_distribution_[0-9]*) ;; *) exit 2 ;; esac
    database_server="${DATABASE_URL%/*}"
    export DATABASE_URL="$database_server/$WP6_DISTRIBUTION_DATABASE_NAME"
    export PLATFORM_DATABASE_URL="$DATABASE_URL"
    export RESTAURANT_DATABASE_URL="$DATABASE_URL"
    alembic upgrade p14dist0016
    python -m tests.smoke_distribution
    alembic downgrade p13kitchen0015
    test "$(alembic current | tr -d "[:space:]")" = "p13kitchen0015"
    python -c "from sqlalchemy import create_engine, inspect; from app.config import settings; assert not inspect(create_engine(settings.database_url_sync)).has_table('\''company_distribution_demands'\'')"
    alembic upgrade p14dist0016
    python -m tests.smoke_distribution
    test "$(alembic current | tr -d "[:space:]")" = "p14dist0016(head)"
  '

after_fingerprint="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT count(*) FROM companies), chr(58), (SELECT count(*) FROM transfer_orders), chr(58), (SELECT count(*) FROM stock_movements), chr(58), COALESCE(to_regclass('\''company_distribution_demands'\'')::text, '\''absent'\''))"
' | tr -d '[:space:]')"
[[ "$before_fingerprint" = "$after_fingerprint" ]] || fail "live legacy source changed: $before_fingerprint -> $after_fingerprint"

printf 'WP6 distribution rehearsal passed; the live legacy source remained unchanged.\n'
