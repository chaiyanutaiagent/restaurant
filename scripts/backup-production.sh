#!/bin/sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${PRODUCTION_ENV_FILE:-.env.production}"
BACKUP_ROOT="${1:-backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="${BACKUP_ROOT%/}/restaurant-pos-prod-${TIMESTAMP}"
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-restaurant-pos-prod}"
UPLOADS_VOLUME="${PRODUCTION_UPLOADS_VOLUME:-${COMPOSE_PROJECT}_uploads}"

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

if [ ! -x scripts/check-production-env.sh ]; then
  fail "scripts/check-production-env.sh is missing or not executable"
fi

printf 'Validating production environment: %s\n' "$ENV_FILE"
scripts/check-production-env.sh "$ENV_FILE"

export PRODUCTION_ENV_FILE="$ENV_FILE"

printf 'Validating production compose configuration: %s\n' "$COMPOSE_FILE"
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

cat > "$BACKUP_DIR/redis-backup-note.txt" <<'NOTE'
Redis is used for rate-limit/cache state and Celery broker/result data in this deployment.
This backup includes the Redis /data volume after redis-cli SAVE. Treat it as operational
state; PostgreSQL and uploads are the durable system-of-record backups.
NOTE

cat > "$BACKUP_DIR/manifest.txt" <<EOF
backup_timestamp_utc=$TIMESTAMP
compose_file=$COMPOSE_FILE
compose_project_name=$COMPOSE_PROJECT
env_file=$ENV_FILE
postgres_service=postgres
redis_service=redis
uploads_source=volume:$UPLOADS_VOLUME
contents=postgres.dump uploads.tar.gz redis.tar.gz redis-backup-note.txt manifest.txt
EOF

printf 'Production backup completed: %s\n' "$BACKUP_DIR"
