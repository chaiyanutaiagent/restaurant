#!/bin/sh
set -eu

ENV_FILE="${1:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

if [ -f "$ENV_FILE" ]; then
  export PRODUCTION_ENV_FILE="$ENV_FILE"
fi

printf 'Validating production compose configuration: %s\n' "$COMPOSE_FILE"
docker compose -f "$COMPOSE_FILE" config >/dev/null

if ! docker compose -f "$COMPOSE_FILE" ps -q nginx >/dev/null 2>&1 \
  || [ -z "$(docker compose -f "$COMPOSE_FILE" ps -q nginx 2>/dev/null)" ]; then
  printf 'ERROR: nginx container is not running.\n' >&2
  exit 1
fi

printf 'Testing nginx configuration.\n'
docker compose -f "$COMPOSE_FILE" exec -T nginx nginx -t

printf 'Reloading nginx.\n'
docker compose -f "$COMPOSE_FILE" exec -T nginx nginx -s reload

printf 'nginx reload completed.\n'
