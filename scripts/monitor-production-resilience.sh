#!/bin/sh
set -eu

BASE_URL="${RESILIENCE_BASE_URL:-http://localhost}"
BACKUP_ROOT="${RESILIENCE_BACKUP_ROOT:-backups}"
MAX_BACKUP_AGE_HOURS="${RESILIENCE_MAX_BACKUP_AGE_HOURS:-26}"
MAX_DISK_PERCENT="${RESILIENCE_MAX_DISK_PERCENT:-80}"
MAX_PROJECTOR_FAILED="${RESILIENCE_MAX_PROJECTOR_FAILED_EVENTS:-0}"
MAX_PROJECTOR_LOOP_ERRORS="${RESILIENCE_MAX_PROJECTOR_LOOP_ERRORS:-0}"
MAX_RESTORE_AGE_DAYS="${RESILIENCE_MAX_RESTORE_AGE_DAYS:-31}"
ALERT_WEBHOOK_URL="${RESILIENCE_ALERT_WEBHOOK_URL:-}"
REQUIRE_ALERT_WEBHOOK="${RESILIENCE_REQUIRE_ALERT_WEBHOOK:-0}"
EVIDENCE_FILE="${RESILIENCE_EVIDENCE_FILE:-}"
HEALTH_SOURCE_FILE="${RESILIENCE_HEALTH_SOURCE_FILE:-}"
ALLOW_OFFLINE_HEALTH="${RESILIENCE_ALLOW_OFFLINE_HEALTH:-0}"
RESTORE_EVIDENCE_FILE="${RESILIENCE_RESTORE_EVIDENCE_FILE:-}"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/restaurant-resilience.XXXXXX")"
ALERTS_FILE="$TMP_DIR/alerts.txt"
HEALTH_FILE="$TMP_DIR/health.json"
STATUS="ok"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT HUP INT TERM

fail_check() {
  STATUS="critical"
  printf '%s\n' "$1" >> "$ALERTS_FILE"
  printf 'CRITICAL: %s\n' "$1" >&2
}

validate_integer() {
  case "$2" in
    ''|*[!0-9]*) fail_check "$1 must be a non-negative integer" ;;
  esac
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

manifest_value() {
  key="$1"
  sed -n "s/^${key}=//p" "$latest_backup/manifest.txt" | head -n 1
}

validate_integer RESILIENCE_MAX_BACKUP_AGE_HOURS "$MAX_BACKUP_AGE_HOURS"
validate_integer RESILIENCE_MAX_DISK_PERCENT "$MAX_DISK_PERCENT"
validate_integer RESILIENCE_MAX_PROJECTOR_FAILED_EVENTS "$MAX_PROJECTOR_FAILED"
validate_integer RESILIENCE_MAX_PROJECTOR_LOOP_ERRORS "$MAX_PROJECTOR_LOOP_ERRORS"
validate_integer RESILIENCE_MAX_RESTORE_AGE_DAYS "$MAX_RESTORE_AGE_DAYS"

if [ -n "$HEALTH_SOURCE_FILE" ]; then
  [ "$ALLOW_OFFLINE_HEALTH" = "1" ] || fail_check "offline health evidence requires RESILIENCE_ALLOW_OFFLINE_HEALTH=1"
  if [ -f "$HEALTH_SOURCE_FILE" ]; then
    cp "$HEALTH_SOURCE_FILE" "$HEALTH_FILE"
    health_code=200
  else
    health_code=000
    fail_check "offline health evidence file is missing: $HEALTH_SOURCE_FILE"
  fi
else
  health_code="$(curl -sS -o "$HEALTH_FILE" -w '%{http_code}' "${BASE_URL%/}/health/ready" || printf '000')"
fi

restore_status="unknown"
restore_drill_at=""
if [ -n "$RESTORE_EVIDENCE_FILE" ]; then
  if [ ! -f "$RESTORE_EVIDENCE_FILE" ]; then
    restore_status="failed"
    fail_check "restore evidence file is missing"
  elif [ "$(sed -n 's/^status=//p' "$RESTORE_EVIDENCE_FILE" | head -n 1)" != "passed" ]; then
    restore_status="failed"
    fail_check "restore drill failed"
  else
    restore_epoch="$(stat -c %Y "$RESTORE_EVIDENCE_FILE" 2>/dev/null || stat -f %m "$RESTORE_EVIDENCE_FILE")"
    restore_age_days=$(( ($(date +%s) - restore_epoch) / 86400 ))
    restore_drill_at="$(python3 -c 'from datetime import datetime, timezone; import sys; print(datetime.fromtimestamp(int(sys.argv[1]), timezone.utc).isoformat())' "$restore_epoch")"
    if [ "$restore_age_days" -gt "$MAX_RESTORE_AGE_DAYS" ]; then
      restore_status="stale"
      fail_check "restore drill is ${restore_age_days}d old; maximum is ${MAX_RESTORE_AGE_DAYS}d"
    else
      restore_status="passed"
    fi
  fi
fi
projector_failed=0
projector_loop_errors=0
if [ "$health_code" != "200" ]; then
  fail_check "readiness endpoint returned HTTP $health_code"
elif ! python3 -c 'import json, sys; payload=json.load(open(sys.argv[1], encoding="utf-8")); assert payload.get("status") == "ok"' "$HEALTH_FILE" 2>/dev/null; then
  fail_check "readiness payload is invalid or not healthy"
else
  projector_failed="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("runtime", {}).get("reference_projector_failed_events", 0))' "$HEALTH_FILE")"
  projector_loop_errors="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("runtime", {}).get("reference_projector_loop_errors", 0))' "$HEALTH_FILE")"
  validate_integer reference_projector_failed_events "$projector_failed"
  validate_integer reference_projector_loop_errors "$projector_loop_errors"
  if [ "$projector_failed" -gt "$MAX_PROJECTOR_FAILED" ]; then
    fail_check "reference projector failed events $projector_failed exceed $MAX_PROJECTOR_FAILED"
  fi
  if [ "$projector_loop_errors" -gt "$MAX_PROJECTOR_LOOP_ERRORS" ]; then
    fail_check "reference projector loop errors $projector_loop_errors exceed $MAX_PROJECTOR_LOOP_ERRORS"
  fi
fi

disk_percent="$(df -P . | awk 'NR==2 {gsub("%", "", $5); print $5}')"
validate_integer disk_usage_percent "$disk_percent"
if [ "$disk_percent" -ge "$MAX_DISK_PERCENT" ]; then
  fail_check "disk usage $disk_percent% reached threshold $MAX_DISK_PERCENT%"
fi

latest_backup=""
backup_age_hours=-1
if [ -d "$BACKUP_ROOT" ]; then
  latest_backup="$(find "$BACKUP_ROOT" -maxdepth 1 -type d -name 'p5-tenant-boundaries-*' | sort | tail -n 1)"
fi
if [ -z "$latest_backup" ]; then
  fail_check "no Phase 5 tenant boundary backup found under $BACKUP_ROOT"
else
  for required_file in manifest.txt legacy.dump platform-core.dump restaurant.dump tenant-export.json; do
    [ -f "$latest_backup/$required_file" ] || fail_check "latest tenant backup is missing $required_file"
  done
  if [ -f "$latest_backup/manifest.txt" ]; then
    backup_mtime="$(stat -c %Y "$latest_backup/manifest.txt" 2>/dev/null || stat -f %m "$latest_backup/manifest.txt")"
    now_epoch="$(date +%s)"
    backup_age_hours=$(( (now_epoch - backup_mtime) / 3600 ))
    if [ "$backup_age_hours" -gt "$MAX_BACKUP_AGE_HOURS" ]; then
      fail_check "latest tenant backup is ${backup_age_hours}h old; maximum is ${MAX_BACKUP_AGE_HOURS}h"
    fi
    for checksum_pair in \
      "legacy.dump:legacy_sha256" \
      "platform-core.dump:platform_sha256" \
      "restaurant.dump:restaurant_sha256" \
      "tenant-export.json:tenant_export_sha256"; do
      artifact_name="${checksum_pair%%:*}"
      checksum_key="${checksum_pair#*:}"
      expected_checksum="$(manifest_value "$checksum_key")"
      if [ -f "$latest_backup/$artifact_name" ] && [ -n "$expected_checksum" ] && \
        [ "$(sha256_file "$latest_backup/$artifact_name")" != "$expected_checksum" ]; then
        fail_check "latest tenant backup checksum failed for $artifact_name"
      fi
    done
  fi
fi

if [ "$REQUIRE_ALERT_WEBHOOK" = "1" ] && [ -z "$ALERT_WEBHOOK_URL" ]; then
  fail_check "alert webhook delivery is required but RESILIENCE_ALERT_WEBHOOK_URL is empty"
fi

[ -f "$ALERTS_FILE" ] || : > "$ALERTS_FILE"
timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [ -z "$EVIDENCE_FILE" ]; then
  EVIDENCE_FILE="$TMP_DIR/evidence.json"
else
  evidence_parent="$(dirname "$EVIDENCE_FILE")"
  mkdir -p "$evidence_parent"
fi

python3 -c '
import json, sys
alerts = [line.rstrip("\n") for line in open(sys.argv[12], encoding="utf-8") if line.strip()]
mapping = (
    ("readiness", "readiness_unhealthy"),
    ("failed events", "projector_failed"),
    ("loop errors", "projector_loop_errors"),
    ("disk usage", "disk_threshold"),
    ("no Phase 5", "backup_missing"),
    ("backup is missing", "backup_incomplete"),
    ("old; maximum", "backup_stale"),
    ("checksum failed", "backup_checksum_failed"),
    ("restore evidence", "restore_missing"),
    ("restore drill is", "restore_stale"),
    ("restore drill failed", "restore_failed"),
    ("webhook delivery is required", "alert_not_configured"),
    ("webhook delivery failed", "alert_delivery_failed"),
)
alert_codes = sorted({code for alert in alerts for marker, code in mapping if marker.lower() in alert.lower()})
payload = {
    "scope": "P5-TENANT-RESILIENCE-02",
    "timestamp": sys.argv[1],
    "status": sys.argv[2],
    "health_http_code": sys.argv[3],
    "reference_projector_failed_events": int(sys.argv[4]),
    "reference_projector_loop_errors": int(sys.argv[5]),
    "disk_usage_percent": int(sys.argv[6]),
    "latest_backup": sys.argv[7] or None,
    "backup_age_hours": int(sys.argv[8]),
    "alert_delivery_configured": sys.argv[9] == "true",
    "restore_status": sys.argv[10],
    "restore_drill_at": sys.argv[11] or None,
    "alert_codes": alert_codes,
    "alerts": alerts,
}
with open(sys.argv[13], "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
    handle.write("\n")
' "$timestamp" "$STATUS" "$health_code" "$projector_failed" "$projector_loop_errors" "$disk_percent" "$latest_backup" "$backup_age_hours" "$([ -n "$ALERT_WEBHOOK_URL" ] && printf true || printf false)" "$restore_status" "$restore_drill_at" "$ALERTS_FILE" "$EVIDENCE_FILE"

if [ "$STATUS" = "critical" ] && [ -n "$ALERT_WEBHOOK_URL" ]; then
  if ! curl -fsS -X POST -H 'Content-Type: application/json' --data-binary "@$EVIDENCE_FILE" "$ALERT_WEBHOOK_URL" >/dev/null; then
    printf 'CRITICAL: resilience alert webhook delivery failed\n' >&2
    exit 2
  fi
  printf 'Alert delivered to configured resilience webhook.\n'
fi

if [ "${RESILIENCE_EVIDENCE_FILE:-}" = "" ]; then
  cat "$EVIDENCE_FILE"
else
  chmod 600 "$EVIDENCE_FILE"
  printf 'Resilience evidence: %s\n' "$EVIDENCE_FILE"
fi

[ "$STATUS" = "ok" ] || exit 1
