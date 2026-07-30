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

printf 'Running production database migrations with Alembic...\n'
docker compose -f "$COMPOSE_FILE" --profile tools run --rm --build migrate

printf 'Production database migrations completed successfully.\n'
