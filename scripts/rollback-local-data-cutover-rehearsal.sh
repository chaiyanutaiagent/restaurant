#!/bin/sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_DIR=""
ASSUME_YES=0
BACKEND_STOPPED=0

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

restart_backend() {
  if [ "$BACKEND_STOPPED" = "1" ]; then
    docker compose -f "$COMPOSE_FILE" up -d backend >/dev/null 2>&1 || true
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --yes) ASSUME_YES=1; shift ;;
    *)
      if [ -n "$BACKUP_DIR" ]; then
        fail "only one backup directory is supported"
      fi
      BACKUP_DIR="$1"
      shift
      ;;
  esac
done

if [ "$ASSUME_YES" != "1" ]; then
  fail "rollback recreates only the two boundary target databases; pass --yes"
fi
if [ -z "$BACKUP_DIR" ] || [ ! -d "$BACKUP_DIR" ]; then
  fail "valid rehearsal backup directory is required"
fi
for file in platform-before.dump restaurant-before.dump manifest.txt; do
  if [ ! -f "$BACKUP_DIR/$file" ]; then
    fail "required rollback file missing: $BACKUP_DIR/$file"
  fi
done
if ! grep -q '^scope_id=P1-DATA-CUTOVER-04$' "$BACKUP_DIR/manifest.txt"; then
  fail "backup manifest is not for P1-DATA-CUTOVER-04"
fi

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
docker compose -f "$COMPOSE_FILE" stop backend >/dev/null 2>&1 || true
BACKEND_STOPPED=1
trap restart_backend EXIT HUP INT TERM

printf 'Recreating only the two boundary target databases for rollback...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
  set -eu
  if [ "$PLATFORM_POSTGRES_DB" = "$POSTGRES_DB" ] || \
     [ "$RESTAURANT_POSTGRES_DB" = "$POSTGRES_DB" ] || \
     [ "$PLATFORM_POSTGRES_DB" = "$RESTAURANT_POSTGRES_DB" ]; then
    echo "refusing to recreate non-distinct databases" >&2
    exit 2
  fi
  for database_name in "$PLATFORM_POSTGRES_DB" "$RESTAURANT_POSTGRES_DB"; do
    case "$database_name" in ""|*[!A-Za-z0-9_]*) exit 2 ;; esac
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
      -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '\''$database_name'\'' AND pid <> pg_backend_pid()" >/dev/null
    dropdb --if-exists -U "$POSTGRES_USER" "$database_name"
    createdb -U "$POSTGRES_USER" "$database_name"
  done
'

docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB"' < "$BACKUP_DIR/platform-before.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$RESTAURANT_POSTGRES_DB"' < "$BACKUP_DIR/restaurant-before.dump"

printf 'Boundary target rollback completed from: %s\n' "$BACKUP_DIR"
