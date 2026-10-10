#!/usr/bin/env bash
# Application-only rollback: intentionally retain additive preparation constraint/history.
set -euo pipefail
cd /home/behappyaiagent/restaurant-uat-releases/3760d60
old=restaurant-pos-backend:rollback-before-print-uat14
BACKEND_IMAGE="$old" docker compose -p restaurant-pos-uat-drill --env-file .env.uat -f docker-compose.prod.yml -f docker-compose.uat.yml -f docker-compose.uat-superadmin.yml up -d --no-deps --no-build backend
docker exec restaurant-pos-uat-drill-nginx-1 nginx -s reload
sed -i "s|^BACKEND_IMAGE=.*$|BACKEND_IMAGE=$old|" .env.uat
echo 'Restored previous UAT application image; additive schema and all audit history retained'
