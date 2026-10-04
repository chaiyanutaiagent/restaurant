#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_ROOT="${P5_ARTIFACT_ROOT:-/private/tmp/restaurant-p5-artifacts}"
UAT_PROJECT="${P5_UAT_COMPOSE_PROJECT:-restaurant-p5-uat03}"
UAT_PASSWORD="${P5_UAT_ADMIN_PASSWORD:-}"
UAT_API_PORT="${P5_UAT_API_PORT:-18001}"
UAT_HTTP_PORT="${P5_UAT_HTTP_PORT:-18081}"
UAT_BACKEND_IMAGE="${P5_UAT_BACKEND_IMAGE:-restaurant-pos-dev-backend:phase5-uat-security}"
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
[[ "$UAT_PROJECT" == restaurant-p5-uat* ]] || fail "UAT Compose project must start with restaurant-p5-uat"
[[ ${#UAT_PASSWORD} -ge 16 ]] || fail "P5_UAT_ADMIN_PASSWORD must be at least 16 characters"

cd "$PROJECT_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
artifact_dir="${ARTIFACT_ROOT%/}/p5-uat-security-03-${timestamp}"
mkdir -p "$artifact_dir"

export COMPOSE_PROJECT_NAME="$UAT_PROJECT"
export COMPOSE_FILE="docker-compose.yml:docker-compose.uat.yml"
export P5_UAT_ADMIN_PASSWORD="$UAT_PASSWORD"
export RESTAURANT_API_PORT="$UAT_API_PORT"
export RESTAURANT_HTTP_PORT="$UAT_HTTP_PORT"
export RESTAURANT_BACKEND_IMAGE="$UAT_BACKEND_IMAGE"

cleanup() {
  if [[ "$KEEP_RUNNING" = "0" ]]; then
    docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

printf 'Preparing isolated Phase 5 UAT stack %s...\n' "$UAT_PROJECT"
docker compose down -v --remove-orphans >/dev/null 2>&1 || true
docker compose build backend frontend nginx
docker compose up -d postgres redis

tries=0
until docker compose exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1))
  [[ "$tries" -lt 45 ]] || fail "isolated UAT PostgreSQL did not become ready"
  sleep 1
done

docker compose run --rm backend alembic upgrade head
docker compose up -d backend frontend nginx
tries=0
until curl -fsS "http://127.0.0.1:${UAT_HTTP_PORT}/health/ready" >"$artifact_dir/health-ready.json"; do
  tries=$((tries + 1))
  [[ "$tries" -lt 60 ]] || fail "isolated UAT application did not become ready"
  sleep 1
done

printf 'Running backend regression and full restaurant UAT...\n'
docker compose exec -T backend python -m unittest discover -s tests -p 'test_*.py' \
  2>&1 | tee "$artifact_dir/backend-regression.log"
docker compose exec -T -e PYTHONPATH=/app backend python tests/smoke_phase5_full_uat_api.py \
  2>&1 | tee "$artifact_dir/full-uat-api.log"
FNB_SMOKE_DATABASE=legacy INTERNAL_BASE_URL=http://127.0.0.1:8000 \
  scripts/fnb-smoke.sh 2>&1 | tee "$artifact_dir/fnb-smoke.log"
FNB_PERMISSION_SMOKE_DATABASE=legacy INTERNAL_BASE_URL=http://127.0.0.1:8000 \
  scripts/fnb-permission-smoke.sh 2>&1 | tee "$artifact_dir/fnb-permission-smoke.log"

printf 'Running frontend and production security regression...\n'
npm --prefix frontend run type-check 2>&1 | tee "$artifact_dir/frontend-typecheck.log"
npm --prefix frontend run build 2>&1 | tee "$artifact_dir/frontend-build.log"

printf 'Running dependency audits...\n'
docker run --rm --user root --entrypoint sh "$UAT_BACKEND_IMAGE" -c \
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

docker compose exec -T -e ENVIRONMENT=production -e ENABLE_API_DOCS=false backend \
  python -c 'from app.main import app; assert app.docs_url is None; assert app.redoc_url is None; assert app.openapi_url is None' \
  2>&1 | tee "$artifact_dir/api-docs-production.log"

docker build \
  --build-arg NGINX_PROD_CONF=default.prod.conf \
  -f nginx/Dockerfile.prod \
  -t restaurant-pos-nginx:phase5-uat-security \
  nginx 2>&1 | tee "$artifact_dir/nginx-production-build.log"
docker run --rm restaurant-pos-nginx:phase5-uat-security nginx -t \
  2>&1 | tee "$artifact_dir/nginx-production-config.log"

if ! rg -q "Content-Security-Policy" nginx/conf.d/default.prod.conf \
  nginx/conf.d/default.prod.cloudflare.conf nginx/conf.d/default.prod.https.template.conf; then
  fail "production nginx variants are missing Content-Security-Policy"
fi
scripts/pre-git-safety-check.sh 2>&1 | tee "$artifact_dir/repository-safety.log"

browser_context="$(sed -n 's/^BROWSER_CONTEXT=//p' "$artifact_dir/full-uat-api.log" | tail -n 1)"
[[ -n "$browser_context" ]] || fail "full UAT did not produce browser context"
printf '%s\n' "$browser_context" >"$artifact_dir/browser-context.json"

cat >"$artifact_dir/manifest.txt" <<EOF
scope=P5-UAT-SECURITY-03
timestamp=$timestamp
compose_project=$UAT_PROJECT
backend_image=$UAT_BACKEND_IMAGE
full_qr_to_erp_api_uat=passed
recipe_store_stock_handoff=passed
accounting_handoff=passed
erp_sales_reconciliation=passed
erp_payment_reconciliation=passed
fnb_dinein_takeaway_regression=passed
role_permission_regression=passed
backend_regression=passed
frontend_typecheck_build=passed
production_api_docs_disabled=passed
production_nginx_config=passed
content_security_policy=passed
repository_safety_scan=passed
browser_visual_uat=pending
backend_dependency_audit=passed
frontend_production_dependency_audit=reviewed_rsc_mode_exception
frontend_full_dependency_audit=reviewed_dev_server_exceptions
dependency_risk_owner_signoff=pending
owner_signoff=pending
production_activated=false
EOF

printf 'Automated Phase 5 UAT/security gate passed. Artifact: %s\n' "$artifact_dir/manifest.txt"
if [[ "$KEEP_RUNNING" = "1" ]]; then
  printf 'Isolated UAT stack kept at http://127.0.0.1:%s for browser verification.\n' "$UAT_HTTP_PORT"
fi
