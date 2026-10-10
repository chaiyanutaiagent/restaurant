#!/usr/bin/env bash
set -euo pipefail
release=/home/behappyaiagent/restaurant-uat-releases/takeaway-store-uat14-print-batch
backup=/home/behappyaiagent/restaurant-uat-deploy-backups/takeaway-store-uat14-print-batch
cd /home/behappyaiagent/restaurant-uat-releases/3760d60
compose=(docker compose -p restaurant-pos-uat-drill --env-file .env.uat -f docker-compose.prod.yml -f docker-compose.uat.yml -f docker-compose.uat-superadmin.yml)
old=restaurant-pos-backend:uat-counter-uat13
new=restaurant-pos-backend:uat-print-uat14
untouched=(restaurant-pos-prod-backend-1 restaurant-pos-prod-frontend-1 restaurant-pos-prod-postgres-1 restaurant-pos-prod-nginx-1 restaurant-pos-uat-drill-frontend-1 restaurant-pos-uat-drill-postgres-1)
test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.Config.Image}}')" = "$old"
test "$(docker image inspect "$new" --format '{{.Id}}')" = sha256:83eacd273d1ff6ca1111b42d3a11bf73b1ebaf279643b0ca15f06ad6ea76261c
test "$(sha256sum /home/behappyaiagent/restaurant-uat-downloads/takeaway-store/latest.json | cut -d' ' -f1)" = 026f7cb1d657660eabb8f604892607f66679fa683b9723a42800b9e56c2d926b
umask 077
mkdir "$backup"
cp .env.uat docker-compose.prod.yml docker-compose.uat.yml docker-compose.uat-superadmin.yml "$backup/"
cp "$release/rollback-backend.sh" "$backup/rollback-backend.sh"
docker inspect "${untouched[@]}" --format '{{.Name}} {{.Id}} {{.Image}} {{json .Config.Env}}' > "$backup/untouched-before.txt"
docker inspect restaurant-pos-uat-drill-backend-1 > "$backup/backend-before.json"
docker inspect restaurant-pos-uat-drill-backend-1 --format '{{range .Config.Env}}{{println .}}{{end}}' > "$backup/runtime-backend.env"
docker tag "$old" restaurant-pos-backend:rollback-before-print-uat14
docker exec restaurant-pos-uat-drill-postgres-1 sh -c 'pg_dump -U "$POSTGRES_USER" -Fc takeaway_ops_db' > "$backup/takeaway.dump"
docker exec -i restaurant-pos-uat-drill-postgres-1 pg_restore --list < "$backup/takeaway.dump" > "$backup/takeaway-list.txt"
docker exec -i restaurant-pos-uat-drill-postgres-1 pg_restore --file=/dev/null < "$backup/takeaway.dump"
test -s "$backup/takeaway-list.txt"
sha256sum "$backup/takeaway.dump" > "$backup/takeaway.sha256"
run=(docker run --rm --network restaurant-pos-uat-drill_restaurant_pos_prod --env-file "$backup/runtime-backend.env" -v "$release/deployment-preflight.py:/app/deployment_preflight.py:ro")
"${run[@]}" "$new" python deployment_preflight.py before > "$backup/database-before.json"
python3 - <<'PY'
import json,subprocess
cmd=['docker','compose','-p','restaurant-pos-uat-drill','--env-file','.env.uat','-f','docker-compose.prod.yml','-f','docker-compose.uat.yml','-f','docker-compose.uat-superadmin.yml']
config=json.loads(subprocess.check_output(cmd+['config','--format','json']))
live=json.loads(subprocess.check_output(['docker','inspect','restaurant-pos-uat-drill-backend-1']))[0]
env=dict(x.split('=',1) for x in live['Config']['Env'])
assert all(env.get(k)==str(v) for k,v in config['services']['backend'].get('environment',{}).items() if k not in ('BACKEND_IMAGE','FRONTEND_IMAGE')), 'Configuration drift'
print('PASS: UAT config and flags match live backend')
PY
cmp .env.uat "$backup/.env.uat"
test "$(awk '/^BACKEND_IMAGE=/{n++} END{print n}' .env.uat)" = 1
# Abort rather than waiting indefinitely for a busy receipt table. Alembic uses transactional DDL.
"${run[@]}" -e 'PGOPTIONS=-c lock_timeout=5s -c statement_timeout=30s' "$new" alembic -c alembic-boundaries.ini -n takeaway upgrade p6takeaway0010
"${run[@]}" "$new" python deployment_preflight.py after > "$backup/database-after-migration.json"
rollback() { trap - ERR; bash "$backup/rollback-backend.sh"; exit 1; }
trap rollback ERR
BACKEND_IMAGE="$new" "${compose[@]}" up -d --no-deps --no-build backend
for attempt in $(seq 1 30); do
  if docker exec restaurant-pos-uat-drill-backend-1 python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=3).read()" 2>/dev/null; then break; fi
  sleep 1
done
docker exec restaurant-pos-uat-drill-backend-1 python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=5).read().decode())"
docker exec restaurant-pos-uat-drill-nginx-1 nginx -t
docker exec restaurant-pos-uat-drill-nginx-1 nginx -s reload
docker inspect "${untouched[@]}" --format '{{.Name}} {{.Id}} {{.Image}} {{json .Config.Env}}' > "$backup/untouched-after.txt"
cmp "$backup/untouched-before.txt" "$backup/untouched-after.txt"
docker inspect restaurant-pos-uat-drill-backend-1 > "$backup/backend-after.json"
python3 - "$backup" <<'PY'
import json,sys
from pathlib import Path
b=Path(sys.argv[1])
old=json.loads((b/'backend-before.json').read_text())[0]
new=json.loads((b/'backend-after.json').read_text())[0]
old_env=dict(v.split('=',1) for v in old['Config']['Env'])
new_env=dict(v.split('=',1) for v in new['Config']['Env'])
assert new['Config']['Image'] == 'restaurant-pos-backend:uat-print-uat14'
assert {k:v for k,v in old_env.items() if k!='BACKEND_IMAGE'} == {k:v for k,v in new_env.items() if k!='BACKEND_IMAGE'}, 'Runtime flags changed'
before=json.loads((b/'database-before.json').read_text())
after=json.loads((b/'database-after-migration.json').read_text())
assert before['queue4_snapshot_sha256']==after['queue4_snapshot_sha256'], 'Real order changed'
print('PASS: Production/shared web/flags and queue4 unchanged')
PY
test "$(sha256sum /home/behappyaiagent/restaurant-uat-downloads/takeaway-store/latest.json | cut -d' ' -f1)" = 026f7cb1d657660eabb8f604892607f66679fa683b9723a42800b9e56c2d926b
cmp .env.uat "$backup/.env.uat"
sed -i "s|^BACKEND_IMAGE=.*$|BACKEND_IMAGE=$new|" .env.uat
trap - ERR
echo 'PASS: UAT backend + additive migration deployed; public latest remains UAT13'
