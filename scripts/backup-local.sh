#!/bin/sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ENV_FILE="${LOCAL_ENV_FILE:-.env}"
BACKUP_ROOT="${1:-backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="${BACKUP_ROOT%/}/restaurant-pos-local-${TIMESTAMP}"
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$(pwd)")}"
UPLOADS_VOLUME="${LOCAL_UPLOADS_VOLUME:-${COMPOSE_PROJECT}_uploads}"

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

if [ ! -f "$COMPOSE_FILE" ]; then
  fail "compose file not found: $COMPOSE_FILE"
fi

if [ ! -f "$ENV_FILE" ]; then
  fail "env file not found: $ENV_FILE"
fi

printf 'Validating local compose configuration: %s\n' "$COMPOSE_FILE"
docker compose -f "$COMPOSE_FILE" config >/dev/null

mkdir -p "$BACKUP_DIR"

printf 'Starting PostgreSQL and Redis backup dependencies...\n'
docker compose -f "$COMPOSE_FILE" up -d postgres redis >/dev/null
wait_for_postgres
wait_for_redis

printf 'Creating PostgreSQL backup...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  > "$BACKUP_DIR/postgres.dump"

printf 'Creating uploads backup...\n'
# Do not mount uploads at Redis' /data path; that image-owned path can change the volume UID/GID.
docker run --rm --entrypoint tar --volume "$UPLOADS_VOLUME:/backup-source:ro" redis:7-alpine \
  -czf - -C /backup-source . \
  > "$BACKUP_DIR/uploads.tar.gz"

printf 'Creating Redis backup...\n'
docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli SAVE >/dev/null
docker compose -f "$COMPOSE_FILE" exec -T redis \
  sh -c 'tar -czf - -C /data .' \
  > "$BACKUP_DIR/redis.tar.gz"

cat > "$BACKUP_DIR/manifest.txt" <<EOF
backup_timestamp_utc=$TIMESTAMP
compose_file=$COMPOSE_FILE
compose_project_name=$COMPOSE_PROJECT
env_file=$ENV_FILE
postgres_service=postgres
redis_service=redis
uploads_source=volume:$UPLOADS_VOLUME
contents=postgres.dump uploads.tar.gz redis.tar.gz manifest.txt
EOF

printf 'Local backup completed: %s\n' "$BACKUP_DIR"
