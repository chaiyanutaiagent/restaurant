#!/usr/bin/env bash
set -euo pipefail
backup=/home/behappyaiagent/restaurant-uat-deploy-backups/recipe-operations-20261013
name=fcs-recipeops-takeaway-restore-check
test -s "$backup/takeaway-predeploy.dump"
if docker container inspect "$name" >/dev/null 2>&1; then exit 1; fi
docker run -d --name "$name" --network none --tmpfs /var/lib/postgresql/data:rw -e POSTGRES_USER=unused -e POSTGRES_PASSWORD=unused -e POSTGRES_DB=unused postgres:15-alpine >/dev/null
trap 'docker rm -f "$name" >/dev/null' EXIT
for attempt in $(seq 1 25); do
 if docker exec "$name" pg_isready -h 127.0.0.1 -U unused -d unused >/dev/null 2>&1; then break; fi
 sleep 1
done
docker exec -i "$name" pg_restore -U unused -d unused --no-owner --no-privileges --exit-on-error < "$backup/takeaway-predeploy.dump"
docker exec "$name" psql -U unused -d unused -Atc 'select count(*) from takeaway_recipes'
echo 'PASS Takeaway backup restored on isolated temporary database'
