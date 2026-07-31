#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_ROOT="${IDENTITY_CUTOVER_BACKUP_ROOT:-backups}"
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
    IDENTITY_DATABASE=legacy REFERENCE_PROJECTOR_ENABLED=false \
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

[[ "$ASSUME_YES" = "1" ]] || fail "this rehearsal writes identity canary records; pass --yes"
[[ -f "$COMPOSE_FILE" ]] || fail "compose file not found: $COMPOSE_FILE"
command -v node >/dev/null 2>&1 || fail "node is required to parse API responses"

compose_backend() {
  IDENTITY_DATABASE="$1" REFERENCE_PROJECTOR_ENABLED="$2" \
    docker compose -f "$COMPOSE_FILE" "${@:3}"
}

wait_ready() {
  expected_identity="$1"
  expected_projector="$2"
  tries=0
  while true; do
    health_json="$(docker compose -f "$COMPOSE_FILE" exec -T backend \
      python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/health/ready", timeout=5).read().decode())' 2>/dev/null || true)"
    if [[ -n "$health_json" ]]; then
      actual_identity="$(printf '%s' "$health_json" | json_get runtime.identity_database)"
      actual_projector="$(printf '%s' "$health_json" | json_get runtime.reference_projector_enabled)"
      projector_running="$(printf '%s' "$health_json" | json_get runtime.reference_projector_running)"
      if [[ "$actual_identity" = "$expected_identity" && \
            "$actual_projector" = "$expected_projector" && \
            ("$expected_projector" = "false" || "$projector_running" = "true") ]]; then
        break
      fi
    fi
    tries=$((tries + 1))
    [[ "$tries" -lt 30 ]] || fail "backend did not become ready"
    sleep 1
  done
}

json_get() {
  node -e 'const fs=require("fs"); let value=JSON.parse(fs.readFileSync(0,"utf8")); for (const key of process.argv[1].split(".")) value=value?.[key]; if (value===undefined||value===null) process.exit(2); console.log(typeof value === "object" ? JSON.stringify(value) : value)' "$1"
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

token_hash() {
  TOKEN_TO_HASH="$1" python3 -c 'import hashlib, os; print(hashlib.sha256(os.environ["TOKEN_TO_HASH"].encode()).hexdigest())'
}

login() {
  company_id="$1"
  branch_id="$2"
  response="$(http_json POST /api/v1/auth/login "{\"company_id\":\"$company_id\",\"branch_id\":\"$branch_id\",\"username\":\"admin\",\"password\":\"${DEFAULT_ADMIN_PASSWORD:?DEFAULT_ADMIN_PASSWORD is required}\"}")"
  actual_identity="$(printf '%s' "$response" | json_get meta.identity_database)"
  [[ "$actual_identity" = "$3" ]] || fail "login used $actual_identity instead of $3"
  printf '%s' "$response"
}

printf 'Starting physical databases and building the canary image...\n'
docker compose -f "$COMPOSE_FILE" up -d postgres redis >/dev/null
docker compose -f "$COMPOSE_FILE" build backend >/dev/null

legacy_head="$(psql_legacy 'SELECT version_num FROM alembic_version')"
platform_head="$(psql_platform 'SELECT version_num FROM alembic_version')"
restaurant_head="$(psql_restaurant 'SELECT version_num FROM alembic_version')"
[[ "$legacy_head" = "$EXPECTED_LEGACY_HEAD" ]] || fail "unexpected legacy head: $legacy_head"
[[ "$platform_head" = "$EXPECTED_PLATFORM_HEAD" ]] || fail "unexpected Platform head: $platform_head"
[[ "$restaurant_head" = "$EXPECTED_RESTAURANT_HEAD" ]] || fail "unexpected Restaurant head: $restaurant_head"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${BACKUP_ROOT%/}/p1-runtime-cutover-06-${timestamp}"
mkdir -p "$backup_dir"
printf 'Backing up all three databases before identity canary...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$backup_dir/legacy-before.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB"' > "$backup_dir/platform-before.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$RESTAURANT_POSTGRES_DB"' > "$backup_dir/restaurant-before.dump"

cat > "$backup_dir/manifest.txt" <<EOF
scope_id=P1-RUNTIME-CUTOVER-06
rehearsal_status=backup_complete
snapshot_timestamp_utc=$timestamp
legacy_migration_head=$legacy_head
platform_migration_head=$platform_head
restaurant_migration_head=$restaurant_head
runtime_identity_database=legacy
contents=legacy-before.dump platform-before.dump restaurant-before.dump manifest.txt
EOF

printf 'Verifying startup guards...\n'
set +e
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e IDENTITY_DATABASE=platform_core \
  -e REFERENCE_PROJECTOR_ENABLED=false \
  backend python -c 'from fastapi.testclient import TestClient; from app.main import app; TestClient(app).__enter__()' \
  >/dev/null 2>&1
guard_projector_status=$?
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e IDENTITY_DATABASE=platform_core \
  -e REFERENCE_PROJECTOR_ENABLED=true \
  backend sh -c 'export PLATFORM_DATABASE_URL="$DATABASE_URL"; python -c '\''from fastapi.testclient import TestClient; from app.main import app; TestClient(app).__enter__()'\''' \
  >/dev/null 2>&1
guard_boundary_status=$?
set -e
[[ "$guard_projector_status" -ne 0 ]] || fail "Platform identity started without projector"
[[ "$guard_boundary_status" -ne 0 ]] || fail "Platform identity started without physical boundary"

company_id="$(psql_legacy "SELECT id FROM companies WHERE is_active ORDER BY created_at LIMIT 1")"
admin_id="$(psql_legacy "SELECT id FROM users WHERE company_id = '$company_id' AND username = 'admin' AND deleted_at IS NULL")"
branch_id="$(psql_platform "SELECT branch_id FROM user_branches WHERE user_id = '$admin_id' AND deleted_at IS NULL ORDER BY is_default DESC, created_at LIMIT 1")"
[[ -n "$company_id" && -n "$branch_id" && -n "$admin_id" ]] || fail "default identity seed is missing"
[[ "$(psql_legacy "SELECT count(*) FROM user_branches WHERE user_id = '$admin_id' AND branch_id = '$branch_id' AND deleted_at IS NULL")" = "1" ]] \
  || fail "admin assignment is not shared by the legacy rollback source"

printf 'Running legacy baseline...\n'
compose_backend legacy false up -d --force-recreate backend >/dev/null
wait_ready legacy false
DEFAULT_ADMIN_PASSWORD="$(docker compose -f "$COMPOSE_FILE" exec -T backend \
  sh -c 'printf %s "$DEFAULT_ADMIN_PASSWORD"')"
[[ -n "$DEFAULT_ADMIN_PASSWORD" ]] || fail "DEFAULT_ADMIN_PASSWORD is required"
legacy_login="$(login "$company_id" "$branch_id" legacy)"
legacy_access="$(printf '%s' "$legacy_login" | json_get data.access_token)"
legacy_refresh="$(printf '%s' "$legacy_login" | json_get data.refresh_token)"
[[ "$(http_status GET /api/v1/auth/me '' "$legacy_access")" = "200" ]] || fail "legacy /auth/me failed"
legacy_refresh_hash="$(token_hash "$legacy_refresh")"
[[ "$(psql_legacy "SELECT count(*) FROM refresh_tokens WHERE token_hash = '$legacy_refresh_hash'")" = "1" ]] \
  || fail "legacy baseline refresh token was not written to legacy"
[[ "$(psql_platform "SELECT count(*) FROM refresh_tokens WHERE token_hash = '$legacy_refresh_hash'")" = "0" ]] \
  || fail "legacy baseline refresh token leaked to Platform"

printf 'Running Platform identity canary...\n'
canary_started_at="$(psql_platform "SELECT extract(epoch FROM clock_timestamp())")"
CANARY_ACTIVE=1
compose_backend platform_core true up -d --force-recreate backend >/dev/null
wait_ready platform_core true
platform_login="$(login "$company_id" "$branch_id" platform_core)"
platform_access="$(printf '%s' "$platform_login" | json_get data.access_token)"
platform_refresh="$(printf '%s' "$platform_login" | json_get data.refresh_token)"
[[ "$(http_status GET /api/v1/auth/me '' "$platform_access")" = "200" ]] || fail "Platform /auth/me failed"
[[ "$(http_status GET /api/v1/auth/permissions '' "$platform_access")" = "200" ]] \
  || fail "Platform /auth/permissions failed"
[[ "$(http_status GET /api/v1/restaurant/brands '' "$platform_access")" = "200" ]] \
  || fail "Platform identity token could not access legacy Restaurant operation"

platform_refresh_hash="$(token_hash "$platform_refresh")"
[[ "$(psql_platform "SELECT count(*) FROM refresh_tokens WHERE token_hash = '$platform_refresh_hash'")" = "1" ]] \
  || fail "Platform refresh token was not written to Platform"
[[ "$(psql_legacy "SELECT count(*) FROM refresh_tokens WHERE token_hash = '$platform_refresh_hash'")" = "0" ]] \
  || fail "Platform refresh token leaked to legacy"

switch_response="$(http_json POST /api/v1/auth/switch-branch "{\"branch_id\":\"$branch_id\"}" "$platform_access")"
[[ "$(printf '%s' "$switch_response" | json_get meta.identity_database)" = "platform_core" ]] \
  || fail "switch-branch did not use Platform"
switch_refresh="$(printf '%s' "$switch_response" | json_get data.refresh_token)"
switch_refresh_hash="$(token_hash "$switch_refresh")"
[[ "$(psql_platform "SELECT count(*) FROM refresh_tokens WHERE token_hash = '$switch_refresh_hash' AND revoked_at IS NULL")" = "1" ]] \
  || fail "switch-branch refresh token was not written to Platform"
[[ "$(psql_legacy "SELECT count(*) FROM refresh_tokens WHERE token_hash = '$switch_refresh_hash'")" = "0" ]] \
  || fail "switch-branch refresh token leaked to legacy"
logout_response="$(http_json POST /api/v1/auth/logout "{\"refresh_token\":\"$switch_refresh\"}")"
[[ "$(printf '%s' "$logout_response" | json_get meta.identity_database)" = "platform_core" ]] \
  || fail "logout did not use Platform"
[[ "$(psql_platform "SELECT count(*) FROM refresh_tokens WHERE token_hash = '$switch_refresh_hash' AND revoked_at IS NOT NULL")" = "1" ]] \
  || fail "logout did not revoke the Platform refresh token"

tries=0
event_id=""
until [[ -n "$event_id" ]]; do
  event_id="$(psql_platform "SELECT id FROM reference_outbox WHERE aggregate_type = 'user' AND aggregate_id = '$admin_id' AND payload->>'source' = 'auth.login' AND occurred_at >= to_timestamp($canary_started_at) AND processed_at IS NOT NULL ORDER BY occurred_at DESC LIMIT 1")"
  tries=$((tries + 1))
  [[ "$tries" -lt 30 ]] || fail "login reference event was not processed"
  [[ -n "$event_id" ]] || sleep 1
done
[[ "$(psql_restaurant "SELECT count(*) FROM platform_projection_events WHERE event_id = '$event_id'")" = "1" ]] \
  || fail "Restaurant projection ledger is missing the login event"
platform_last_login="$(psql_platform "SELECT last_login_at FROM users WHERE id = '$admin_id'")"
restaurant_last_login="$(psql_restaurant "SELECT last_login_at FROM users WHERE id = '$admin_id'")"
[[ "$platform_last_login" = "$restaurant_last_login" ]] || fail "Restaurant User projection is behind Platform"

refresh_response="$(http_json POST /api/v1/auth/refresh "{\"refresh_token\":\"$platform_refresh\"}")"
next_platform_access="$(printf '%s' "$refresh_response" | json_get data.access_token)"
next_platform_refresh="$(printf '%s' "$refresh_response" | json_get data.refresh_token)"
[[ "$(printf '%s' "$refresh_response" | json_get meta.identity_database)" = "platform_core" ]] \
  || fail "refresh did not use Platform"
next_platform_refresh_hash="$(token_hash "$next_platform_refresh")"
[[ "$(psql_platform "SELECT count(*) FROM refresh_tokens WHERE token_hash = '$next_platform_refresh_hash' AND revoked_at IS NULL")" = "1" ]] \
  || fail "rotated Platform refresh token is missing"
[[ "$(psql_legacy "SELECT count(*) FROM refresh_tokens WHERE token_hash = '$next_platform_refresh_hash'")" = "0" ]] \
  || fail "rotated Platform refresh token leaked to legacy"

printf 'Rolling identity source back to legacy...\n'
compose_backend legacy false up -d --force-recreate backend >/dev/null
wait_ready legacy false
CANARY_ACTIVE=0
[[ "$(http_status GET /api/v1/auth/me '' "$next_platform_access")" = "200" ]] \
  || fail "signed access token did not survive identity route rollback"
[[ "$(http_status POST /api/v1/auth/refresh "{\"refresh_token\":\"$next_platform_refresh\"}")" = "401" ]] \
  || fail "Platform refresh token unexpectedly worked after legacy rollback"
rollback_login="$(login "$company_id" "$branch_id" legacy)"
rollback_access="$(printf '%s' "$rollback_login" | json_get data.access_token)"
[[ "$(http_status GET /api/v1/auth/me '' "$rollback_access")" = "200" ]] \
  || fail "legacy re-login after rollback failed"

legacy_head_after="$(psql_legacy 'SELECT version_num FROM alembic_version')"
platform_head_after="$(psql_platform 'SELECT version_num FROM alembic_version')"
restaurant_head_after="$(psql_restaurant 'SELECT version_num FROM alembic_version')"
[[ "$legacy_head_after" = "$legacy_head" ]] || fail "legacy migration head changed"
[[ "$platform_head_after" = "$platform_head" ]] || fail "Platform migration head changed"
[[ "$restaurant_head_after" = "$restaurant_head" ]] || fail "Restaurant migration head changed"

cat > "$backup_dir/manifest.txt" <<EOF
scope_id=P1-RUNTIME-CUTOVER-06
rehearsal_status=verified
snapshot_timestamp_utc=$timestamp
legacy_migration_head=$legacy_head_after
platform_migration_head=$platform_head_after
restaurant_migration_head=$restaurant_head_after
final_runtime_identity_database=legacy
startup_projector_guard=true
startup_physical_boundary_guard=true
platform_refresh_isolated=true
restaurant_user_projection_parity=true
access_token_survives_rollback=true
platform_refresh_requires_relogin_after_rollback=true
canary_event_id=$event_id
contents=legacy-before.dump platform-before.dump restaurant-before.dump manifest.txt
EOF

printf 'Identity cutover rehearsal passed: %s\n' "$backup_dir"
