#!/usr/bin/env bash
set -euo pipefail
cd /home/behappyaiagent/restaurant-uat-releases/3760d60
# Never roll back guards once governed recipes or stock postings are in use.
docker exec restaurant-pos-uat-drill-backend-1 python -c 'import asyncio; from sqlalchemy import text; from app.database import AsyncSessionLocal
async def check():
 async with AsyncSessionLocal() as db:
  assert await db.scalar(text("SELECT count(*) FROM recipe_reviews WHERE status IN ('\''approved_hold'\'', '\''published'\'')")) == 0, "Approved/published recipes exist: verify cross-DB publication and forward-fix"
  assert await db.scalar(text("SELECT count(*) FROM recipe_production_runs")) == 0, "Production evidence exists: recover pending outputs before any rollback"
asyncio.run(check())'
compose=(docker compose -p restaurant-pos-uat-drill --env-file .env.uat -f docker-compose.prod.yml -f docker-compose.uat.yml -f docker-compose.uat-superadmin.yml)
BACKEND_IMAGE=restaurant-pos-backend:uat-recipe-reviews-20261013 FRONTEND_IMAGE=restaurant-pos-frontend:uat-recipe-reviews-20261013 "${compose[@]}" up -d --no-deps --no-build backend frontend
docker exec restaurant-pos-uat-drill-nginx-1 nginx -t
docker exec restaurant-pos-uat-drill-nginx-1 nginx -s reload
sed -i -e 's|^BACKEND_IMAGE=.*$|BACKEND_IMAGE=restaurant-pos-backend:uat-recipe-reviews-20261013|' -e 's|^FRONTEND_IMAGE=.*$|FRONTEND_IMAGE=restaurant-pos-frontend:uat-recipe-reviews-20261013|' .env.uat
echo 'UAT images reverted; all recipe and stock evidence preserved; no database downgrade.'
