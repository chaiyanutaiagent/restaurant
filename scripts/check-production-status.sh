#!/bin/sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${PRODUCTION_ENV_FILE:-.env.production}"
BASE_URL="${PRODUCTION_STATUS_BASE_URL:-http://localhost}"
ERRORS=0

fail_check() {
  printf 'ERROR: %s\n' "$1" >&2
  ERRORS=$((ERRORS + 1))
}

check_http() {
  path="$1"
  url="${BASE_URL%/}$path"
  code="$(curl -sS -o /dev/null -w '%{http_code}' "$url" || printf '000')"
  if [ "$code" = "200" ]; then
    printf '%s OK (%s)\n' "$path" "$code"
  else
    fail_check "$path failed at $url with HTTP $code"
  fi
}

container_field() {
  container_id="$1"
  template="$2"
  docker inspect --format "$template" "$container_id" 2>/dev/null || printf 'unknown'
}

printf 'Validating production environment: %s\n' "$ENV_FILE"
scripts/check-production-env.sh "$ENV_FILE"

export PRODUCTION_ENV_FILE="$ENV_FILE"

printf 'Validating production compose configuration: %s\n' "$COMPOSE_FILE"
docker compose -f "$COMPOSE_FILE" config >/dev/null

printf '\nService status:\n'
docker compose -f "$COMPOSE_FILE" ps

printf '\nContainer health and restarts:\n'
for service in postgres redis backend frontend nginx; do
  container_id="$(docker compose -f "$COMPOSE_FILE" ps -a -q "$service" 2>/dev/null || true)"
  if [ -z "$container_id" ]; then
    fail_check "$service container is not created"
    continue
  fi

  running="$(container_field "$container_id" '{{.State.Running}}')"
  health="$(container_field "$container_id" '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
  restarts="$(container_field "$container_id" '{{.RestartCount}}')"
  printf '%s running=%s health=%s restarts=%s\n' "$service" "$running" "$health" "$restarts"

  if [ "$running" != "true" ]; then
    fail_check "$service is not running"
  fi

  case "$service:$health" in
    postgres:healthy|redis:healthy|backend:healthy|frontend:none|nginx:none)
      ;;
    *)
      fail_check "$service health is $health"
      ;;
  esac
done

cloudflared_container_id="$(docker compose -f "$COMPOSE_FILE" ps -a -q cloudflared 2>/dev/null || true)"
if [ -n "$cloudflared_container_id" ]; then
  running="$(container_field "$cloudflared_container_id" '{{.State.Running}}')"
  restarts="$(container_field "$cloudflared_container_id" '{{.RestartCount}}')"
  printf 'cloudflared running=%s health=not-configured restarts=%s\n' "$running" "$restarts"
  if [ "$running" != "true" ]; then
    fail_check "cloudflared is not running"
  fi
fi

printf '\nHTTP health checks:\n'
check_http "/health/live"
check_http "/health/ready"

printf '\nDisk usage for current filesystem:\n'
df -h .
disk_percent="$(df -P . | awk 'NR==2 {gsub("%", "", $5); print $5}')"
if [ -n "$disk_percent" ] && [ "$disk_percent" -ge 80 ]; then
  printf 'WARNING: disk usage is %s%%; investigate capacity before production growth.\n' "$disk_percent" >&2
fi

printf '\nBackup freshness:\n'
if [ -d backups ]; then
  latest_backup="$(find backups -maxdepth 1 -type d -name 'restaurant-pos-prod-*' | sort | tail -n 1)"
  if [ -n "$latest_backup" ]; then
    now="$(date +%s)"
    backup_mtime="$(stat -c %Y "$latest_backup" 2>/dev/null || stat -f %m "$latest_backup")"
    age_hours="$(( (now - backup_mtime) / 3600 ))"
    printf 'latest_backup=%s age_hours=%s\n' "$latest_backup" "$age_hours"
  else
    printf 'backups/ exists, but no restaurant-pos-prod-* backup directories were found.\n'
  fi
else
  printf 'backups/ not found; no local backup freshness data available.\n'
fi

if [ "$ERRORS" -ne 0 ]; then
  printf '\nProduction status check failed with %s error(s).\n' "$ERRORS" >&2
  exit 1
fi

printf '\nProduction status check passed.\n'
