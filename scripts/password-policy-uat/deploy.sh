#!/usr/bin/env bash
# UAT only: no database writes, credentials, flags or Production changes.
set -euo pipefail
artifact_dir="${1:?Pass uploaded artifact directory}"
cd /home/behappyaiagent/restaurant-uat-releases/3760d60
old_backend=restaurant-pos-backend:uat-sketchbiz-host-20261016-r1
old_frontend=restaurant-pos-frontend:uat-sketchbiz-host-20261016-r1
new_backend=restaurant-pos-backend:uat-password-policy-20261020-r2
new_frontend=restaurant-pos-frontend:uat-password-policy-20261020-r1
test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.Config.Image}}')" = "$old_backend"
test "$(docker inspect restaurant-pos-uat-drill-frontend-1 --format '{{.Config.Image}}')" = "$old_frontend"
grep -qx "BACKEND_IMAGE=$old_backend" .env.uat
grep -qx "FRONTEND_IMAGE=$old_frontend" .env.uat
test "$(docker exec restaurant-pos-uat-drill-backend-1 sha256sum /app/app/schemas/membership.py | cut -d' ' -f1)" = 2f1be4a9c76d01a2d12809b2f228adc70a3e7723893f71c76d570fd539778b8e
test "$(docker exec restaurant-pos-uat-drill-backend-1 sha256sum /app/app/schemas/platform.py | cut -d' ' -f1)" = 6c8df0d8dc2b74bbc04324d17e5b745f012bdc62a071c5ae49e66f5e0089307b
untouched() {
  docker ps -a --format '{{.Names}} {{.ID}}' | grep '^restaurant-pos-' | grep -vE '^restaurant-pos-uat-drill-(backend|frontend)-1 ' | sort
}
before="$(untouched)"
backup="$(mktemp -d /home/behappyaiagent/restaurant-uat-deploy-backups/password-policy.XXXXXX)"
cp -p .env.uat "$backup/env.uat"
chmod 600 "$backup/env.uat"
compose() {
  docker compose -p restaurant-pos-uat-drill --env-file .env.uat -f docker-compose.prod.yml -f docker-compose.uat.yml -f docker-compose.uat-superadmin.yml "$@"
}
rollback() {
  cp -p "$backup/env.uat" .env.uat
  compose up -d --no-deps --no-build backend frontend
  docker exec restaurant-pos-uat-drill-nginx-1 nginx -s reload
  echo "Rolled back UAT; backup: $backup"
}
docker build -f "$artifact_dir/scripts/password-policy-uat/backend.Dockerfile" -t "$new_backend" "$artifact_dir"
docker build -f "$artifact_dir/scripts/password-policy-uat/frontend.Dockerfile" -t "$new_frontend" "$artifact_dir"
# Check schema compatibility without starting a service or accessing a database.
docker run --rm --network none --entrypoint python "$new_backend" -c 'from app.schemas.platform import PlatformCustomRoleCreate, PlatformCompanyOwnerCreate; from app.schemas.membership import SaasPasswordResetConfirm; assert PlatformCompanyOwnerCreate.model_json_schema()["properties"]["password"]["minLength"] == 8; assert SaasPasswordResetConfirm.model_json_schema()["properties"]["new_password"]["minLength"] == 8'
trap rollback ERR
sed -i "s|^BACKEND_IMAGE=$old_backend$|BACKEND_IMAGE=$new_backend|; s|^FRONTEND_IMAGE=$old_frontend$|FRONTEND_IMAGE=$new_frontend|" .env.uat
compose up -d --no-deps --no-build backend frontend
for attempt in $(seq 1 90); do
  if test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.State.Health.Status}}')" = healthy; then break; fi
  sleep 2
done
test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.State.Health.Status}}')" = healthy
docker cp "$artifact_dir/backend/tests/test_customer_password_length.py" restaurant-pos-uat-drill-backend-1:/tmp/test_customer_password_length.py
docker cp "$artifact_dir/backend/tests/test_saas_membership.py" restaurant-pos-uat-drill-backend-1:/tmp/test_saas_membership.py
docker exec -e PYTHONPATH=/app restaurant-pos-uat-drill-backend-1 python -m unittest discover -s /tmp -p test_customer_password_length.py
docker exec -e PYTHONPATH=/app restaurant-pos-uat-drill-backend-1 python -m unittest discover -s /tmp -p test_saas_membership.py
docker exec restaurant-pos-uat-drill-nginx-1 nginx -s reload
test "$(curl --max-time 15 -s -o /dev/null -w '%{http_code}' -H 'Host: sketchbiz.foodchainservice.com' http://127.0.0.1:18081/)" = 200
test "$(curl --max-time 15 -s -o /dev/null -w '%{http_code}' -H 'Host: sketchbiz.foodchainservice.com' http://127.0.0.1:18081/api/v1/auth/me)" = 401
test "$before" = "$(untouched)"
trap - ERR
echo "UAT password policy deployed; other containers unchanged."
echo "Rollback env: $backup/env.uat"
