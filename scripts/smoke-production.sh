#!/bin/sh
set -eu

ENV_FILE="${1:-.env.production}"
BASE_URL="${PRODUCTION_SMOKE_BASE_URL:-http://localhost}"
ERRORS=0
WARNINGS=0
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/restaurant-pos-smoke.XXXXXX")"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT INT TERM

fail_check() {
  printf 'FAIL: %s\n' "$1" >&2
  ERRORS=$((ERRORS + 1))
}

warn_check() {
  printf 'SKIP: %s\n' "$1"
  WARNINGS=$((WARNINGS + 1))
}

pass_check() {
  printf 'PASS: %s\n' "$1"
}

http_status() {
  path="$1"
  curl -sS -o "$TMP_DIR/response.body" -w '%{http_code}' "${BASE_URL%/}$path" || printf '000'
}

check_get() {
  label="$1"
  path="$2"
  expected="$3"
  code="$(http_status "$path")"
  case "$code" in
    $expected)
      pass_check "$label ($path returned $code)"
      ;;
    *)
      fail_check "$label ($path returned $code, expected $expected)"
      ;;
  esac
}

json_escape() {
  python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$1"
}

extract_access_token() {
  python3 -c '
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as fh:
    payload = json.load(fh)
token = (((payload or {}).get("data") or {}).get("access_token") or "")
if token:
    print(token)
' "$1"
}

printf 'Starting production smoke test against %s\n' "$BASE_URL"
printf 'Validating production environment: %s\n' "$ENV_FILE"
scripts/check-production-env.sh "$ENV_FILE"

export PRODUCTION_ENV_FILE="$ENV_FILE"

if [ "${PRODUCTION_SMOKE_SKIP_STATUS:-0}" = "1" ]; then
  warn_check "production status check skipped by PRODUCTION_SMOKE_SKIP_STATUS=1"
else
  printf 'Running production status check.\n'
  PRODUCTION_STATUS_BASE_URL="$BASE_URL" scripts/check-production-status.sh
fi

printf '\nHTTP smoke checks:\n'
check_get "legacy health" "/health" "200"
check_get "liveness" "/health/live" "200"
check_get "readiness" "/health/ready" "200"
check_get "frontend root" "/" "200"

printf '\nOptional auth smoke check:\n'
if [ -n "${SMOKE_TEST_EMAIL:-}" ] || [ -n "${SMOKE_TEST_PASSWORD:-}" ] || [ -n "${SMOKE_TEST_COMPANY_ID:-}" ]; then
  if [ -z "${SMOKE_TEST_EMAIL:-}" ] || [ -z "${SMOKE_TEST_PASSWORD:-}" ] || [ -z "${SMOKE_TEST_COMPANY_ID:-}" ]; then
    fail_check "auth smoke requires SMOKE_TEST_EMAIL, SMOKE_TEST_PASSWORD, and SMOKE_TEST_COMPANY_ID"
  else
    login_payload="$TMP_DIR/login.json"
    login_response="$TMP_DIR/login-response.json"
    {
      printf '{"username":%s,' "$(json_escape "$SMOKE_TEST_EMAIL")"
      printf '"password":%s' "$(json_escape "$SMOKE_TEST_PASSWORD")"
      if [ -n "${SMOKE_TEST_BRANCH_ID:-}" ]; then
        printf ',"branch_id":%s' "$(json_escape "$SMOKE_TEST_BRANCH_ID")"
      fi
      printf '}'
    } > "$login_payload"

    login_code="$(curl -sS -o "$login_response" -w '%{http_code}' \
      -X POST "${BASE_URL%/}/api/v1/auth/login" \
      -H 'Content-Type: application/json' \
      -H "X-Company-ID: $SMOKE_TEST_COMPANY_ID" \
      --data-binary "@$login_payload" || printf '000')"

    if [ "$login_code" != "200" ]; then
      fail_check "auth login returned $login_code"
    else
      token="$(extract_access_token "$login_response")"
      if [ -z "$token" ]; then
        fail_check "auth login response did not include an access token"
      else
        me_code="$(curl -sS -o "$TMP_DIR/me-response.json" -w '%{http_code}' \
          "${BASE_URL%/}/api/v1/auth/me" \
          -H "Authorization: Bearer $token" \
          -H "X-Company-ID: $SMOKE_TEST_COMPANY_ID" || printf '000')"
        if [ "$me_code" = "200" ]; then
          pass_check "auth login and /api/v1/auth/me read-only check"
        else
          fail_check "authenticated /api/v1/auth/me returned $me_code"
        fi
      fi
    fi
  fi
else
  warn_check "auth smoke not configured; set SMOKE_TEST_EMAIL, SMOKE_TEST_PASSWORD, and SMOKE_TEST_COMPANY_ID to enable it"
fi

if [ "$ERRORS" -ne 0 ]; then
  printf '\nProduction smoke test failed with %s failure(s) and %s skipped check(s).\n' "$ERRORS" "$WARNINGS" >&2
  exit 1
fi

printf '\nProduction smoke test passed with %s skipped check(s).\n' "$WARNINGS"
