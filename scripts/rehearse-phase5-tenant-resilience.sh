#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ARTIFACT_ROOT="${P5_ARTIFACT_ROOT:-/private/tmp/restaurant-p5-artifacts}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export P5_BACKEND_IMAGE="${P5_RESILIENCE_BACKEND_IMAGE:-restaurant-pos-dev-backend:phase5-resilience-gate}"
export RESTAURANT_BACKEND_IMAGE="$P5_BACKEND_IMAGE"
ASSUME_YES=0

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --yes) ASSUME_YES=1; shift ;;
    --artifact-root)
      [[ "$#" -ge 2 ]] || fail "--artifact-root requires a path"
      ARTIFACT_ROOT="$2"
      shift 2
      ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[[ "$ASSUME_YES" = "1" ]] || fail "this gate creates and drops isolated databases; pass --yes"
[[ -f "$COMPOSE_FILE" ]] || fail "compose file not found: $COMPOSE_FILE"
cd "$PROJECT_DIR"

psql_boundary() {
  database_env="$1"
  query="$2"
  docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
    case "$1" in
      POSTGRES_DB) database_name="$POSTGRES_DB" ;;
      PLATFORM_POSTGRES_DB) database_name="$PLATFORM_POSTGRES_DB" ;;
      RESTAURANT_POSTGRES_DB) database_name="$RESTAURANT_POSTGRES_DB" ;;
      *) exit 2 ;;
    esac
    psql -U "$POSTGRES_USER" -d "$database_name" -tAc "$2"
  ' sh "$database_env" "$query" | tr -d '[:space:]'
}

source_fingerprint() {
  printf '%s:%s:%s' \
    "$(psql_boundary "$1" 'SELECT version_num FROM alembic_version')" \
    "$(psql_boundary "$1" 'SELECT count(*) FROM companies')" \
    "$(psql_boundary "$1" 'SELECT count(*) FROM users')"
}

printf 'Starting isolated Phase 5 tenant resilience gate...\n'
docker compose -f "$COMPOSE_FILE" up -d postgres redis >/dev/null
tries=0
until docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1))
  [[ "$tries" -lt 30 ]] || fail "postgres service did not become ready"
  sleep 1
done

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
artifact_dir="${ARTIFACT_ROOT%/}/p5-resilience-gate-02-${timestamp}"
mkdir -p "$artifact_dir"

legacy_before="$(source_fingerprint POSTGRES_DB)"
platform_before="$(source_fingerprint PLATFORM_POSTGRES_DB)"
restaurant_before="$(source_fingerprint RESTAURANT_POSTGRES_DB)"
latest_image_before="$(docker image inspect restaurant-pos-dev-backend:latest --format '{{.Id}}')"

printf 'Running Phase 5 migration/API/unit/frontend regression gate...\n'
scripts/rehearse-phase5-tenant-lifecycle.sh --yes --artifact-root "$artifact_dir"
printf 'Running frontend type-check and production build...\n'
npm --prefix frontend run type-check
npm --prefix frontend run build

company_id="$(psql_boundary POSTGRES_DB 'SELECT id FROM companies ORDER BY created_at, id LIMIT 1')"
[[ -n "$company_id" ]] || fail "no Company is available for tenant resilience drill"
for database_env in PLATFORM_POSTGRES_DB RESTAURANT_POSTGRES_DB; do
  [[ "$(psql_boundary "$database_env" "SELECT count(*) FROM companies WHERE id = '$company_id'")" = "1" ]] || \
    fail "Company $company_id is missing from $database_env"
done

printf 'Creating and restoring tenant boundary backup...\n'
P5_TENANT_BACKUP_ROOT="$artifact_dir" scripts/backup-tenant-boundaries.sh \
  --company-id "$company_id" \
  --reason "Phase 5 isolated tenant resilience gate"
backup_dir="$(find "$artifact_dir" -maxdepth 1 -type d -name 'p5-tenant-boundaries-*' | sort | tail -n 1)"
[[ -n "$backup_dir" ]] || fail "tenant boundary backup artifact was not created"
scripts/restore-tenant-boundaries-drill.sh --yes "$backup_dir"

printf 'Checking healthy and critical monitoring paths...\n'
RESILIENCE_ALLOW_OFFLINE_HEALTH=1 \
RESILIENCE_HEALTH_SOURCE_FILE="$PROJECT_DIR/backend/tests/fixtures/p5_resilience_health_ready_ok.json" \
RESILIENCE_BACKUP_ROOT="$artifact_dir" \
RESILIENCE_EVIDENCE_FILE="$artifact_dir/monitor-healthy.json" \
scripts/monitor-production-resilience.sh

if RESILIENCE_ALLOW_OFFLINE_HEALTH=1 \
  RESILIENCE_HEALTH_SOURCE_FILE="$PROJECT_DIR/backend/tests/fixtures/p5_resilience_health_ready_ok.json" \
  RESILIENCE_BACKUP_ROOT="$artifact_dir" \
  RESILIENCE_MAX_DISK_PERCENT=0 \
  RESILIENCE_EVIDENCE_FILE="$artifact_dir/monitor-critical.json" \
  scripts/monitor-production-resilience.sh; then
  fail "critical monitoring path unexpectedly passed"
fi
[[ "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["status"])' "$artifact_dir/monitor-critical.json")" = "critical" ]] || \
  fail "critical monitoring evidence was not recorded"

legacy_after="$(source_fingerprint POSTGRES_DB)"
platform_after="$(source_fingerprint PLATFORM_POSTGRES_DB)"
restaurant_after="$(source_fingerprint RESTAURANT_POSTGRES_DB)"
latest_image_after="$(docker image inspect restaurant-pos-dev-backend:latest --format '{{.Id}}')"
[[ "$legacy_before" = "$legacy_after" ]] || fail "live Legacy source changed"
[[ "$platform_before" = "$platform_after" ]] || fail "live Platform source changed"
[[ "$restaurant_before" = "$restaurant_after" ]] || fail "live Restaurant source changed"
[[ "$latest_image_before" = "$latest_image_after" ]] || fail "backend latest image changed"

temporary_count="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT count(*) FROM pg_database WHERE datname LIKE '\''restaurant_p5_resilience_%'\''"
' | tr -d '[:space:]')"
[[ "$temporary_count" = "0" ]] || fail "tenant resilience drill databases remain: $temporary_count"

cat > "$artifact_dir/manifest.txt" <<EOF
scope=P5-TENANT-RESILIENCE-02
timestamp=$timestamp
company_id=$company_id
legacy_source=$legacy_before
platform_source=$platform_before
restaurant_source=$restaurant_before
backend_image=$P5_BACKEND_IMAGE
latest_backend_image=$latest_image_after
tenant_export_api=passed
credential_redaction=passed
tenant_boundary_backup=passed
isolated_restore_checksum=passed
incident_recovery_evidence=passed
monitor_healthy_path=passed
monitor_critical_path=passed
unit_regression=passed
frontend_typecheck_build=passed
live_sources_unchanged=true
temporary_databases_remaining=0
production_activated=false
EOF

printf 'Phase 5 tenant resilience gate passed. Artifact: %s\n' "$artifact_dir/manifest.txt"
