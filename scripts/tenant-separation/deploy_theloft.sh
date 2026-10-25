#!/usr/bin/env bash
set -euo pipefail
umask 077
release=/home/behappyaiagent/restaurant-uat-releases/theloft-separation-20261025
cd /home/behappyaiagent/restaurant-uat-releases/3760d60
compose() { docker compose -p restaurant-pos-uat-drill --env-file .env.uat -f docker-compose.prod.yml -f docker-compose.uat.yml -f docker-compose.uat-superadmin.yml "$@"; }
case "${1:-}" in
  pause)
    test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.Config.Image}}')" = restaurant-pos-backend:uat-stock-target-20261025-r1
    test "$(docker inspect restaurant-pos-uat-drill-frontend-1 --format '{{.Config.Image}}')" = restaurant-pos-frontend:uat-disable-qa-20261025-r1
    test ! -e "$release/env.before-theloft"
    cp -p .env.uat "$release/env.before-theloft"
    cp -p docker-compose.uat-superadmin.yml "$release/compose-superadmin.before-theloft.yml"
    compose stop nginx backend
    ;;
  migrate)
    test "${THELOFT_MIGRATION_BACKUP_VERIFIED:-}" = YES
    test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.State.Running}}')" = false
    compose run --rm --no-deps -v "$release:/migration:ro" -e PYTHONPATH=/app -e THELOFT_MIGRATION_APPLY=YES -e THELOFT_MIGRATION_BACKUP_VERIFIED=YES -e THELOFT_MAINTENANCE_CONFIRMED=YES --entrypoint python backend /migration/migrate_theloft.py
    compose run --rm --no-deps -v "$release:/migration:ro" -e PYTHONPATH=/app --entrypoint python backend /migration/reconcile_theloft_context.py
    compose run --rm --no-deps -v "$release:/migration:ro" -e PYTHONPATH=/app --entrypoint python backend /migration/reconcile_theloft_references.py
    ;;
  deploy)
    # Set only image references; never print environment secrets.
    sed -i 's|^BACKEND_IMAGE=.*$|BACKEND_IMAGE=restaurant-pos-backend:uat-theloft-20261025-r1|;s|^FRONTEND_IMAGE=.*$|FRONTEND_IMAGE=restaurant-pos-frontend:uat-theloft-20261025-r1|' .env.uat
    sed -i 's|restaurant-pos-backend:uat-stock-target-20261025-r1|restaurant-pos-backend:uat-theloft-20261025-r1|g' docker-compose.uat-superadmin.yml
    compose up -d --no-deps --no-build backend frontend
    ;;
  open)
    test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.State.Health.Status}}')" = healthy
    compose start nginx
    docker exec restaurant-pos-uat-drill-nginx-1 nginx -t
    docker exec restaurant-pos-uat-drill-nginx-1 nginx -s reload
    ;;
  *) echo 'Expected pause, migrate, deploy, or open'; exit 2;;
esac
