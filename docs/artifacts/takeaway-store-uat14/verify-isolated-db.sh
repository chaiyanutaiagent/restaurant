#!/usr/bin/env bash
# Run on UAT host. Never migrates the active database or changes live containers.
set -euo pipefail
release=/home/behappyaiagent/restaurant-uat-releases/takeaway-store-uat14-print-batch
fixture=restaurant-uat14-print-fixture
candidate=restaurant-pos-backend:uat-print-uat14
runtime=/home/behappyaiagent/restaurant-uat-deploy-backups/recipe-quick-create-candidate/runtime-backend.env
test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.Config.Image}}')" = restaurant-pos-backend:uat-counter-uat13
if docker container inspect "$fixture" >/dev/null 2>&1; then echo 'Fixture name already exists; refusing reuse'; exit 1; fi
# No published ports, no network interfaces except loopback, ephemeral tmpfs storage.
docker run -d --name "$fixture" --label foodchain.disposable=uat14-print-test --network none --tmpfs /var/lib/postgresql/data -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=takeaway_ops_db postgres:15-alpine >/dev/null
cleanup() {
  test "$(docker inspect "$fixture" --format '{{index .Config.Labels "foodchain.disposable"}}')" = uat14-print-test
  docker rm -f "$fixture" >/dev/null
}
trap cleanup EXIT
for attempt in $(seq 1 30); do docker exec "$fixture" pg_isready -U postgres >/dev/null 2>&1 && break; sleep 1; done
docker exec restaurant-pos-uat-drill-postgres-1 sh -c 'pg_dump -U "$POSTGRES_USER" --no-owner --no-acl takeaway_ops_db' | docker exec -i "$fixture" psql -v ON_ERROR_STOP=1 -U postgres -d takeaway_ops_db >/dev/null
run=(docker run --rm --network "container:$fixture" --env-file "$runtime" -e TAKEAWAY_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:5432/takeaway_ops_db -v "$release/verify-isolated-db.py:/app/verify_isolated_db.py:ro")
"${run[@]}" "$candidate" alembic -c alembic-boundaries.ini -n takeaway upgrade p6takeaway0010
"${run[@]}" "$candidate" python verify_isolated_db.py
# Old UAT13 application still reads receipts after the additive migration (rollback compatibility).
"${run[@]}" restaurant-pos-backend:uat-counter-uat13 python -c 'import asyncio; from sqlalchemy import select; from app.database import TakeawaySessionLocal; from app.models.takeaway import TakeawayReceipt
async def main():
 async with TakeawaySessionLocal() as db:
  rows=list(await db.scalars(select(TakeawayReceipt))); assert rows; print("PASS: old UAT13 model reads migrated receipts; retain additive schema on rollback")
asyncio.run(main())'
sha256sum /home/behappyaiagent/restaurant-uat-downloads/takeaway-store/latest.json
