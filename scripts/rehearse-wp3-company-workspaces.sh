#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
export RESTAURANT_BACKEND_IMAGE="${WP3_WORKSPACE_BACKEND_IMAGE:-restaurant-pos-dev-backend:wp3-workspace-gate}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATABASE_PREFIX="restaurant_wp3_workspace_"
WORKSPACE_DATABASE=""
TEMP_DIR=""

fail() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

cleanup() {
  if [[ -n "$WORKSPACE_DATABASE" ]]; then
    case "$WORKSPACE_DATABASE" in
      ${DATABASE_PREFIX}[0-9]*)
        docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
          psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
            -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '\''$1'\'' AND pid <> pg_backend_pid()" >/dev/null
          dropdb --if-exists -U "$POSTGRES_USER" "$1"
        ' sh "$WORKSPACE_DATABASE" >/dev/null 2>&1 || true
        ;;
    esac
  fi
  if [[ -n "$TEMP_DIR" ]]; then
    case "$TEMP_DIR" in
      /private/tmp/restaurant-wp3-workspace.*|/tmp/restaurant-wp3-workspace.*) rm -rf "$TEMP_DIR" ;;
    esac
  fi
}
trap cleanup EXIT HUP INT TERM

cd "$PROJECT_DIR"
[[ "${1:-}" = "--yes" ]] || fail "this rehearsal creates and drops one isolated temporary database; pass --yes"

docker compose -f "$COMPOSE_FILE" up -d postgres redis >/dev/null
tries=0
until docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1))
  [[ "$tries" -lt 30 ]] || fail "postgres service did not become ready"
  sleep 1
done

timestamp="$(date -u +%Y%m%d%H%M%S)"
WORKSPACE_DATABASE="${DATABASE_PREFIX}${timestamp}$$"
TEMP_DIR="$(mktemp -d /private/tmp/restaurant-wp3-workspace.XXXXXX 2>/dev/null || mktemp -d /tmp/restaurant-wp3-workspace.XXXXXX)"

before_fingerprint="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT count(*) FROM companies), chr(58), (SELECT count(*) FROM brands), chr(58), (SELECT count(*) FROM branches), chr(58), (SELECT count(*) FROM audit_logs))"
' | tr -d '[:space:]')"

printf 'Cloning the local source into an isolated WP3 database...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$TEMP_DIR/source.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$WORKSPACE_DATABASE"
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$WORKSPACE_DATABASE" < "$TEMP_DIR/source.dump"

printf 'Building and running the WP3 workspace API gate...\n'
docker compose -f "$COMPOSE_FILE" build backend >/dev/null
docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
  -e WP3_WORKSPACE_DATABASE_NAME="$WORKSPACE_DATABASE" \
  -e IDENTITY_DATABASE=legacy \
  -e RESTAURANT_SERVICE_DATABASE=legacy \
  -e REFERENCE_PROJECTOR_ENABLED=false \
  -e TAKEAWAY_FEATURE_ENABLED=false \
  -v "$PWD/backend/tests:/app/tests:ro" \
  backend sh -c '
    set -eu
    case "$WP3_WORKSPACE_DATABASE_NAME" in restaurant_wp3_workspace_[0-9]*) ;; *) exit 2 ;; esac
    database_server="${DATABASE_URL%/*}"
    export DATABASE_URL="$database_server/$WP3_WORKSPACE_DATABASE_NAME"
    export PLATFORM_DATABASE_URL="$DATABASE_URL"
    export RESTAURANT_DATABASE_URL="$DATABASE_URL"
    alembic upgrade head
    python -m tests.smoke_company_workspace_api
  '

after_fingerprint="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT concat((SELECT version_num FROM alembic_version), chr(58), (SELECT count(*) FROM companies), chr(58), (SELECT count(*) FROM brands), chr(58), (SELECT count(*) FROM branches), chr(58), (SELECT count(*) FROM audit_logs))"
' | tr -d '[:space:]')"
[[ "$before_fingerprint" = "$after_fingerprint" ]] || fail "live local source changed: $before_fingerprint -> $after_fingerprint"

printf 'WP3 Company workspace gate passed; live source remained unchanged.\n'
