#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_ROOT="${RESTAURANT_CUTOVER_BACKUP_ROOT:-backups}"
ASSUME_YES=0
EXPECTED_LEGACY_HEAD="6b7c8d9e0f12"
EXPECTED_PLATFORM_HEAD="p1platform0003"
EXPECTED_RESTAURANT_HEAD="p1restaurant0003"
INTERNAL_BASE_URL="http://127.0.0.1:8000"
CANARY_ACTIVE=0

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

rollback_on_exit() {
  if [[ "$CANARY_ACTIVE" = "1" ]]; then
    IDENTITY_DATABASE=legacy \
    RESTAURANT_SERVICE_DATABASE=legacy \
    REFERENCE_PROJECTOR_ENABLED=false \
      docker compose -f "$COMPOSE_FILE" up -d --force-recreate backend >/dev/null 2>&1 || true
  fi
}

trap rollback_on_exit EXIT HUP INT TERM

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --yes)
      ASSUME_YES=1
      shift
      ;;
    --backup-root)
      [[ "$#" -ge 2 ]] || fail "--backup-root requires a path"
      BACKUP_ROOT="$2"
      shift 2
      ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[[ "$ASSUME_YES" = "1" ]] || fail "this rehearsal recreates boundary targets and writes bounded UAT records; pass --yes"
[[ -f "$COMPOSE_FILE" ]] || fail "compose file not found: $COMPOSE_FILE"
command -v node >/dev/null 2>&1 || fail "node is required to parse API responses"

compose_backend() {
  IDENTITY_DATABASE="$1" \
  RESTAURANT_SERVICE_DATABASE="$2" \
  REFERENCE_PROJECTOR_ENABLED="$3" \
    docker compose -f "$COMPOSE_FILE" "${@:4}"
}

json_get() {
  node -e 'const fs=require("fs"); let value=JSON.parse(fs.readFileSync(0,"utf8")); for (const key of process.argv[1].split(".")) value=value?.[key]; if (value===undefined||value===null) process.exit(2); console.log(typeof value === "object" ? JSON.stringify(value) : value)' "$1"
}

wait_ready() {
  expected_identity="$1"
  expected_restaurant="$2"
  expected_projector="$3"
  tries=0
  while true; do
    health_json="$(docker compose -f "$COMPOSE_FILE" exec -T backend \
      python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/health/ready", timeout=5).read().decode())' 2>/dev/null || true)"
    if [[ -n "$health_json" ]]; then
      actual_identity="$(printf '%s' "$health_json" | json_get runtime.identity_database)"
      actual_restaurant="$(printf '%s' "$health_json" | json_get runtime.restaurant_service_database)"
      actual_projector="$(printf '%s' "$health_json" | json_get runtime.reference_projector_enabled)"
      projector_running="$(printf '%s' "$health_json" | json_get runtime.reference_projector_running)"
      if [[ "$actual_identity" = "$expected_identity" && \
            "$actual_restaurant" = "$expected_restaurant" && \
            "$actual_projector" = "$expected_projector" && \
            ("$expected_projector" = "false" || "$projector_running" = "true") ]]; then
        break
      fi
    fi
    tries=$((tries + 1))
    [[ "$tries" -lt 30 ]] || fail "backend did not become ready in $expected_identity/$expected_restaurant/$expected_projector mode"
    sleep 1
  done
}

http_json() {
  method="$1"
  path="$2"
  body="${3:-}"
  token="${4:-}"
  docker compose -f "$COMPOSE_FILE" exec -T backend python -c 'import sys, urllib.error, urllib.request
method, url, body, token = sys.argv[1:5]
headers = {"Content-Type": "application/json"}
if token:
    headers["Authorization"] = f"Bearer {token}"
request = urllib.request.Request(url, data=body.encode() if body else None, headers=headers, method=method)
try:
    response = urllib.request.urlopen(request, timeout=10)
    print(response.read().decode())
except urllib.error.HTTPError as exc:
    sys.stderr.write(exc.read().decode() + "\n")
    raise' "$method" "$INTERNAL_BASE_URL$path" "$body" "$token"
}

http_status() {
  method="$1"
  path="$2"
  body="${3:-}"
  token="${4:-}"
  docker compose -f "$COMPOSE_FILE" exec -T backend python -c 'import sys, urllib.error, urllib.request
method, url, body, token = sys.argv[1:5]
headers = {"Content-Type": "application/json"}
if token:
    headers["Authorization"] = f"Bearer {token}"
request = urllib.request.Request(url, data=body.encode() if body else None, headers=headers, method=method)
try:
    response = urllib.request.urlopen(request, timeout=10)
    print(response.status)
except urllib.error.HTTPError as exc:
    print(exc.code)' "$method" "$INTERNAL_BASE_URL$path" "$body" "$token"
}

psql_legacy() {
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "$1"' sh "$1" | tr -d '[:space:]'
}

psql_platform() {
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'psql -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB" -tAc "$1"' sh "$1" | tr -d '[:space:]'
}

psql_restaurant() {
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'psql -U "$POSTGRES_USER" -d "$RESTAURANT_POSTGRES_DB" -tAc "$1"' sh "$1" | tr -d '[:space:]'
}

login() {
  company_id="$1"
  branch_id="$2"
  expected_identity="$3"
  response="$(http_json POST /api/v1/auth/login "{\"company_id\":\"$company_id\",\"branch_id\":\"$branch_id\",\"username\":\"admin\",\"password\":\"${DEFAULT_ADMIN_PASSWORD:?DEFAULT_ADMIN_PASSWORD is required}\"}")"
  actual_identity="$(printf '%s' "$response" | json_get meta.identity_database)"
  [[ "$actual_identity" = "$expected_identity" ]] || fail "login used $actual_identity instead of $expected_identity"
  printf '%s' "$response"
}

printf 'Starting physical databases...\n'
docker compose -f "$COMPOSE_FILE" up -d postgres redis >/dev/null

legacy_head="$(psql_legacy 'SELECT version_num FROM alembic_version')"
platform_head="$(psql_platform 'SELECT version_num FROM alembic_version')"
restaurant_head="$(psql_restaurant 'SELECT version_num FROM alembic_version')"
[[ "$legacy_head" = "$EXPECTED_LEGACY_HEAD" ]] || fail "unexpected legacy head: $legacy_head"
[[ "$platform_head" = "$EXPECTED_PLATFORM_HEAD" ]] || fail "unexpected Platform head: $platform_head"
[[ "$restaurant_head" = "$EXPECTED_RESTAURANT_HEAD" ]] || fail "unexpected Restaurant head: $restaurant_head"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${BACKUP_ROOT%/}/p1-restaurant-runtime-canary-07-${timestamp}"
mkdir -p "$backup_dir"

printf 'Forcing rollback-safe legacy runtime before the maintenance snapshot...\n'
compose_backend legacy legacy false up -d --force-recreate backend >/dev/null
wait_ready legacy legacy false

printf 'Freshly rebaselining both targets from the current legacy source...\n'
scripts/rehearse-local-data-cutover.sh \
  --yes \
  --backup-root "$backup_dir/rebaseline"
compose_backend legacy legacy false up -d --force-recreate backend >/dev/null
wait_ready legacy legacy false

printf 'Seeding and verifying Platform reference projections...\n'
projection_output="$(docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e IDENTITY_DATABASE=legacy \
  -e RESTAURANT_SERVICE_DATABASE=legacy \
  -e REFERENCE_PROJECTOR_ENABLED=false \
  backend python -m app.utils.project_platform_references --seed-snapshot --drain --verify)"
printf '%s\n' "$projection_output"

legacy_head="$(psql_legacy 'SELECT version_num FROM alembic_version')"
platform_head="$(psql_platform 'SELECT version_num FROM alembic_version')"
restaurant_head="$(psql_restaurant 'SELECT version_num FROM alembic_version')"
[[ "$legacy_head" = "$EXPECTED_LEGACY_HEAD" ]] || fail "legacy head changed during rebaseline"
[[ "$platform_head" = "$EXPECTED_PLATFORM_HEAD" ]] || fail "unexpected rebaselined Platform head: $platform_head"
[[ "$restaurant_head" = "$EXPECTED_RESTAURANT_HEAD" ]] || fail "unexpected rebaselined Restaurant head: $restaurant_head"

printf 'Backing up the fresh three-database canary baseline...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$backup_dir/legacy-before.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB"' > "$backup_dir/platform-before.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$RESTAURANT_POSTGRES_DB"' > "$backup_dir/restaurant-before.dump"

cat > "$backup_dir/manifest.txt" <<EOF
scope_id=P1-RESTAURANT-RUNTIME-CANARY-07
rehearsal_status=backup_complete
snapshot_timestamp_utc=$timestamp
legacy_migration_head=$legacy_head
platform_migration_head=$platform_head
restaurant_migration_head=$restaurant_head
runtime_identity_database=legacy
runtime_restaurant_service_database=legacy
contents=legacy-before.dump platform-before.dump restaurant-before.dump rebaseline manifest.txt
EOF

printf 'Verifying Restaurant service startup guards...\n'
set +e
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e IDENTITY_DATABASE=legacy \
  -e RESTAURANT_SERVICE_DATABASE=restaurant \
  -e REFERENCE_PROJECTOR_ENABLED=true \
  backend python -c 'from fastapi.testclient import TestClient; from app.main import app; TestClient(app).__enter__()' \
  >/dev/null 2>&1
guard_identity_status=$?
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e IDENTITY_DATABASE=platform_core \
  -e RESTAURANT_SERVICE_DATABASE=restaurant \
  -e REFERENCE_PROJECTOR_ENABLED=false \
  backend python -c 'from fastapi.testclient import TestClient; from app.main import app; TestClient(app).__enter__()' \
  >/dev/null 2>&1
guard_projector_status=$?
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e IDENTITY_DATABASE=platform_core \
  -e RESTAURANT_SERVICE_DATABASE=restaurant \
  -e REFERENCE_PROJECTOR_ENABLED=true \
  backend sh -c 'export RESTAURANT_DATABASE_URL="$DATABASE_URL"; python -c '\''from fastapi.testclient import TestClient; from app.main import app; TestClient(app).__enter__()'\''' \
  >/dev/null 2>&1
guard_boundary_status=$?
set -e
[[ "$guard_identity_status" -ne 0 ]] || fail "Restaurant service started without Platform identity"
[[ "$guard_projector_status" -ne 0 ]] || fail "Restaurant service started without projector"
[[ "$guard_boundary_status" -ne 0 ]] || fail "Restaurant service started without physical boundary"

company_id="$(psql_platform 'SELECT id FROM companies WHERE is_active ORDER BY created_at LIMIT 1')"
admin_id="$(psql_platform "SELECT id FROM users WHERE company_id = '$company_id' AND username = 'admin' AND deleted_at IS NULL")"
branch_id="$(psql_platform "SELECT branch_id FROM user_branches WHERE user_id = '$admin_id' AND deleted_at IS NULL ORDER BY is_default DESC, created_at LIMIT 1")"
[[ -n "$company_id" && -n "$branch_id" && -n "$admin_id" ]] || fail "default identity seed is missing"

legacy_settings_hash="$(psql_legacy "SELECT md5(row_to_json(s)::text) FROM branch_settings s WHERE branch_id = '$branch_id'")"
restaurant_settings_hash="$(psql_restaurant "SELECT md5(row_to_json(s)::text) FROM branch_settings s WHERE branch_id = '$branch_id'")"
[[ -n "$legacy_settings_hash" && "$legacy_settings_hash" = "$restaurant_settings_hash" ]] \
  || fail "Branch Settings snapshot parity failed before canary"

printf 'Running legacy baseline...\n'
DEFAULT_ADMIN_PASSWORD="$(docker compose -f "$COMPOSE_FILE" exec -T backend \
  sh -c 'printf %s "$DEFAULT_ADMIN_PASSWORD"')"
[[ -n "$DEFAULT_ADMIN_PASSWORD" ]] || fail "DEFAULT_ADMIN_PASSWORD is required"
legacy_login="$(login "$company_id" "$branch_id" legacy)"
legacy_access="$(printf '%s' "$legacy_login" | json_get data.access_token)"
legacy_settings="$(http_json GET "/api/v1/system/branches/$branch_id/settings" '' "$legacy_access")"
[[ "$(printf '%s' "$legacy_settings" | json_get meta.restaurant_service_database)" = "legacy" ]] \
  || fail "legacy settings response did not identify legacy source"
original_receipt_copies="$(printf '%s' "$legacy_settings" | json_get data.receipt_copies)"
if [[ "$original_receipt_copies" = "1" ]]; then
  canary_receipt_copies=2
else
  canary_receipt_copies=1
fi

legacy_sessions_before="$(psql_legacy 'SELECT count(*) FROM dining_sessions')"
restaurant_sessions_before="$(psql_restaurant 'SELECT count(*) FROM dining_sessions')"
legacy_sales_before="$(psql_legacy 'SELECT count(*) FROM sale_orders')"
restaurant_sales_before="$(psql_restaurant 'SELECT count(*) FROM sale_orders')"

printf 'Running Platform identity + Restaurant service canary...\n'
canary_started_at="$(psql_restaurant 'SELECT extract(epoch FROM clock_timestamp())')"
CANARY_ACTIVE=1
compose_backend platform_core restaurant true up -d --force-recreate backend >/dev/null
wait_ready platform_core restaurant true

platform_login="$(login "$company_id" "$branch_id" platform_core)"
platform_access="$(printf '%s' "$platform_login" | json_get data.access_token)"
[[ "$(http_status GET /api/v1/auth/me '' "$platform_access")" = "200" ]] \
  || fail "Platform /auth/me failed during Restaurant canary"

settings_update="$(http_json PATCH "/api/v1/system/branches/$branch_id/settings" \
  "{\"receipt_copies\":$canary_receipt_copies}" "$platform_access")"
[[ "$(printf '%s' "$settings_update" | json_get meta.restaurant_service_database)" = "restaurant" ]] \
  || fail "settings update did not identify Restaurant source"
[[ "$(printf '%s' "$settings_update" | json_get data.receipt_copies)" = "$canary_receipt_copies" ]] \
  || fail "settings API did not return the canary value"
[[ "$(psql_restaurant "SELECT receipt_copies FROM branch_settings WHERE branch_id = '$branch_id'")" = "$canary_receipt_copies" ]] \
  || fail "settings canary value was not written to Restaurant"
[[ "$(psql_legacy "SELECT receipt_copies FROM branch_settings WHERE branch_id = '$branch_id'")" = "$original_receipt_copies" ]] \
  || fail "settings canary value leaked to legacy"
[[ "$(psql_restaurant "SELECT count(*) FROM audit_logs WHERE action = 'system.branch.settings_updated' AND resource_id = '$branch_id' AND created_at >= to_timestamp($canary_started_at)")" -ge 1 ]] \
  || fail "Restaurant settings audit was not written"
[[ "$(psql_legacy "SELECT count(*) FROM audit_logs WHERE action = 'system.branch.settings_updated' AND resource_id = '$branch_id' AND created_at >= to_timestamp($canary_started_at)")" = "0" ]] \
  || fail "Restaurant settings audit leaked to legacy"

fb_settings="$(http_json GET /api/v1/restaurant/settings '' "$platform_access")"
[[ "$(printf '%s' "$fb_settings" | json_get data.receipt_copies)" = "$canary_receipt_copies" ]] \
  || fail "F&B settings did not read the Restaurant canary value"

printf 'Running the full F&B workflow against the Restaurant database...\n'
FNB_SMOKE_DATABASE=restaurant scripts/fnb-smoke.sh

printf 'Running the F&B permission matrix across the canary ownership boundary...\n'
FNB_PERMISSION_IDENTITY_DATABASE=platform_core \
FNB_PERMISSION_SERVICE_DATABASE=restaurant \
  scripts/fnb-permission-smoke.sh

legacy_sessions_after="$(psql_legacy 'SELECT count(*) FROM dining_sessions')"
restaurant_sessions_after="$(psql_restaurant 'SELECT count(*) FROM dining_sessions')"
legacy_sales_after="$(psql_legacy 'SELECT count(*) FROM sale_orders')"
restaurant_sales_after="$(psql_restaurant 'SELECT count(*) FROM sale_orders')"
[[ "$legacy_sessions_after" = "$legacy_sessions_before" ]] \
  || fail "F&B canary session writes leaked to legacy"
[[ "$legacy_sales_after" = "$legacy_sales_before" ]] \
  || fail "F&B canary sale writes leaked to legacy"
[[ "$restaurant_sessions_after" -ge $((restaurant_sessions_before + 2)) ]] \
  || fail "F&B canary did not create the expected Restaurant sessions"
[[ "$restaurant_sales_after" -ge $((restaurant_sales_before + 2)) ]] \
  || fail "F&B canary did not create the expected Restaurant sales"

printf 'Restoring the bounded settings value before rollback...\n'
settings_restore="$(http_json PATCH "/api/v1/system/branches/$branch_id/settings" \
  "{\"receipt_copies\":$original_receipt_copies}" "$platform_access")"
[[ "$(printf '%s' "$settings_restore" | json_get data.receipt_copies)" = "$original_receipt_copies" ]] \
  || fail "settings API did not restore the original value"
[[ "$(psql_restaurant "SELECT receipt_copies FROM branch_settings WHERE branch_id = '$branch_id'")" = "$original_receipt_copies" ]] \
  || fail "Restaurant settings value was not restored"

printf 'Rolling identity and Restaurant service routes back to legacy...\n'
compose_backend legacy legacy false up -d --force-recreate backend >/dev/null
wait_ready legacy legacy false
CANARY_ACTIVE=0
[[ "$(http_status GET /api/v1/auth/me '' "$platform_access")" = "200" ]] \
  || fail "signed access token did not survive Restaurant route rollback"
rollback_settings="$(http_json GET "/api/v1/system/branches/$branch_id/settings" '' "$platform_access")"
[[ "$(printf '%s' "$rollback_settings" | json_get meta.restaurant_service_database)" = "legacy" ]] \
  || fail "Branch Settings did not roll back to legacy"
[[ "$(printf '%s' "$rollback_settings" | json_get data.receipt_copies)" = "$original_receipt_copies" ]] \
  || fail "legacy settings changed during Restaurant canary"

printf 'Verifying final reference parity...\n'
final_projection="$(docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e IDENTITY_DATABASE=legacy \
  -e RESTAURANT_SERVICE_DATABASE=legacy \
  -e REFERENCE_PROJECTOR_ENABLED=false \
  backend python -m app.utils.project_platform_references --seed-snapshot --drain --verify)"
printf '%s\n' "$final_projection"

legacy_head_after="$(psql_legacy 'SELECT version_num FROM alembic_version')"
platform_head_after="$(psql_platform 'SELECT version_num FROM alembic_version')"
restaurant_head_after="$(psql_restaurant 'SELECT version_num FROM alembic_version')"
[[ "$legacy_head_after" = "$legacy_head" ]] || fail "legacy migration head changed"
[[ "$platform_head_after" = "$platform_head" ]] || fail "Platform migration head changed"
[[ "$restaurant_head_after" = "$restaurant_head" ]] || fail "Restaurant migration head changed"

printf 'Creating and restore-drilling the final boundary backup...\n'
boundary_backup_output="$(scripts/backup-local-database-boundary.sh "$backup_dir/final-boundary")"
printf '%s\n' "$boundary_backup_output"
boundary_backup_dir="$(printf '%s\n' "$boundary_backup_output" | sed -n 's/^Boundary backup completed: //p')"
[[ -n "$boundary_backup_dir" ]] || fail "could not resolve final boundary backup directory"
BOUNDARY_DRILL_SUFFIX="p1canary07_${timestamp}" \
BOUNDARY_DRILL_CLEANUP=1 \
  scripts/restore-local-database-boundary-drill.sh "$boundary_backup_dir"

cat > "$backup_dir/manifest.txt" <<EOF
scope_id=P1-RESTAURANT-RUNTIME-CANARY-07
rehearsal_status=verified
snapshot_timestamp_utc=$timestamp
legacy_migration_head=$legacy_head_after
platform_migration_head=$platform_head_after
restaurant_migration_head=$restaurant_head_after
final_runtime_identity_database=legacy
final_runtime_restaurant_service_database=legacy
final_reference_projector_enabled=false
startup_identity_guard=true
startup_projector_guard=true
startup_physical_boundary_guard=true
settings_write_isolated_to_restaurant=true
settings_audit_isolated_to_restaurant=true
settings_canary_value_restored=true
fnb_sessions_legacy_before=$legacy_sessions_before
fnb_sessions_legacy_after=$legacy_sessions_after
fnb_sessions_restaurant_before=$restaurant_sessions_before
fnb_sessions_restaurant_after=$restaurant_sessions_after
fnb_sales_legacy_before=$legacy_sales_before
fnb_sales_legacy_after=$legacy_sales_after
fnb_sales_restaurant_before=$restaurant_sales_before
fnb_sales_restaurant_after=$restaurant_sales_after
final_boundary_backup=$boundary_backup_dir
final_restore_drill=true
contents=legacy-before.dump platform-before.dump restaurant-before.dump rebaseline final-boundary manifest.txt
EOF

printf 'Restaurant service cutover rehearsal passed: %s\n' "$backup_dir"
