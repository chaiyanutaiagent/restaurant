#!/bin/sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_ROOT="${CUTOVER_BACKUP_ROOT:-backups}"
ASSUME_YES=0
EXPECTED_LEGACY_HEAD="6b7c8d9e0f12"
PLATFORM_TABLES="companies brands branches brand_branches users roles permissions role_permissions user_branches refresh_tokens user_access_requests user_invitations audit_logs"
RESTAURANT_CRITICAL_TABLES="companies brands branches brand_branches users branch_settings products stock_locations stock_balances recipes recipe_ingredients dining_tables dining_sessions dining_orders dining_order_items kitchen_tickets sale_orders sale_order_items payments audit_logs"
BACKEND_STOPPED=0

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

validate_database_name() {
  case "$1" in
    ""|*[!A-Za-z0-9_]*) fail "invalid PostgreSQL database name: $1" ;;
  esac
}

restart_backend() {
  if [ "$BACKEND_STOPPED" = "1" ]; then
    docker compose -f "$COMPOSE_FILE" up -d backend >/dev/null 2>&1 || true
  fi
}

database_count() {
  database_name="$1"
  table_name="$2"
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'psql -U "$POSTGRES_USER" -d "$1" -tAc "SELECT count(*) FROM \"$2\""' \
    sh "$database_name" "$table_name" | tr -d '[:space:]'
}

write_counts() {
  database_name="$1"
  table_names="$2"
  output_file="$3"
  : > "$output_file"
  for table_name in $table_names; do
    printf '%s=%s\n' "$table_name" "$(database_count "$database_name" "$table_name")" >> "$output_file"
  done
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --yes)
      ASSUME_YES=1
      shift
      ;;
    --backup-root)
      [ "$#" -ge 2 ] || fail "--backup-root requires a path"
      BACKUP_ROOT="$2"
      shift 2
      ;;
    *) fail "unknown argument: $1" ;;
  esac
done

if [ "$ASSUME_YES" != "1" ]; then
  fail "this rehearsal recreates only the two boundary target databases; pass --yes"
fi
if [ ! -f "$COMPOSE_FILE" ]; then
  fail "compose file not found: $COMPOSE_FILE"
fi

docker compose -f "$COMPOSE_FILE" up -d postgres redis >/dev/null
tries=0
until docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1))
  if [ "$tries" -ge 30 ]; then
    fail "postgres service did not become ready"
  fi
  sleep 2
done

legacy_database="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'printf %s "$POSTGRES_DB"')"
platform_database="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'printf %s "$PLATFORM_POSTGRES_DB"')"
restaurant_database="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'printf %s "$RESTAURANT_POSTGRES_DB"')"
validate_database_name "$legacy_database"
validate_database_name "$platform_database"
validate_database_name "$restaurant_database"
if [ "$legacy_database" = "$platform_database" ] || [ "$legacy_database" = "$restaurant_database" ] || [ "$platform_database" = "$restaurant_database" ]; then
  fail "legacy, Platform and Restaurant database names must be distinct"
fi

legacy_head="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT version_num FROM alembic_version"' | tr -d '[:space:]')"
if [ "$legacy_head" != "$EXPECTED_LEGACY_HEAD" ]; then
  fail "legacy migration head is $legacy_head; expected $EXPECTED_LEGACY_HEAD"
fi

printf 'Building migration image before maintenance window...\n'
docker compose -f "$COMPOSE_FILE" build backend >/dev/null

printf 'Stopping backend writer...\n'
docker compose -f "$COMPOSE_FILE" stop backend >/dev/null
BACKEND_STOPPED=1
trap restart_backend EXIT HUP INT TERM

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${BACKUP_ROOT%/}/p1-data-cutover-04-${timestamp}"
mkdir -p "$backup_dir"

printf 'Backing up legacy source and both pre-rehearsal targets...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$backup_dir/legacy-source.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB"' > "$backup_dir/platform-before.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$RESTAURANT_POSTGRES_DB"' > "$backup_dir/restaurant-before.dump"

write_counts "$legacy_database" "$PLATFORM_TABLES" "$backup_dir/legacy-platform-counts.txt"
write_counts "$legacy_database" "$RESTAURANT_CRITICAL_TABLES" "$backup_dir/legacy-restaurant-counts.txt"

cat > "$backup_dir/manifest.txt" <<EOF
scope_id=P1-DATA-CUTOVER-04
rehearsal_status=backup_complete
snapshot_timestamp_utc=$timestamp
legacy_database=$legacy_database
legacy_migration_head=$legacy_head
platform_database=$platform_database
restaurant_database=$restaurant_database
runtime_system_of_record=legacy
platform_system_of_record=false
restaurant_system_of_record=false
contents=legacy-source.dump platform-before.dump restaurant-before.dump legacy-platform-counts.txt legacy-restaurant-counts.txt manifest.txt
EOF

printf 'Recreating only the two rehearsal target databases...\n'
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

printf 'Restoring the same legacy snapshot into both targets...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB"' < "$backup_dir/legacy-source.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$RESTAURANT_POSTGRES_DB"' < "$backup_dir/legacy-source.dump"

printf 'Preserving the legacy schema head and pruning Platform operational tables...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB" -c "ALTER TABLE alembic_version RENAME TO legacy_alembic_version; ALTER TABLE legacy_alembic_version RENAME CONSTRAINT alembic_version_pkc TO legacy_alembic_version_pkc"'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$RESTAURANT_POSTGRES_DB" -c "ALTER TABLE alembic_version RENAME TO legacy_alembic_version; ALTER TABLE legacy_alembic_version RENAME CONSTRAINT alembic_version_pkc TO legacy_alembic_version_pkc"'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB" -f /opt/restaurant/platform-control-plane-prune.psql'

printf 'Applying independent Platform and Restaurant migration histories...\n'
COMPOSE_FILE="$COMPOSE_FILE" scripts/run-boundary-migrations.sh

write_counts "$platform_database" "$PLATFORM_TABLES" "$backup_dir/platform-after-counts.txt"
write_counts "$restaurant_database" "$RESTAURANT_CRITICAL_TABLES" "$backup_dir/restaurant-after-counts.txt"
cmp "$backup_dir/legacy-platform-counts.txt" "$backup_dir/platform-after-counts.txt" >/dev/null \
  || fail "Platform row-count parity failed"
cmp "$backup_dir/legacy-restaurant-counts.txt" "$backup_dir/restaurant-after-counts.txt" >/dev/null \
  || fail "Restaurant critical row-count parity failed"

platform_operational_tables="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB" -tAc "$1"' sh \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('dining_sessions', 'sale_orders', 'products', 'stock_balances', 'recipes')" | tr -d '[:space:]')"
if [ "$platform_operational_tables" != "0" ]; then
  fail "Platform database still contains Restaurant operational tables"
fi

cat > "$backup_dir/manifest.txt" <<EOF
scope_id=P1-DATA-CUTOVER-04
rehearsal_status=verified
snapshot_timestamp_utc=$timestamp
legacy_database=$legacy_database
legacy_migration_head=$legacy_head
platform_database=$platform_database
restaurant_database=$restaurant_database
runtime_system_of_record=legacy
platform_system_of_record=false
restaurant_system_of_record=false
contents=legacy-source.dump platform-before.dump restaurant-before.dump legacy-platform-counts.txt platform-after-counts.txt legacy-restaurant-counts.txt restaurant-after-counts.txt manifest.txt
EOF

printf 'Data cutover rehearsal passed: %s\n' "$backup_dir"
