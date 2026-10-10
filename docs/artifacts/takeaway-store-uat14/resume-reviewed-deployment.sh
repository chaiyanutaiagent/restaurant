#!/usr/bin/env bash
# Initial safety check rolled back only because BACKEND_IMAGE changed as intended.
# Migration/verified backup already exist. Resume without repeating either or overwriting evidence.
set -euo pipefail
release=/home/behappyaiagent/restaurant-uat-releases/takeaway-store-uat14-print-batch
backup=/home/behappyaiagent/restaurant-uat-deploy-backups/takeaway-store-uat14-print-batch
cd /home/behappyaiagent/restaurant-uat-releases/3760d60
new=restaurant-pos-backend:uat-print-uat14
test "$(docker inspect restaurant-pos-uat-drill-backend-1 --format '{{.Config.Image}}')" = restaurant-pos-backend:rollback-before-print-uat14
test "$(docker image inspect "$new" --format '{{.Id}}')" = sha256:83eacd273d1ff6ca1111b42d3a11bf73b1ebaf279643b0ca15f06ad6ea76261c
sha256sum -c "$backup/takeaway.sha256"
python3 - "$backup" <<'PY'
import json,subprocess,sys
from pathlib import Path
b=Path(sys.argv[1]); old=json.loads((b/'backend-before.json').read_text())[0]
live=json.loads(subprocess.check_output(['docker','inspect','restaurant-pos-uat-drill-backend-1']))[0]
assert old['Image']==live['Image']
def env(c): return {k:v for k,v in (s.split('=',1) for s in c['Config']['Env']) if k!='BACKEND_IMAGE'}
assert env(old)==env(live)
def clean(s): return '\n'.join(x for x in s.splitlines() if not x.startswith('BACKEND_IMAGE='))
assert clean((b/'.env.uat').read_text())==clean(Path('.env.uat').read_text())
print('PASS: only BACKEND_IMAGE differs; all flags unchanged')
PY
docker run --rm --network restaurant-pos-uat-drill_restaurant_pos_prod --env-file "$backup/runtime-backend.env" -v "$release/deployment-preflight.py:/app/deployment_preflight.py:ro" "$new" python deployment_preflight.py after > "$backup/database-before-retry.json"
rollback() { trap - ERR; bash "$backup/rollback-backend.sh"; exit 1; }
trap rollback ERR
BACKEND_IMAGE="$new" docker compose -p restaurant-pos-uat-drill --env-file .env.uat -f docker-compose.prod.yml -f docker-compose.uat.yml -f docker-compose.uat-superadmin.yml up -d --no-deps --no-build backend
for attempt in $(seq 1 30); do
  if docker exec restaurant-pos-uat-drill-backend-1 python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=3).read()" 2>/dev/null; then break; fi
  sleep 1
done
docker exec restaurant-pos-uat-drill-backend-1 python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=5).read().decode())"
docker exec restaurant-pos-uat-drill-nginx-1 nginx -t
docker exec restaurant-pos-uat-drill-nginx-1 nginx -s reload
docker inspect restaurant-pos-uat-drill-backend-1 > "$backup/backend-after-retry.json"
docker inspect restaurant-pos-prod-backend-1 restaurant-pos-prod-frontend-1 restaurant-pos-prod-postgres-1 restaurant-pos-prod-nginx-1 restaurant-pos-uat-drill-frontend-1 restaurant-pos-uat-drill-postgres-1 --format '{{.Name}} {{.Id}} {{.Image}} {{json .Config.Env}}' > "$backup/untouched-after-retry.txt"
cmp "$backup/untouched-before.txt" "$backup/untouched-after-retry.txt"
python3 - "$backup" <<'PY'
import json,sys
from pathlib import Path
b=Path(sys.argv[1]); old=json.loads((b/'backend-before.json').read_text())[0]; new=json.loads((b/'backend-after-retry.json').read_text())[0]
def env(c): return dict(s.split('=',1) for s in c['Config']['Env'])
x=env(old); y=env(new)
assert new['Config']['Image']=='restaurant-pos-backend:uat-print-uat14'
# env_file retains the previous image pointer until persistence below; image identity is Config.Image.
y.pop('BACKEND_IMAGE'); x.pop('BACKEND_IMAGE')
assert x==y
assert json.loads((b/'database-before.json').read_text())['queue4_snapshot_sha256']==json.loads((b/'database-before-retry.json').read_text())['queue4_snapshot_sha256']
print('PASS: runtime flags and original queue unchanged')
PY
test "$(sha256sum /home/behappyaiagent/restaurant-uat-downloads/takeaway-store/latest.json | cut -d' ' -f1)" = 026f7cb1d657660eabb8f604892607f66679fa683b9723a42800b9e56c2d926b
sed -i "s|^BACKEND_IMAGE=.*$|BACKEND_IMAGE=$new|" .env.uat
trap - ERR
echo 'PASS: backend UAT14 deployed; additive schema retained; latest UAT13 unchanged'
