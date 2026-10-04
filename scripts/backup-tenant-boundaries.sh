#!/bin/sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_ROOT="${P5_TENANT_BACKUP_ROOT:-backups}"
COMPANY_ID=""
REASON="Phase 5 tenant resilience backup"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

wait_for_postgres() {
  tries=0
  until docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
    tries=$((tries + 1))
    [ "$tries" -lt 30 ] || fail "postgres service did not become ready"
    sleep 2
  done
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --company-id)
      [ "$#" -ge 2 ] || fail "--company-id requires a UUID"
      COMPANY_ID="$2"
      shift 2
      ;;
    --reason)
      [ "$#" -ge 2 ] || fail "--reason requires text"
      REASON="$2"
      shift 2
      ;;
    --backup-root)
      [ "$#" -ge 2 ] || fail "--backup-root requires a path"
      BACKUP_ROOT="$2"
      shift 2
      ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[ -n "$COMPANY_ID" ] || fail "--company-id is required"
[ -f "$COMPOSE_FILE" ] || fail "compose file not found: $COMPOSE_FILE"

docker compose -f "$COMPOSE_FILE" up -d postgres >/dev/null
wait_for_postgres

legacy_database="${P5_LEGACY_DATABASE_NAME:-$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'printf %s "$POSTGRES_DB"')}"
platform_database="${P5_PLATFORM_DATABASE_NAME:-$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'printf %s "$PLATFORM_POSTGRES_DB"')}"
restaurant_database="${P5_RESTAURANT_DATABASE_NAME:-$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'printf %s "$RESTAURANT_POSTGRES_DB"')}"

[ -n "$legacy_database" ] || fail "legacy database name is empty"
[ -n "$platform_database" ] || fail "Platform database name is empty"
[ -n "$restaurant_database" ] || fail "Restaurant database name is empty"
if [ "$legacy_database" = "$platform_database" ] || [ "$legacy_database" = "$restaurant_database" ] || [ "$platform_database" = "$restaurant_database" ]; then
  fail "tenant boundary backup requires three distinct database names"
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${BACKUP_ROOT%/}/p5-tenant-boundaries-${timestamp}"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"

printf 'Creating Legacy, Platform and Restaurant boundary dumps...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$1"' sh "$legacy_database" \
  > "$backup_dir/legacy.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$1"' sh "$platform_database" \
  > "$backup_dir/platform-core.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$1"' sh "$restaurant_database" \
  > "$backup_dir/restaurant.dump"

printf 'Creating credential-redacted tenant evidence...\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e P5_LEGACY_DATABASE_NAME="$legacy_database" \
  -e P5_PLATFORM_DATABASE_NAME="$platform_database" \
  -e P5_RESTAURANT_DATABASE_NAME="$restaurant_database" \
  backend sh -c '
    set -eu
    legacy_server="${DATABASE_URL%/*}"
    platform_server="${PLATFORM_DATABASE_URL%/*}"
    restaurant_server="${RESTAURANT_DATABASE_URL%/*}"
    export DATABASE_URL="$legacy_server/$P5_LEGACY_DATABASE_NAME"
    export PLATFORM_DATABASE_URL="$platform_server/$P5_PLATFORM_DATABASE_NAME"
    export RESTAURANT_DATABASE_URL="$restaurant_server/$P5_RESTAURANT_DATABASE_NAME"
    exec python -B -m app.utils.export_tenant --company-id "$1" --reason "$2"
  ' sh "$COMPANY_ID" "$REASON" > "$backup_dir/tenant-export.json"

for artifact in legacy.dump platform-core.dump restaurant.dump tenant-export.json; do
  chmod 600 "$backup_dir/$artifact"
done

legacy_sha256="$(sha256_file "$backup_dir/legacy.dump")"
platform_sha256="$(sha256_file "$backup_dir/platform-core.dump")"
restaurant_sha256="$(sha256_file "$backup_dir/restaurant.dump")"
export_sha256="$(sha256_file "$backup_dir/tenant-export.json")"
content_sha256="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["content_sha256"])' "$backup_dir/tenant-export.json")"

cat > "$backup_dir/manifest.txt" <<EOF
scope=P5-TENANT-RESILIENCE-02
backup_timestamp_utc=$timestamp
company_id=$COMPANY_ID
legacy_source_database=$legacy_database
platform_source_database=$platform_database
restaurant_source_database=$restaurant_database
legacy_dump=legacy.dump
legacy_sha256=$legacy_sha256
platform_dump=platform-core.dump
platform_sha256=$platform_sha256
restaurant_dump=restaurant.dump
restaurant_sha256=$restaurant_sha256
tenant_export=tenant-export.json
tenant_export_sha256=$export_sha256
tenant_content_sha256=$content_sha256
credential_redaction=true
uploads_included=false
redis_included=false
reason=$REASON
EOF
chmod 600 "$backup_dir/manifest.txt"

printf 'Tenant boundary backup completed: %s\n' "$backup_dir"
printf 'Tenant content SHA-256: %s\n' "$content_sha256"
