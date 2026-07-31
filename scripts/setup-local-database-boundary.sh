#!/bin/sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

if [ ! -f "$COMPOSE_FILE" ]; then
  fail "compose file not found: $COMPOSE_FILE"
fi

printf 'Starting local PostgreSQL...\n'
docker compose -f "$COMPOSE_FILE" up -d postgres >/dev/null

tries=0
until docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1))
  if [ "$tries" -ge 30 ]; then
    fail "postgres service did not become ready"
  fi
  sleep 2
done

printf 'Creating physical boundary databases when absent...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c '/docker-entrypoint-initdb.d/20-database-boundaries.sh'

printf 'Building backend migration image...\n'
docker compose -f "$COMPOSE_FILE" build backend >/dev/null

COMPOSE_FILE="$COMPOSE_FILE" scripts/run-boundary-migrations.sh

printf 'Local database boundary setup completed.\n'
