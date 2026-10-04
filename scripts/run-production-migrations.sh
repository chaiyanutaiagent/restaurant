#!/bin/sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${1:-.env.production}"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

if [ ! -f "$COMPOSE_FILE" ]; then
  fail "compose file not found: $COMPOSE_FILE"
fi

if [ ! -x scripts/check-production-env.sh ]; then
  fail "scripts/check-production-env.sh is missing or not executable"
fi

if ! grep -Eq '^[[:space:]]*migrate:' "$COMPOSE_FILE"; then
  fail "migration service not found in $COMPOSE_FILE"
fi

printf 'Validating production environment: %s\n' "$ENV_FILE"
scripts/check-production-env.sh "$ENV_FILE"

export PRODUCTION_ENV_FILE="$ENV_FILE"

printf 'Validating production compose configuration: %s\n' "$COMPOSE_FILE"
docker compose -f "$COMPOSE_FILE" --profile tools config >/dev/null

printf 'Running Legacy production database migrations with Alembic...\n'
docker compose -f "$COMPOSE_FILE" --profile tools run --rm --build migrate

printf 'Ensuring Platform, Restaurant, Retail and Takeaway databases exist...\n'
for key in PLATFORM_POSTGRES_DB RESTAURANT_POSTGRES_DB RETAIL_POSTGRES_DB TAKEAWAY_POSTGRES_DB; do
  database_name="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'printenv "$1"' sh "$key")"
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
    set -eu
    database_name="$1"
    case "$database_name" in
      ""|*[!A-Za-z0-9_]*) exit 2 ;;
    esac
    if ! psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
      -tAc "SELECT 1 FROM pg_database WHERE datname = '\''$database_name'\''" | grep -q 1; then
      createdb -U "$POSTGRES_USER" "$database_name"
    fi
  ' sh "$database_name"
done

printf 'Running Platform, Restaurant, Retail and Takeaway boundary migrations...\n'
docker compose -f "$COMPOSE_FILE" --profile tools run --rm --no-deps migrate sh -c '
  set -eu
  alembic -c alembic-boundaries.ini -n platform upgrade head
  alembic -c alembic-boundaries.ini -n restaurant upgrade head
  alembic -c alembic-boundaries.ini -n retail upgrade head
  alembic -c alembic-boundaries.ini -n takeaway upgrade head
'

printf 'All five production database migrations completed successfully.\n'
