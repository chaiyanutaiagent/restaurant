#!/usr/bin/env bash
set -euo pipefail
# Explicit, isolated database names. Abort rather than overwrite any database.
backup=/home/behappyaiagent/restaurant-uat-deploy-backups/theloft-separation-20261025.bRCFqf
container=restaurant-pos-uat-drill-postgres-1
for kind in platform restaurant retail; do
  case "$kind" in
    platform) source_db=restaurant_platform_core_db ;;
    restaurant) source_db=restaurant_uat_db ;;
    retail) source_db=retail_ops_db ;;
  esac
  target_db="theloft_rehearsal_20261025_${kind}"
  docker exec "$container" sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$target_db"
  docker exec -i "$container" sh -c 'pg_restore --exit-on-error --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$target_db" < "$backup/$source_db.dump"
  echo "RESTORED $target_db"
done
