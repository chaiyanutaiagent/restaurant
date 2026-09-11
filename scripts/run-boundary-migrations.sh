#!/bin/sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

if [ ! -f "$COMPOSE_FILE" ]; then
  printf 'ERROR: compose file not found: %s\n' "$COMPOSE_FILE" >&2
  exit 1
fi

printf 'Migrating platform_core database...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps backend \
  alembic -c alembic-boundaries.ini -n platform upgrade head

printf 'Migrating restaurant database...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps backend \
  alembic -c alembic-boundaries.ini -n restaurant upgrade head

printf 'Migrating takeaway database...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps backend \
  alembic -c alembic-boundaries.ini -n takeaway upgrade head

printf 'Boundary migrations completed.\n'
