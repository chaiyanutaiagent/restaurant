#!/bin/sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_DIR="${1:-}"
DRILL_SUFFIX="${BOUNDARY_DRILL_SUFFIX:-restore_drill}"
CLEANUP="${BOUNDARY_DRILL_CLEANUP:-0}"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

validate_database_name() {
  case "$1" in
    ""|*[!A-Za-z0-9_]*) fail "invalid drill database name: $1" ;;
  esac
}

if [ -z "$BACKUP_DIR" ]; then
  fail "backup directory argument is required"
fi
for file in platform-core.dump restaurant.dump manifest.txt; do
  if [ ! -f "$BACKUP_DIR/$file" ]; then
    fail "required backup file missing: $BACKUP_DIR/$file"
  fi
done

platform_drill="restaurant_platform_core_${DRILL_SUFFIX}"
restaurant_drill="restaurant_ops_${DRILL_SUFFIX}"
validate_database_name "$platform_drill"
validate_database_name "$restaurant_drill"

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

for drill_database in "$platform_drill" "$restaurant_drill"; do
  if docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT 1 FROM pg_database WHERE datname = '\''$1'\''"' sh "$drill_database" | grep -q 1; then
    fail "drill database already exists: $drill_database"
  fi
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$drill_database"
done

docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$platform_drill" \
  < "$BACKUP_DIR/platform-core.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$restaurant_drill" \
  < "$BACKUP_DIR/restaurant.dump"

platform_boundary="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$1" -tAc "SELECT boundary_name FROM database_boundary_metadata"' sh "$platform_drill" | tr -d '[:space:]')"
restaurant_boundary="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$1" -tAc "SELECT boundary_name FROM database_boundary_metadata"' sh "$restaurant_drill" | tr -d '[:space:]')"

if [ "$platform_boundary" != "platform_core" ] || [ "$restaurant_boundary" != "restaurant" ]; then
  fail "restored boundary metadata did not match expected values"
fi

printf 'Boundary restore drill passed: platform=%s restaurant=%s\n' "$platform_drill" "$restaurant_drill"

if [ "$CLEANUP" = "1" ]; then
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'dropdb -U "$POSTGRES_USER" "$1"' sh "$platform_drill"
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'dropdb -U "$POSTGRES_USER" "$1"' sh "$restaurant_drill"
  printf 'Restore drill databases removed.\n'
fi
