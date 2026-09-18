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

checksum_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    fail "sha256 checksum utility not found"
  fi
}

manifest_value() {
  awk -F= -v key="$1" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$BACKUP_DIR/manifest.txt"
}

verify_checksum() {
  expected="$(manifest_value "$1")"
  [ -n "$expected" ] || fail "checksum missing from manifest: $1"
  actual="$(checksum_file "$BACKUP_DIR/$2")"
  [ "$actual" = "$expected" ] || fail "checksum mismatch: $2"
}

ensure_postgres_running() {
  if docker compose -f "$COMPOSE_FILE" ps --status running --services | grep -qx postgres; then
    printf 'PostgreSQL is already running; restore drill will not recreate it.\n'
    return
  fi
  docker compose -f "$COMPOSE_FILE" up -d postgres >/dev/null
}

if [ -z "$BACKUP_DIR" ]; then
  fail "backup directory argument is required"
fi
for file in platform-core.dump restaurant.dump retail.dump takeaway.dump manifest.txt; do
  if [ ! -f "$BACKUP_DIR/$file" ]; then
    fail "required backup file missing: $BACKUP_DIR/$file"
  fi
done

include_legacy=0
if [ -f "$BACKUP_DIR/postgres.dump" ] && [ -n "$(manifest_value postgres_sha256)" ]; then
  verify_checksum postgres_sha256 postgres.dump
  include_legacy=1
fi
verify_checksum platform_sha256 platform-core.dump
verify_checksum restaurant_sha256 restaurant.dump
verify_checksum retail_sha256 retail.dump
verify_checksum takeaway_sha256 takeaway.dump

platform_drill="restaurant_platform_core_${DRILL_SUFFIX}"
restaurant_drill="restaurant_ops_${DRILL_SUFFIX}"
retail_drill="retail_ops_${DRILL_SUFFIX}"
takeaway_drill="takeaway_ops_${DRILL_SUFFIX}"
legacy_drill="restaurant_legacy_${DRILL_SUFFIX}"
validate_database_name "$platform_drill"
validate_database_name "$restaurant_drill"
validate_database_name "$retail_drill"
validate_database_name "$takeaway_drill"
validate_database_name "$legacy_drill"

ensure_postgres_running

tries=0
until docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1))
  if [ "$tries" -ge 30 ]; then
    fail "postgres service did not become ready"
  fi
  sleep 2
done

drill_databases="$platform_drill $restaurant_drill $retail_drill $takeaway_drill"
if [ "$include_legacy" = "1" ]; then
  drill_databases="$legacy_drill $drill_databases"
fi
for drill_database in $drill_databases; do
  if docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT 1 FROM pg_database WHERE datname = '\''$1'\''"' sh "$drill_database" | grep -q 1; then
    fail "drill database already exists: $drill_database"
  fi
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$drill_database"
done

if [ "$include_legacy" = "1" ]; then
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$legacy_drill" \
    < "$BACKUP_DIR/postgres.dump"
fi
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$platform_drill" \
  < "$BACKUP_DIR/platform-core.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$restaurant_drill" \
  < "$BACKUP_DIR/restaurant.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$retail_drill" \
  < "$BACKUP_DIR/retail.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$takeaway_drill" \
  < "$BACKUP_DIR/takeaway.dump"

platform_boundary="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$1" -tAc "SELECT boundary_name FROM database_boundary_metadata"' sh "$platform_drill" | tr -d '[:space:]')"
restaurant_boundary="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$1" -tAc "SELECT boundary_name FROM database_boundary_metadata"' sh "$restaurant_drill" | tr -d '[:space:]')"
retail_boundary="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$1" -tAc "SELECT boundary_name FROM database_boundary_metadata"' sh "$retail_drill" | tr -d '[:space:]')"
takeaway_boundary="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$1" -tAc "SELECT boundary_name FROM database_boundary_metadata"' sh "$takeaway_drill" | tr -d '[:space:]')"

if [ "$platform_boundary" != "platform_core" ] || [ "$restaurant_boundary" != "restaurant" ] || [ "$retail_boundary" != "retail" ] || [ "$takeaway_boundary" != "takeaway" ]; then
  fail "restored boundary metadata did not match expected values"
fi

legacy_result="not_included"
if [ "$include_legacy" = "1" ]; then
  legacy_head="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'psql -U "$POSTGRES_USER" -d "$1" -tAc "SELECT version_num FROM alembic_version"' sh "$legacy_drill" | tr -d '[:space:]')"
  [ -n "$legacy_head" ] || fail "restored Legacy database has no migration head"
  legacy_result="$legacy_drill"
fi

printf 'Boundary restore drill passed: legacy=%s platform=%s restaurant=%s retail=%s takeaway=%s\n' \
  "$legacy_result" "$platform_drill" "$restaurant_drill" "$retail_drill" "$takeaway_drill"

if [ "$CLEANUP" = "1" ]; then
  for drill_database in $drill_databases; do
    docker compose -f "$COMPOSE_FILE" exec -T postgres \
      sh -c 'dropdb -U "$POSTGRES_USER" "$1"' sh "$drill_database"
  done
  printf 'Restore drill databases removed.\n'
fi
