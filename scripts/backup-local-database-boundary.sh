#!/bin/sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_ROOT="${1:-backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="${BACKUP_ROOT%/}/restaurant-boundaries-local-${TIMESTAMP}"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
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

if [ ! -f "$COMPOSE_FILE" ]; then
  fail "compose file not found: $COMPOSE_FILE"
fi

mkdir -p "$BACKUP_DIR"
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

printf 'Backing up platform_core database...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB"' \
  > "$BACKUP_DIR/platform-core.dump"

printf 'Backing up restaurant database...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$RESTAURANT_POSTGRES_DB"' \
  > "$BACKUP_DIR/restaurant.dump"

printf 'Backing up retail database...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "${RETAIL_POSTGRES_DB:-retail_ops_db}"' \
  > "$BACKUP_DIR/retail.dump"

printf 'Backing up takeaway database...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "${TAKEAWAY_POSTGRES_DB:-takeaway_ops_db}"' \
  > "$BACKUP_DIR/takeaway.dump"

platform_sha256="$(checksum_file "$BACKUP_DIR/platform-core.dump")"
restaurant_sha256="$(checksum_file "$BACKUP_DIR/restaurant.dump")"
retail_sha256="$(checksum_file "$BACKUP_DIR/retail.dump")"
takeaway_sha256="$(checksum_file "$BACKUP_DIR/takeaway.dump")"

cat > "$BACKUP_DIR/manifest.txt" <<EOF
backup_timestamp_utc=$TIMESTAMP
compose_file=$COMPOSE_FILE
platform_dump=platform-core.dump
restaurant_dump=restaurant.dump
retail_dump=retail.dump
takeaway_dump=takeaway.dump
platform_sha256=$platform_sha256
restaurant_sha256=$restaurant_sha256
retail_sha256=$retail_sha256
takeaway_sha256=$takeaway_sha256
legacy_database_included=false
scope_ids=P1-DATABASE-BOUNDARY-03,P6-TAKEAWAY-IMPLEMENTATION-06,WP7-RETAIL-SAAS-ALIGNMENT-01
EOF

chmod 600 "$BACKUP_DIR/platform-core.dump" "$BACKUP_DIR/restaurant.dump" "$BACKUP_DIR/retail.dump" "$BACKUP_DIR/takeaway.dump" "$BACKUP_DIR/manifest.txt"

printf 'Boundary backup completed: %s\n' "$BACKUP_DIR"
