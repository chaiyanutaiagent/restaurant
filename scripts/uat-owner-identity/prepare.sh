#!/usr/bin/env bash
set -euo pipefail
umask 077
test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.Config.Image}}')" = restaurant-pos-backend:uat-password-policy-20261020-r2
backup=$(mktemp -d /home/behappyaiagent/restaurant-uat-deploy-backups/owner-identity-20261025.XXXXXX)
cp -p /home/behappyaiagent/restaurant-uat-releases/3760d60/.env.uat "$backup/env.uat"
cp -p /home/behappyaiagent/restaurant-uat-releases/3760d60/docker-compose.uat-superadmin.yml "$backup/superadmin-compose.yml"
for database in restaurant_platform_core_db restaurant_uat_db restaurant_ops_db retail_ops_db takeaway_ops_db; do
  docker exec restaurant-pos-uat-drill-postgres-1 sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$1"' sh "$database" > "$backup/$database.dump"
  docker exec -i restaurant-pos-uat-drill-postgres-1 pg_restore --list < "$backup/$database.dump" > /dev/null
done
cd "$backup"
sha256sum *.dump > SHA256SUMS
echo "$backup"
