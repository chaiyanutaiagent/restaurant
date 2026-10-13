#!/usr/bin/env bash
set -euo pipefail
cd /home/behappyaiagent/restaurant-uat-releases/3760d60
backup=/home/behappyaiagent/restaurant-uat-deploy-backups/recipe-operations-20261013
old=restaurant-pos-backend:uat-recipe-operations-20261013-r1
new=restaurant-pos-backend:uat-recipe-operations-20261013-r2
test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.Config.Image}}')" = "$old"
compose=(docker compose -p restaurant-pos-uat-drill --env-file .env.uat -f docker-compose.prod.yml -f docker-compose.uat.yml -f docker-compose.uat-superadmin.yml)
rollback() {
 trap - ERR
 BACKEND_IMAGE="$old" "${compose[@]}" up -d --no-deps --no-build backend
 docker exec restaurant-pos-uat-drill-nginx-1 nginx -s reload
 exit 1
}
trap rollback ERR
BACKEND_IMAGE="$new" "${compose[@]}" up -d --no-deps --no-build backend
for attempt in $(seq 1 25); do
 if docker exec restaurant-pos-uat-drill-backend-1 python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=5).read()" 2>/dev/null; then break; fi
 sleep 2
done
docker exec restaurant-pos-uat-drill-backend-1 python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=5).read().decode())"
docker exec restaurant-pos-uat-drill-nginx-1 nginx -s reload
sed -i "s|^BACKEND_IMAGE=.*$|BACKEND_IMAGE=$new|" .env.uat
docker image inspect "$new" restaurant-pos-frontend:uat-recipe-operations-20261013 --format '{{.Id}} {{json .RepoTags}}' > "$backup/deployed-images.txt"
trap - ERR
echo 'PASS final UAT recipe operations revision; Production unchanged'
