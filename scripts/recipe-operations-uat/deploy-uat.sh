#!/usr/bin/env bash
set -euo pipefail
release=/home/behappyaiagent/restaurant-uat-releases/recipe-operations-20261013
backup=/home/behappyaiagent/restaurant-uat-deploy-backups/recipe-operations-20261013
cd /home/behappyaiagent/restaurant-uat-releases/3760d60
compose=(docker compose -p restaurant-pos-uat-drill --env-file .env.uat -f docker-compose.prod.yml -f docker-compose.uat.yml -f docker-compose.uat-superadmin.yml)
old_backend=restaurant-pos-backend:uat-recipe-reviews-20261013
old_frontend=restaurant-pos-frontend:uat-recipe-reviews-20261013
new_backend=restaurant-pos-backend:uat-recipe-operations-20261013-r2
new_frontend=restaurant-pos-frontend:uat-recipe-operations-20261013
unchanged=(restaurant-pos-prod-backend-1 restaurant-pos-prod-frontend-1 restaurant-pos-prod-postgres-1 restaurant-pos-prod-nginx-1 restaurant-pos-prod-redis-1 restaurant-pos-uat-drill-postgres-1 restaurant-pos-uat-drill-redis-1)
test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.Config.Image}}')" = "$old_backend"
test "$(docker inspect restaurant-pos-uat-drill-frontend-1 --format '{{.Config.Image}}')" = "$old_frontend"
python3 /home/behappyaiagent/restaurant-uat-releases/document-lifecycle-20261013/verify-config.py
umask 077
cp .env.uat "$backup/.env.uat"
docker inspect "${unchanged[@]}" --format '{{.Name}} {{.Id}} {{.Image}}' > "$backup/untouched-before.txt"
docker image inspect "$old_backend" "$old_frontend" --format '{{.Id}} {{json .RepoTags}}' > "$backup/rollback-images.txt"
sha256sum -c "$backup/predeploy.sha256"
test -s "$backup/takeaway-predeploy.dump"
docker exec restaurant-pos-uat-drill-backend-1 python -c 'import asyncio; from sqlalchemy import text; from app.database import AsyncSessionLocal
async def check():
 async with AsyncSessionLocal() as db:
  assert (await db.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()==["recipeflow0032"]
asyncio.run(check())'
BACKEND_IMAGE="$new_backend" "${compose[@]}" run --rm --no-deps backend alembic upgrade recipeops0034
rollback() { trap - ERR; bash "$release/rollback-uat.sh"; exit 1; }
trap rollback ERR
BACKEND_IMAGE="$new_backend" FRONTEND_IMAGE="$new_frontend" "${compose[@]}" up -d --no-deps --no-build backend frontend
for attempt in $(seq 1 25); do
 if docker exec restaurant-pos-uat-drill-backend-1 python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=5).read()" 2>/dev/null; then break; fi
 sleep 2
done
docker exec restaurant-pos-uat-drill-backend-1 python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=5).read().decode())"
docker exec restaurant-pos-uat-drill-nginx-1 nginx -t
docker exec restaurant-pos-uat-drill-nginx-1 nginx -s reload
docker exec restaurant-pos-uat-drill-frontend-1 wget -q -O /dev/null http://127.0.0.1/
docker exec -i restaurant-pos-uat-drill-backend-1 python - < "$release/live-read-check.py" > "$backup/live-read-result.json"
docker inspect "${unchanged[@]}" --format '{{.Name}} {{.Id}} {{.Image}}' > "$backup/untouched-after.txt"
cmp "$backup/untouched-before.txt" "$backup/untouched-after.txt"
cmp .env.uat "$backup/.env.uat"
sed -i -e "s|^BACKEND_IMAGE=.*$|BACKEND_IMAGE=$new_backend|" -e "s|^FRONTEND_IMAGE=.*$|FRONTEND_IMAGE=$new_frontend|" .env.uat
trap - ERR
docker image inspect "$new_backend" "$new_frontend" --format '{{.Id}} {{json .RepoTags}}' > "$backup/deployed-images.txt"
echo 'PASS UAT only; legacy recipes registered without source/stock mutations; Production, flags and routing unchanged'
