#!/usr/bin/env bash
set -euo pipefail
release=/home/behappyaiagent/restaurant-uat-releases/recipe-operations-20261013
backup=/home/behappyaiagent/restaurant-uat-deploy-backups/recipe-operations-20261013
qa=/home/behappyaiagent/restaurant-uat-releases/document-lifecycle-20261013/qa.env
name=fcs-recipeops-isolated-20261013
image=restaurant-pos-backend:uat-recipe-operations-20261013-r2
umask 077
if ! test -s "$backup/predeploy.dump"; then
 docker exec restaurant-pos-uat-drill-postgres-1 pg_dump -U restaurant_uat -d restaurant_uat_db -Fc > "$backup/predeploy.dump"
fi
sha256sum "$backup/predeploy.dump" > "$backup/predeploy.sha256"
if docker container inspect "$name" >/dev/null 2>&1; then exit 1; fi
docker run -d --name "$name" --network none --tmpfs /var/lib/postgresql/data:rw -e POSTGRES_USER=unused -e POSTGRES_PASSWORD=unused -e POSTGRES_DB=unused postgres:15-alpine >/dev/null
trap 'docker rm -f "$name" >/dev/null' EXIT
for attempt in $(seq 1 25); do
 if docker exec "$name" pg_isready -h 127.0.0.1 -U unused -d unused >/dev/null 2>&1; then break; fi
 sleep 1
done
docker exec -i "$name" pg_restore -U unused -d unused --no-owner --no-privileges --exit-on-error < "$backup/predeploy.dump"
docker exec "$name" createdb -U unused takeaway_unused
docker run --rm --network container:"$name" --env-file "$qa" "$image" alembic upgrade recipeops0034
docker run --rm --network container:"$name" --env-file "$qa" -e PYTHONPATH=/app --mount type=bind,src="$release/backend/tests/integration_recipe_operations.py",dst=/check.py,readonly "$image" python /check.py
