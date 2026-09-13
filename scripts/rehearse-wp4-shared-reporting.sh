#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
export RESTAURANT_BACKEND_IMAGE="${WP4_REPORTING_BACKEND_IMAGE:-restaurant-pos-dev-backend:wp4-reporting-gate}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATABASE_PREFIX="restaurant_wp4_reporting_"
REPORTING_DATABASE=""
TEMP_DIR=""

fail() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

cleanup() {
  if [[ -n "$REPORTING_DATABASE" ]]; then
    case "$REPORTING_DATABASE" in
      ${DATABASE_PREFIX}[0-9]*)
        docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
          psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
            -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '\''$1'\'' AND pid <> pg_backend_pid()" >/dev/null
          dropdb --if-exists -U "$POSTGRES_USER" "$1"
        ' sh "$REPORTING_DATABASE" >/dev/null 2>&1 || true
        ;;
    esac
  fi
  if [[ -n "$TEMP_DIR" ]]; then
    case "$TEMP_DIR" in
      /private/tmp/restaurant-wp4-reporting.*|/tmp/restaurant-wp4-reporting.*) rm -rf "$TEMP_DIR" ;;
    esac
  fi
}
trap cleanup EXIT HUP INT TERM

cd "$PROJECT_DIR"
[[ "${1:-}" = "--yes" ]] || fail "this rehearsal creates and drops one isolated Platform clone; pass --yes"

docker compose -f "$COMPOSE_FILE" up -d postgres redis >/dev/null
tries=0
until docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1))
  [[ "$tries" -lt 30 ]] || fail "postgres service did not become ready"
  sleep 1
done

timestamp="$(date -u +%Y%m%d%H%M%S)"
REPORTING_DATABASE="${DATABASE_PREFIX}${timestamp}$$"
TEMP_DIR="$(mktemp -d /private/tmp/restaurant-wp4-reporting.XXXXXX 2>/dev/null || mktemp -d /tmp/restaurant-wp4-reporting.XXXXXX)"

before_fingerprint="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
  psql -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB" -tAc \
    "SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT count(*) FROM companies), chr(58), (SELECT count(*) FROM brands), chr(58), (SELECT count(*) FROM branches), chr(58), COALESCE(to_regclass('\''company_reporting_facts'\'')::text, '\''absent'\''))"
' | tr -d '[:space:]')"

printf 'Backing up and restoring Platform core into an isolated WP4 database...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB"' > "$TEMP_DIR/platform.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$REPORTING_DATABASE"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$REPORTING_DATABASE" < "$TEMP_DIR/platform.dump"

printf 'Building WP4 and rehearsing upgrade, smoke, downgrade, and re-upgrade...\n'
docker compose -f "$COMPOSE_FILE" build backend >/dev/null
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e WP4_REPORTING_DATABASE_NAME="$REPORTING_DATABASE" \
  -e IDENTITY_DATABASE=legacy \
  -e REFERENCE_PROJECTOR_ENABLED=false \
  -e SHARED_REPORTING_PROJECTOR_ENABLED=false \
  -e TAKEAWAY_FEATURE_ENABLED=false \
  -v "$PWD/backend/tests:/app/tests:ro" \
  backend sh -c '
    set -eu
    case "$WP4_REPORTING_DATABASE_NAME" in restaurant_wp4_reporting_[0-9]*) ;; *) exit 2 ;; esac
    database_server="${PLATFORM_DATABASE_URL%/*}"
    export DATABASE_URL="$database_server/$WP4_REPORTING_DATABASE_NAME"
    export PLATFORM_DATABASE_URL="$DATABASE_URL"
    export RESTAURANT_DATABASE_URL="$DATABASE_URL"
    alembic -c alembic-boundaries.ini -n platform upgrade p13platform0017
    python -m tests.smoke_shared_reporting
    alembic -c alembic-boundaries.ini -n platform downgrade p12platform0016
    test "$(alembic -c alembic-boundaries.ini -n platform current | tr -d "[:space:]")" = "p12platform0016"
    alembic -c alembic-boundaries.ini -n platform upgrade p13platform0017
    python -m tests.smoke_shared_reporting
    test "$(alembic -c alembic-boundaries.ini -n platform current | tr -d "[:space:]")" = "p13platform0017(head)"
  '

after_fingerprint="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
  psql -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB" -tAc \
    "SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT count(*) FROM companies), chr(58), (SELECT count(*) FROM brands), chr(58), (SELECT count(*) FROM branches), chr(58), COALESCE(to_regclass('\''company_reporting_facts'\'')::text, '\''absent'\''))"
' | tr -d '[:space:]')"
[[ "$before_fingerprint" = "$after_fingerprint" ]] || fail "live Platform source changed: $before_fingerprint -> $after_fingerprint"

printf 'WP4 shared reporting rehearsal passed; live Platform source remained unchanged.\n'
