#!/bin/sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${PRODUCTION_ENV_FILE:-.env.production}"
BACKUP_DIR=""
ASSUME_YES=0
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-restaurant-pos-prod}"
UPLOADS_VOLUME="${PRODUCTION_UPLOADS_VOLUME:-${COMPOSE_PROJECT}_uploads}"
UPLOADS_OWNER="${PRODUCTION_UPLOADS_OWNER:-100:101}"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

manifest_value() {
  key="$1"
  sed -n "s/^${key}=//p" "$BACKUP_DIR/manifest.txt" | head -n 1
}

checksum_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

verify_checksum() {
  key="$1"
  file="$2"
  expected="$(manifest_value "$key")"
  [ -n "$expected" ] || fail "checksum missing from manifest: $key"
  [ "$(checksum_file "$BACKUP_DIR/$file")" = "$expected" ] \
    || fail "checksum mismatch: $file"
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

if [ ! -x scripts/check-production-env.sh ]; then
  fail "scripts/check-production-env.sh is missing or not executable"
fi

for file in postgres.dump platform-core.dump restaurant.dump retail.dump takeaway.dump uploads.tar.gz redis.tar.gz manifest.txt; do
  if [ ! -f "$BACKUP_DIR/$file" ]; then
    fail "required backup file missing: $BACKUP_DIR/$file"
  fi
done

verify_checksum postgres_sha256 postgres.dump
verify_checksum platform_sha256 platform-core.dump
verify_checksum restaurant_sha256 restaurant.dump
verify_checksum retail_sha256 retail.dump
verify_checksum takeaway_sha256 takeaway.dump

printf 'Validating production environment: %s\n' "$ENV_FILE"
scripts/check-production-env.sh "$ENV_FILE"

export PRODUCTION_ENV_FILE="$ENV_FILE"

printf 'Validating production compose configuration: %s\n' "$COMPOSE_FILE"
docker compose -f "$COMPOSE_FILE" config >/dev/null

printf '%s\n' 'WARNING: restore is destructive.'
printf '%s\n' 'Stop backend/nginx/frontend workers before restoring, or allow this script to stop them now.'
printf '%s\n' 'PostgreSQL data, uploads, and Redis data for this compose project will be replaced.'

if [ "$ASSUME_YES" -ne 1 ]; then
  printf 'Type RESTORE to continue: '
  read CONFIRMATION
  if [ "$CONFIRMATION" != "RESTORE" ]; then
    fail "restore cancelled"
  fi
fi

printf 'Stopping application services before restore...\n'
docker compose -f "$COMPOSE_FILE" stop nginx frontend backend >/dev/null 2>&1 || true

printf 'Starting PostgreSQL and Redis restore dependencies...\n'
docker compose -f "$COMPOSE_FILE" up -d postgres redis >/dev/null
wait_for_postgres
wait_for_redis

legacy_database="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'printf %s "$POSTGRES_DB"')"
platform_database="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'printf %s "$PLATFORM_POSTGRES_DB"')"
restaurant_database="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'printf %s "$RESTAURANT_POSTGRES_DB"')"
retail_database="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'printf %s "$RETAIL_POSTGRES_DB"')"
takeaway_database="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'printf %s "$TAKEAWAY_POSTGRES_DB"')"

unique_database_count="$(printf '%s\n' "$legacy_database" "$platform_database" "$restaurant_database" "$retail_database" "$takeaway_database" | sort -u | wc -l | tr -d '[:space:]')"
[ "$unique_database_count" = "5" ] || fail "restore requires five distinct database names"

restore_database() {
  database_name="$1"
  dump_file="$2"
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'dropdb --if-exists --force -U "$POSTGRES_USER" "$1" && createdb -U "$POSTGRES_USER" "$1"' sh "$database_name"
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'pg_restore --no-owner --role="$POSTGRES_USER" -U "$POSTGRES_USER" -d "$1"' sh "$database_name" \
    < "$BACKUP_DIR/$dump_file"
}

printf 'Restoring Legacy and all four boundary databases...\n'
restore_database "$legacy_database" postgres.dump
restore_database "$platform_database" platform-core.dump
restore_database "$restaurant_database" restaurant.dump
restore_database "$retail_database" retail.dump
restore_database "$takeaway_database" takeaway.dump

verify_boundary() {
  database_name="$1"
  expected="$2"
  actual="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'psql -U "$POSTGRES_USER" -d "$1" -tAc "SELECT boundary_name FROM database_boundary_metadata"' sh "$database_name" | tr -d '[:space:]')"
  [ "$actual" = "$expected" ] || fail "$database_name boundary mismatch: $actual"
}

verify_boundary "$platform_database" platform_core
verify_boundary "$restaurant_database" restaurant
verify_boundary "$retail_database" retail
verify_boundary "$takeaway_database" takeaway

printf 'Restoring uploads backup...\n'
docker run --rm -i --volume "$UPLOADS_VOLUME:/data" redis:7-alpine \
  sh -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar -xzf - -C /data && chown -R "$1" /data' \
  sh "$UPLOADS_OWNER" \
  < "$BACKUP_DIR/uploads.tar.gz"

printf 'Restoring Redis backup...\n'
docker compose -f "$COMPOSE_FILE" stop redis >/dev/null
docker compose -f "$COMPOSE_FILE" run --rm --no-deps --entrypoint sh redis \
  -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar -xzf - -C /data' \
  < "$BACKUP_DIR/redis.tar.gz"
docker compose -f "$COMPOSE_FILE" up -d redis >/dev/null

printf 'Production restore completed from: %s\n' "$BACKUP_DIR"
