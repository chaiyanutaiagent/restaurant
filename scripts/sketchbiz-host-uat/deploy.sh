#!/usr/bin/env bash
# UAT-only image overlay. No migrations, seed commands, Production or DNS writes.
set -euo pipefail
artifact_dir="${1:?Pass the uploaded artifact directory}"
cd /home/behappyaiagent/restaurant-uat-releases/3760d60
old_backend=restaurant-pos-backend:uat-retail-catalog-20261014-r2
old_frontend=restaurant-pos-frontend:uat-retail-catalog-20261014-r2
new_backend=restaurant-pos-backend:uat-sketchbiz-host-20261016-r1
new_frontend=restaurant-pos-frontend:uat-sketchbiz-host-20261016-r1
test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.Config.Image}}')" = "$old_backend"
test "$(docker inspect restaurant-pos-uat-drill-frontend-1 --format '{{.Config.Image}}')" = "$old_frontend"
grep -qx "BACKEND_IMAGE=$old_backend" .env.uat
grep -qx "FRONTEND_IMAGE=$old_frontend" .env.uat
test "$(docker exec restaurant-pos-uat-drill-backend-1 sha256sum /app/app/main.py | cut -d' ' -f1)" = 2bce9f86b1225f4a4e4906e4b95120b7927da17a72d2f3b2c3d958a832e40a16
untouched() {
  docker ps -a --format '{{.Names}} {{.ID}}' | grep '^restaurant-pos-' | grep -vE '^restaurant-pos-uat-drill-(backend|frontend)-1 ' | sort
}
before="$(untouched)"
backup="$(mktemp -d /home/behappyaiagent/restaurant-uat-deploy-backups/sketchbiz-host.XXXXXX)"
cp -p .env.uat "$backup/env.uat"
chmod 600 "$backup/env.uat"
compose() {
  docker compose -p restaurant-pos-uat-drill --env-file .env.uat -f docker-compose.prod.yml -f docker-compose.uat.yml -f docker-compose.uat-superadmin.yml "$@"
}
rollback() {
  cp -p "$backup/env.uat" .env.uat
  compose up -d --no-deps --no-build backend frontend
  docker exec restaurant-pos-uat-drill-nginx-1 nginx -s reload
  echo "Rolled back UAT images; backup: $backup"
}
docker build -f "$artifact_dir/scripts/sketchbiz-host-uat/backend.Dockerfile" -t "$new_backend" "$artifact_dir"
docker build -f "$artifact_dir/scripts/sketchbiz-host-uat/frontend.Dockerfile" -t "$new_frontend" "$artifact_dir"
trap rollback ERR
sed -i "s|^BACKEND_IMAGE=$old_backend$|BACKEND_IMAGE=$new_backend|; s|^FRONTEND_IMAGE=$old_frontend$|FRONTEND_IMAGE=$new_frontend|" .env.uat
compose up -d --no-deps --no-build backend frontend
for attempt in $(seq 1 24); do
  if test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.State.Health.Status}}')" = healthy; then break; fi
  sleep 2
done
test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.State.Health.Status}}')" = healthy
docker exec restaurant-pos-uat-drill-nginx-1 nginx -s reload
check_status() {
  expected="$1"; shift
  actual="$(curl --max-time 15 -s -o /dev/null -w '%{http_code}' "$@")"
  test "$actual" = "$expected"
}
check_status 200 -H 'Host: sketchbiz.foodchainservice.com' http://127.0.0.1:18081/
check_status 200 -H 'Host: sketchbiz.foodchainservice.com' http://127.0.0.1:18081/api/v1/membership/businesses/sketch-biz
check_status 401 -H 'Host: sketchbiz.foodchainservice.com' http://127.0.0.1:18081/api/v1/auth/me
check_status 404 -X POST -H 'Host: sketchbiz.foodchainservice.com' http://127.0.0.1:18081/api/v1/auth/uat/auto-login
check_status 403 -X POST -H 'Host: sketchbiz.foodchainservice.com' -H 'Content-Type: application/json' --data '{"company_id":"other","username":"invalid","password":"invalid"}' http://127.0.0.1:18081/api/v1/auth/login
check_status 200 -H 'Host: uat-app.foodchainservice.com' http://127.0.0.1:18081/health
test "$before" = "$(untouched)"
trap - ERR
echo "UAT deployment passed 6 HTTP checks; Production/infrastructure container IDs unchanged."
echo "Rollback env: $backup/env.uat"
