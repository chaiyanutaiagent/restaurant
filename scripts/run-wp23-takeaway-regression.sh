#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

printf 'WP23: security and boundary checks\n'
scripts/check-takeaway-security-boundary.sh
scripts/check-takeaway-android-boundary.sh

printf 'WP23: backend regression\n'
docker compose run --rm --no-deps \
  -v "$PROJECT_DIR/backend/app:/app/app:ro" \
  -v "$PROJECT_DIR/backend/tests:/app/tests:ro" \
  backend python -B -m unittest discover -s tests -p 'test_*.py'

printf 'WP23: Takeaway migration head\n'
docker compose run --rm --no-deps \
  -v "$PROJECT_DIR/backend/app:/app/app:ro" \
  -v "$PROJECT_DIR/backend/alembic_takeaway:/app/alembic_takeaway:ro" \
  -v "$PROJECT_DIR/backend/alembic-boundaries.ini:/app/alembic-boundaries.ini:ro" \
  backend sh -lc 'export TAKEAWAY_DATABASE_URL="${TAKEAWAY_DATABASE_URL:-${DATABASE_URL%/*}/${TAKEAWAY_POSTGRES_DB:-takeaway_ops_db}}"; exec alembic -c alembic-boundaries.ini -n takeaway upgrade head'

printf 'WP23: paid-first, offline replay, QR, KDS, stock, two-brand production, ERP and rollback journey\n'
docker compose run --rm --no-deps \
  -e TAKEAWAY_FEATURE_ENABLED=true \
  -e TAKEAWAY_SERVICE_DATABASE=takeaway \
  -e REFERENCE_PROJECTOR_ENABLED=true \
  -e IDENTITY_DATABASE=platform_core \
  -v "$PROJECT_DIR/backend/app:/app/app:ro" \
  -v "$PROJECT_DIR/backend/tests:/app/tests:ro" \
  backend sh -lc 'export TAKEAWAY_DATABASE_URL="${TAKEAWAY_DATABASE_URL:-${DATABASE_URL%/*}/${TAKEAWAY_POSTGRES_DB:-takeaway_ops_db}}"; python -B -m tests.smoke_takeaway_service'

printf 'WP23: import replay and no-side-effect reconciliation\n'
docker compose run --rm --no-deps \
  -e TAKEAWAY_FEATURE_ENABLED=true \
  -e TAKEAWAY_SERVICE_DATABASE=takeaway \
  -e REFERENCE_PROJECTOR_ENABLED=true \
  -e IDENTITY_DATABASE=platform_core \
  -v "$PROJECT_DIR/backend/app:/app/app:ro" \
  -v "$PROJECT_DIR/backend/tests:/app/tests:ro" \
  backend sh -lc 'export TAKEAWAY_DATABASE_URL="${TAKEAWAY_DATABASE_URL:-${DATABASE_URL%/*}/${TAKEAWAY_POSTGRES_DB:-takeaway_ops_db}}"; python -B -m tests.smoke_takeaway_import'

printf 'WP23: frontend compile and production bundle\n'
npm --prefix frontend run type-check
npm --prefix frontend run build

printf 'PASS: WP23 automated regression gate\n'
