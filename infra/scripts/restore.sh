#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"

COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.prod.yml}"
ENV_FILE="${PRODUCTION_ENV_FILE:-$ROOT_DIR/.env.production}"
BACKUP_DIR=""
ASSUME_YES=0
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-restaurant-pos-prod}"
UPLOADS_VOLUME="${PRODUCTION_UPLOADS_VOLUME:-${COMPOSE_PROJECT}_uploads}"
UPLOADS_OWNER="${PRODUCTION_UPLOADS_OWNER:-100:101}"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

wait_for_postgres() {
  tries=0
  until docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
    tries=$((tries + 1))
    if [ "$tries" -ge 30 ]; then
      fail "postgres service did not become ready"
    fi
    sleep 2
  done
}

wait_for_redis() {
  tries=0
  until docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping >/dev/null 2>&1; do
    tries=$((tries + 1))
    if [ "$tries" -ge 30 ]; then
      fail "redis service did not become ready"
    fi
    sleep 2
  done
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --yes)
      ASSUME_YES=1
      shift
      ;;
    -*)
      fail "unknown option: $1"
      ;;
    *)
      if [ -n "$BACKUP_DIR" ]; then
        fail "only one backup directory argument is supported"
      fi
      BACKUP_DIR="$1"
      shift
      ;;
  esac
done

if [ -z "$BACKUP_DIR" ]; then
  fail "backup directory argument is required"
fi

if [ ! -d "$BACKUP_DIR" ]; then
  fail "backup directory not found: $BACKUP_DIR"
fi

if [ ! -f "$COMPOSE_FILE" ]; then
  fail "compose file not found: $COMPOSE_FILE"
fi

if [ ! -f "$ENV_FILE" ]; then
  fail "production env file not found: $ENV_FILE"
fi

for file in postgres.dump uploads.tar.gz redis.tar.gz manifest.txt; do
  if [ ! -f "$BACKUP_DIR/$file" ]; then
    fail "required backup file missing: $BACKUP_DIR/$file"
  fi
done

if [ -x "$ROOT_DIR/scripts/check-production-env.sh" ]; then
  "$ROOT_DIR/scripts/check-production-env.sh" "$ENV_FILE"
fi

export PRODUCTION_ENV_FILE="$ENV_FILE"

docker compose -f "$COMPOSE_FILE" config >/dev/null

printf '%s\n' 'WARNING: production restore is destructive.'
printf '%s\n' 'PostgreSQL data, uploads, and Redis state for this compose project will be replaced.'

if [ "$ASSUME_YES" -ne 1 ]; then
  printf 'Type RESTORE to continue: '
  read CONFIRMATION
  if [ "$CONFIRMATION" != "RESTORE" ]; then
    fail "restore cancelled"
  fi
fi

printf 'Stopping application services...\n'
docker compose -f "$COMPOSE_FILE" stop nginx frontend backend >/dev/null 2>&1 || true

printf 'Starting PostgreSQL and Redis restore dependencies...\n'
docker compose -f "$COMPOSE_FILE" up -d postgres redis >/dev/null
wait_for_postgres
wait_for_redis

printf 'Restoring PostgreSQL...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'dropdb --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --clean --if-exists --no-owner --role="$POSTGRES_USER" -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < "$BACKUP_DIR/postgres.dump"

printf 'Restoring uploads...\n'
docker run --rm -i --volume "$UPLOADS_VOLUME:/data" redis:7-alpine \
  sh -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar -xzf - -C /data && chown -R "$1" /data' \
  sh "$UPLOADS_OWNER" \
  < "$BACKUP_DIR/uploads.tar.gz"

printf 'Restoring Redis...\n'
docker compose -f "$COMPOSE_FILE" stop redis >/dev/null
docker compose -f "$COMPOSE_FILE" run --rm --no-deps --entrypoint sh redis \
  -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar -xzf - -C /data' \
  < "$BACKUP_DIR/redis.tar.gz"
docker compose -f "$COMPOSE_FILE" up -d redis >/dev/null

printf 'Production restore completed from: %s\n' "$BACKUP_DIR"
