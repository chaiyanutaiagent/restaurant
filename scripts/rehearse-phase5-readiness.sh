#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_ROOT="${P5_ARTIFACT_ROOT:-/private/tmp/restaurant-p5-artifacts}"
READINESS_PROJECT="${P5_READINESS_COMPOSE_PROJECT:-restaurant-p5-uat-readiness05}"
READINESS_PASSWORD="${P5_READINESS_ADMIN_PASSWORD:-}"
API_PORT="${P5_READINESS_API_PORT:-18003}"
HTTP_PORT="${P5_READINESS_HTTP_PORT:-18083}"
BACKEND_IMAGE="${P5_READINESS_BACKEND_IMAGE:-restaurant-pos-dev-backend:phase5-readiness}"
PLAYWRIGHT_BROWSERS="${P5_PLAYWRIGHT_BROWSERS_PATH:-/private/tmp/restaurant-playwright-browsers}"
ASSUME_YES=0
KEEP_RUNNING=0

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --yes) ASSUME_YES=1; shift ;;
    --keep-running) KEEP_RUNNING=1; shift ;;
    --artifact-root)
      [[ "$#" -ge 2 ]] || fail "--artifact-root requires a path"
      ARTIFACT_ROOT="$2"
      shift 2
      ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[[ "$ASSUME_YES" = "1" ]] || fail "this gate replaces only its isolated Compose volumes; pass --yes"
[[ "$READINESS_PROJECT" == restaurant-p5-uat-readiness* ]] \
  || fail "readiness Compose project must start with restaurant-p5-uat-readiness"
[[ ${#READINESS_PASSWORD} -ge 16 ]] \
  || fail "P5_READINESS_ADMIN_PASSWORD must be at least 16 characters"
[[ -d "$PLAYWRIGHT_BROWSERS" ]] \
  || fail "Playwright Chromium is missing; run PLAYWRIGHT_BROWSERS_PATH=$PLAYWRIGHT_BROWSERS npm --prefix frontend exec playwright install chromium"

cd "$PROJECT_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
artifact_dir="${ARTIFACT_ROOT%/}/p5-production-readiness-05-${timestamp}"
mkdir -p "$artifact_dir/browser"

export COMPOSE_PROJECT_NAME="$READINESS_PROJECT"
export COMPOSE_FILE="docker-compose.yml:docker-compose.uat.yml"
export P5_UAT_ADMIN_PASSWORD="$READINESS_PASSWORD"
export RESTAURANT_API_PORT="$API_PORT"
export RESTAURANT_HTTP_PORT="$HTTP_PORT"
export RESTAURANT_BACKEND_IMAGE="$BACKEND_IMAGE"

cleanup() {
  if [[ "$KEEP_RUNNING" = "0" ]]; then
    docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

printf 'Preparing isolated Phase 5 readiness stack %s...\n' "$READINESS_PROJECT"
docker compose down -v --remove-orphans >/dev/null 2>&1 || true
docker compose build backend frontend nginx
docker compose up -d postgres redis

tries=0
until docker compose exec -T postgres sh -c \
  'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1))
  [[ "$tries" -lt 45 ]] || fail "isolated readiness PostgreSQL did not become ready"
  sleep 1
done

docker compose run --rm backend alembic upgrade head
docker compose up -d backend frontend nginx
tries=0
until curl -fsS "http://127.0.0.1:${HTTP_PORT}/health/ready" \
  >"$artifact_dir/health-ready.json"; do
  tries=$((tries + 1))
  [[ "$tries" -lt 60 ]] || fail "isolated readiness application did not become ready"
  sleep 1
done

printf 'Running backend baseline and preparing browser context...\n'
docker compose exec -T backend python -m unittest discover -s tests -p 'test_*.py' \
  2>&1 | tee "$artifact_dir/backend-regression.log"
docker compose exec -T -e PYTHONPATH=/app backend python tests/smoke_phase5_full_uat_api.py \
  2>&1 | tee "$artifact_dir/full-uat-api.log"

browser_context="$(sed -n 's/^BROWSER_CONTEXT=//p' "$artifact_dir/full-uat-api.log" | tail -n 1)"
[[ -n "$browser_context" ]] || fail "full UAT did not produce browser context"
printf '%s\n' "$browser_context" >"$artifact_dir/browser-context.json"

printf 'Running mobile/tablet Playwright flow...\n'
P5_UAT_BASE_URL="http://127.0.0.1:${HTTP_PORT}" \
P5_BROWSER_CONTEXT_FILE="$artifact_dir/browser-context.json" \
P5_READINESS_ARTIFACT_DIR="$artifact_dir/browser" \
P5_UAT_ADMIN_PASSWORD="$READINESS_PASSWORD" \
PLAYWRIGHT_BROWSERS_PATH="$PLAYWRIGHT_BROWSERS" \
  npm --prefix frontend run e2e:p5 2>&1 | tee "$artifact_dir/browser-e2e.log"

printf 'Running 100-order reconnect/idempotency load gate...\n'
docker compose exec -T -e PYTHONPATH=/app backend \
  python tests/smoke_phase5_readiness_load_api.py \
  2>&1 | tee "$artifact_dir/load-reconnect-idempotency.log"

printf 'Running frontend, documentation, and repository validation...\n'
npm --prefix frontend run type-check 2>&1 | tee "$artifact_dir/frontend-typecheck.log"
npm --prefix frontend run build 2>&1 | tee "$artifact_dir/frontend-build.log"

printf 'Running release dependency audits...\n'
docker run --rm --user root --entrypoint sh "$BACKEND_IMAGE" -c \
  'python -m pip install --no-cache-dir -q pip-audit && python -m pip_audit -r requirements.txt -f json' \
  >"$artifact_dir/backend-dependency-audit.json"

frontend_prod_audit_status=0
npm --prefix frontend audit --omit=dev --json \
  >"$artifact_dir/frontend-production-dependency-audit.json" || frontend_prod_audit_status=$?
[[ "$frontend_prod_audit_status" -le 1 ]] || fail "frontend production dependency audit could not run"

node - "$artifact_dir/frontend-production-dependency-audit.json" <<'NODE'
const fs = require("fs");
const report = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const vulnerabilities = report.vulnerabilities || {};
const packages = Object.keys(vulnerabilities).sort();
const allowedPackages = new Set(["react-router", "react-router-dom"]);
if (packages.some((name) => !allowedPackages.has(name))) {
  throw new Error(`unexpected production dependency findings: ${packages.join(", ")}`);
}
const routerFindings = (vulnerabilities["react-router"]?.via || [])
  .filter((item) => typeof item === "object");
if (routerFindings.some((item) => item.url !== "https://github.com/advisories/GHSA-qwww-vcr4-c8h2")) {
  throw new Error("production React Router audit contains a finding outside the reviewed RSC-mode advisory");
}
if ((report.metadata?.vulnerabilities?.critical || 0) !== 0) {
  throw new Error("critical production dependency finding detected");
}
NODE

frontend_all_audit_status=0
npm --prefix frontend audit --json \
  >"$artifact_dir/frontend-full-dependency-audit.json" || frontend_all_audit_status=$?
[[ "$frontend_all_audit_status" -le 1 ]] || fail "frontend full dependency audit could not run"

node - "$artifact_dir/frontend-full-dependency-audit.json" <<'NODE'
const fs = require("fs");
const report = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const reviewedPackages = new Set([
  "esbuild",
  "react-router",
  "react-router-dom",
  "vite",
  "vite-plugin-pwa",
]);
const reviewedAdvisories = new Set([
  "https://github.com/advisories/GHSA-qwww-vcr4-c8h2",
  "https://github.com/advisories/GHSA-67mh-4wv8-2f99",
  "https://github.com/advisories/GHSA-4w7w-66w2-5vf9",
  "https://github.com/advisories/GHSA-v6wh-96g9-6wx3",
  "https://github.com/advisories/GHSA-fx2h-pf6j-xcff",
]);
const vulnerabilities = report.vulnerabilities || {};
const unexpectedPackages = Object.keys(vulnerabilities)
  .filter((name) => !reviewedPackages.has(name));
const unexpectedAdvisories = Object.values(vulnerabilities)
  .flatMap((finding) => finding.via || [])
  .filter((item) => typeof item === "object")
  .map((item) => item.url)
  .filter((url) => !reviewedAdvisories.has(url));
if (unexpectedPackages.length || unexpectedAdvisories.length) {
  throw new Error(
    `unexpected full dependency findings: packages=${unexpectedPackages.join(",")} advisories=${unexpectedAdvisories.join(",")}`,
  );
}
if ((report.metadata?.vulnerabilities?.critical || 0) !== 0) {
  throw new Error("critical frontend dependency finding detected");
}
NODE

scripts/validate-phase5-readiness-docs.sh 2>&1 | tee "$artifact_dir/readiness-docs.log"
scripts/pre-git-safety-check.sh 2>&1 | tee "$artifact_dir/repository-safety.log"

cat >"$artifact_dir/manifest.txt" <<EOF
scope=P5-PRODUCTION-READINESS-05
timestamp=$timestamp
compose_project=$READINESS_PROJECT
backend_image=$BACKEND_IMAGE
draft_pr=2
backend_regression=passed
full_qr_to_erp_api_uat=passed
standalone_chromium_mobile_tablet_e2e=passed
browser_console_pageerror_http5xx=passed
browser_screenshots=6
offline_load_orders=100
offline_batch_size=50
reconnect_probe=passed
lost_acknowledgement_replay=passed
sale_payment_session_outbox_journal_stock_idempotency=passed
frontend_typecheck_build=passed
backend_dependency_audit=passed_zero_known_vulnerabilities
frontend_production_dependency_audit=reviewed_rsc_mode_exception
frontend_full_dependency_audit=reviewed_dev_server_exceptions
readiness_document_package=passed
repository_safety_scan=passed
in_app_browser=unavailable_no_connected_instance
physical_device_uat=deferred_by_owner_until_hardware_arrives
security_owner_signoff=pending
operator_owner_signoff=pending
platform_owner_completion_signoff=pending
production_activated=false
phase6_started=false
EOF

printf 'Phase 5 production readiness rehearsal passed. Artifact: %s\n' "$artifact_dir/manifest.txt"
if [[ "$KEEP_RUNNING" = "1" ]]; then
  printf 'Isolated readiness stack kept at http://127.0.0.1:%s.\n' "$HTTP_PORT"
fi
