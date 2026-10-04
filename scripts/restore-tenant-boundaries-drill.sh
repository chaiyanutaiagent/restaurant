#!/bin/sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_DIR=""
ASSUME_YES=0
CLEANUP="${P5_TENANT_DRILL_CLEANUP:-1}"
LEGACY_DRILL=""
PLATFORM_DRILL=""
RESTAURANT_DRILL=""
STARTED_AT="$(date +%s)"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

manifest_value() {
  key="$1"
  sed -n "s/^${key}=//p" "$BACKUP_DIR/manifest.txt" | head -n 1
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

drop_drill_database() {
  database_name="$1"
  case "$database_name" in
    restaurant_p5_resilience_legacy_[0-9]*|restaurant_p5_resilience_platform_[0-9]*|restaurant_p5_resilience_ops_[0-9]*)
      docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
        psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
          -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '\''$1'\'' AND pid <> pg_backend_pid()" >/dev/null
        dropdb --if-exists -U "$POSTGRES_USER" "$1"
      ' sh "$database_name" >/dev/null 2>&1 || true
      ;;
  esac
}

cleanup() {
  [ "$CLEANUP" = "1" ] || return 0
  [ -z "$LEGACY_DRILL" ] || drop_drill_database "$LEGACY_DRILL"
  [ -z "$PLATFORM_DRILL" ] || drop_drill_database "$PLATFORM_DRILL"
  [ -z "$RESTAURANT_DRILL" ] || drop_drill_database "$RESTAURANT_DRILL"
}
trap cleanup EXIT HUP INT TERM

while [ "$#" -gt 0 ]; do
  case "$1" in
    --yes) ASSUME_YES=1; shift ;;
    --keep-databases) CLEANUP=0; shift ;;
    -*) fail "unknown option: $1" ;;
    *)
      [ -z "$BACKUP_DIR" ] || fail "only one backup directory is supported"
      BACKUP_DIR="$1"
      shift
      ;;
  esac
done

[ "$ASSUME_YES" = "1" ] || fail "pass --yes to create and drop isolated drill databases"
[ -n "$BACKUP_DIR" ] || fail "backup directory argument is required"
[ -f "$COMPOSE_FILE" ] || fail "compose file not found: $COMPOSE_FILE"
for file in manifest.txt legacy.dump platform-core.dump restaurant.dump tenant-export.json; do
  [ -f "$BACKUP_DIR/$file" ] || fail "required backup file missing: $BACKUP_DIR/$file"
done

[ "$(sha256_file "$BACKUP_DIR/legacy.dump")" = "$(manifest_value legacy_sha256)" ] || fail "Legacy dump checksum mismatch"
[ "$(sha256_file "$BACKUP_DIR/platform-core.dump")" = "$(manifest_value platform_sha256)" ] || fail "Platform dump checksum mismatch"
[ "$(sha256_file "$BACKUP_DIR/restaurant.dump")" = "$(manifest_value restaurant_sha256)" ] || fail "Restaurant dump checksum mismatch"
[ "$(sha256_file "$BACKUP_DIR/tenant-export.json")" = "$(manifest_value tenant_export_sha256)" ] || fail "tenant export checksum mismatch"

company_id="$(manifest_value company_id)"
source_content_sha256="$(manifest_value tenant_content_sha256)"
[ -n "$company_id" ] || fail "manifest Company ID is missing"
[ -n "$source_content_sha256" ] || fail "manifest tenant content checksum is missing"

docker compose -f "$COMPOSE_FILE" up -d postgres >/dev/null
tries=0
until docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1))
  [ "$tries" -lt 30 ] || fail "postgres service did not become ready"
  sleep 2
done

suffix="$(date -u +%Y%m%d%H%M%S)$$"
LEGACY_DRILL="restaurant_p5_resilience_legacy_${suffix}"
PLATFORM_DRILL="restaurant_p5_resilience_platform_${suffix}"
RESTAURANT_DRILL="restaurant_p5_resilience_ops_${suffix}"

printf 'Simulating loss of isolated tenant boundaries, then restoring three fresh databases...\n'
for database_name in "$LEGACY_DRILL" "$PLATFORM_DRILL" "$RESTAURANT_DRILL"; do
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$database_name"
done
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$LEGACY_DRILL" \
  < "$BACKUP_DIR/legacy.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$PLATFORM_DRILL" \
  < "$BACKUP_DIR/platform-core.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$RESTAURANT_DRILL" \
  < "$BACKUP_DIR/restaurant.dump"

restored_export="$BACKUP_DIR/restored-tenant-export.json"
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e P5_LEGACY_DATABASE_NAME="$LEGACY_DRILL" \
  -e P5_PLATFORM_DATABASE_NAME="$PLATFORM_DRILL" \
  -e P5_RESTAURANT_DATABASE_NAME="$RESTAURANT_DRILL" \
  backend sh -c '
    set -eu
    legacy_server="${DATABASE_URL%/*}"
    platform_server="${PLATFORM_DATABASE_URL%/*}"
    restaurant_server="${RESTAURANT_DATABASE_URL%/*}"
    export DATABASE_URL="$legacy_server/$P5_LEGACY_DATABASE_NAME"
    export PLATFORM_DATABASE_URL="$platform_server/$P5_PLATFORM_DATABASE_NAME"
    export RESTAURANT_DATABASE_URL="$restaurant_server/$P5_RESTAURANT_DATABASE_NAME"
    exec python -B -m app.utils.export_tenant --company-id "$1" --reason "isolated restore verification"
  ' sh "$company_id" > "$restored_export"
chmod 600 "$restored_export"

restored_content_sha256="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["content_sha256"])' "$restored_export")"
[ "$source_content_sha256" = "$restored_content_sha256" ] || fail "restored tenant content checksum mismatch"

completed_at="$(date +%s)"
rto_seconds=$((completed_at - STARTED_AT))
evidence="$BACKUP_DIR/recovery-evidence-$(date -u +%Y%m%dT%H%M%SZ).txt"
cat > "$evidence" <<EOF
scope=P5-TENANT-RESILIENCE-02
incident=isolated_three_boundary_loss
recovery=three_boundary_pg_restore_and_tenant_export_verification
company_id=$company_id
source_content_sha256=$source_content_sha256
restored_content_sha256=$restored_content_sha256
content_match=true
rto_seconds=$rto_seconds
live_source_databases_modified=false
drill_databases_cleanup=$CLEANUP
status=passed
EOF
chmod 600 "$evidence"

printf 'Isolated tenant restore drill passed in %s seconds.\n' "$rto_seconds"
printf 'Recovery evidence: %s\n' "$evidence"
