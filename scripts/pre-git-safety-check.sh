#!/bin/sh
set -eu

ERRORS=0
WARNINGS=0

fail_check() {
  printf 'FAIL: %s\n' "$1" >&2
  ERRORS=$((ERRORS + 1))
}

warn_check() {
  printf 'WARN: %s\n' "$1" >&2
  WARNINGS=$((WARNINGS + 1))
}

pass_check() {
  printf 'PASS: %s\n' "$1"
}

check_absent_path() {
  path="$1"
  label="$2"
  if [ -e "$path" ]; then
    fail_check "$label present: $path"
  else
    pass_check "$label absent"
  fi
}

check_required_file() {
  path="$1"
  if [ -f "$path" ]; then
    pass_check "required file exists: $path"
  else
    fail_check "required file missing: $path"
  fi
}

check_required_doc() {
  path="$1"
  check_required_file "$path"
}

check_find_empty() {
  description="$1"
  shift
  results="$("$@" 2>/dev/null || true)"
  if [ -n "$results" ]; then
    fail_check "$description found"
    printf '%s\n' "$results" >&2
  else
    pass_check "$description absent"
  fi
}

printf '%s\n' 'Running pre-Git safety checks.'
printf '%s\n' 'This script checks file names and paths only; it does not print env contents.'

if [ -e .env ]; then
  warn_check ".env exists locally; keep it ignored and do not stage it"
else
  pass_check ".env absent"
fi

check_absent_path ".env.production" "production env file"
check_absent_path "nginx/conf.d/default.prod.https.conf" "generated HTTPS nginx config"
check_absent_path "backups" "backup directory"
check_absent_path "restore-tmp" "restore temp directory"
check_absent_path "uploads" "local uploads directory"
check_absent_path "backend/uploads" "backend local uploads directory"
check_absent_path "logs" "local logs directory"

check_find_empty "certificate/private key files" \
  find . -path './.git' -prune -o -type f \( -name '*.pem' -o -name '*.key' -o -name '*.crt' \) -print

check_find_empty "backup/dump/sql artifacts" \
  find . -path './.git' -prune -o -type f \( -name '*.dump' -o -name '*.sql' -o -name '*.backup.tar.gz' -o -name '*.bak' \) -print

if [ -d releases ]; then
  check_find_empty "generated release manifests" \
    find releases -mindepth 2 -type f -name 'release-manifest.txt' -print
else
  pass_check "releases directory absent"
fi

check_find_empty "local log files" \
  find . -path './.git' -prune -o -type f -name '*.log' -print

check_required_file ".env.example"
check_required_file ".env.production.example"

check_required_doc "docs/production/git-ci.md"
check_required_doc "docs/production/first-git-commit.md"
check_required_doc "docs/production/README.md"
check_required_doc "docs/production/production-readiness-checklist.md"
check_required_doc "docs/production/go-live-checklist.md"
check_required_doc "docs/production/operator-handoff.md"
check_required_doc "docs/production/incident-quick-guide.md"
check_required_doc "docs/production/sign-off.md"

printf '%s\n' 'Checking shell syntax for scripts/*.sh.'
for script in scripts/*.sh; do
  sh -n "$script"
done
pass_check "shell syntax passed"

if [ "$ERRORS" -ne 0 ]; then
  printf '\nPre-Git safety check failed with %s error(s) and %s warning(s).\n' "$ERRORS" "$WARNINGS" >&2
  exit 1
fi

printf '\nPre-Git safety check passed with %s warning(s).\n' "$WARNINGS"
