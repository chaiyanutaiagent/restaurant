#!/usr/bin/env bash
set -euo pipefail
cd /home/behappyaiagent/restaurant-uat-releases/3760d60
backup=/home/behappyaiagent/restaurant-uat-deploy-backups/owner-identity-20261025.8OTe8W
artifact=/home/behappyaiagent/restaurant-uat-owner-identity-20261025
test -s "$backup/restaurant_platform_core_db.dump"
test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.Config.Image}}')" = restaurant-pos-backend:uat-password-policy-20261020-r2
cmp "$backup/superadmin-compose.yml" docker-compose.uat-superadmin.yml
test "$(docker exec restaurant-pos-uat-drill-backend-1 sha256sum /app/app/services/platform_service.py | cut -d' ' -f1)" = 7923fa858a1d2725f40059a1aa79011656c03a9f3c657670ae0fcc9670516aba
untouched() { docker ps -a --format '{{.Names}} {{.ID}}' | grep '^restaurant-pos-' | grep -vE '^restaurant-pos-uat-drill-backend-' | sort; }
before=$(untouched)
compose() { docker compose -p restaurant-pos-uat-drill --env-file .env.uat -f docker-compose.prod.yml -f docker-compose.uat.yml -f docker-compose.uat-superadmin.yml "$@"; }
rollback() {
  cp -p "$backup/superadmin-compose.yml" docker-compose.uat-superadmin.yml
  compose up -d --no-deps --no-build backend
  docker exec restaurant-pos-uat-drill-nginx-1 nginx -s reload
}
trap rollback ERR
cp "$artifact/scripts/uat-owner-identity/compose.yml" docker-compose.uat-superadmin.yml
compose up -d --no-deps --no-build backend
for attempt in $(seq 1 25); do
  if test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.State.Health.Status}}')" = healthy; then break; fi
  sleep 2
done
test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.State.Health.Status}}')" = healthy
docker exec restaurant-pos-uat-drill-nginx-1 nginx -s reload
test "$before" = "$(untouched)"
trap - ERR
echo 'UAT owner identity deployed; other services unchanged'
