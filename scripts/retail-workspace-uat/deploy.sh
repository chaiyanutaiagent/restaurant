#!/usr/bin/env bash
set -Eeuo pipefail
artifact_dir="${1:?provide extracted artifact directory}"
[[ "$artifact_dir" == /home/behappyaiagent/restaurant-uat-deploy-backups/retail-workspace.* ]] || exit 2
downloads=/home/behappyaiagent/restaurant-uat-downloads
release=native-pos-0.1.0-uat.14
apk=foodchainservice-retail-0.1.0-uat.14.apk
expected_sha="${2:?provide verified APK SHA256}"
[[ "$expected_sha" =~ ^[a-f0-9]{64}$ ]] || exit 2
old_image=restaurant-pos-frontend:uat-retail-photo-20261026-r1
new_image=restaurant-pos-frontend:uat-retail-share-20261026-r1
old_backend=restaurant-pos-backend:uat-retail-payments-20261026-r1
new_backend=restaurant-pos-backend:uat-retail-payments-20261026-r1
cd /home/behappyaiagent/restaurant-uat-releases/3760d60
compose() { docker compose -p restaurant-pos-uat-drill --env-file .env.uat -f docker-compose.prod.yml -f docker-compose.uat.yml -f docker-compose.uat-superadmin.yml "$@"; }
test "$(docker inspect --format '{{.Config.Image}}' restaurant-pos-uat-drill-frontend-1)" = "$old_image"
test "$(docker inspect --format '{{.Config.Image}}' restaurant-pos-uat-drill-backend-1)" = "$old_backend"
test ! -e "$downloads/$release"
test -f "$downloads/native-pos-updates/retail.json"
printf '%s  %s\n' "$expected_sha" "$artifact_dir/$release/$apk" | sha256sum -c -
cp .env.uat "$artifact_dir/env.uat.rollback"
cp docker-compose.uat-superadmin.yml "$artifact_dir/compose.rollback.yml"
cp "$downloads/native-pos-updates/retail.json" "$artifact_dir/retail.rollback.json"
sha256sum "$downloads/native-pos-updates/restaurant.json" > "$artifact_dir/restaurant.before.sha256"
docker inspect --format '{{.Config.Image}}' restaurant-pos-uat-drill-backend-1 > "$artifact_dir/backend.before"
docker inspect --format '{{.Config.Image}}' restaurant-pos-prod-frontend-1 > "$artifact_dir/production.before"
docker inspect --format '{{.Config.Image}}' restaurant-pos-prod-backend-1 > "$artifact_dir/production-backend.before"
rollback() {
  cp "$artifact_dir/env.uat.rollback" .env.uat
  cp "$artifact_dir/compose.rollback.yml" docker-compose.uat-superadmin.yml
  cp "$artifact_dir/retail.rollback.json" "$downloads/native-pos-updates/retail.json"
  compose up -d --no-deps --no-build frontend
  docker exec restaurant-pos-uat-drill-nginx-1 nginx -s reload
  echo 'Rolled back UAT frontend and Retail update channel; immutable APK retained.'
}
trap rollback ERR
docker build -t "$new_image" "$artifact_dir"
chmod -R u=rwX,go=rX "$artifact_dir/$release"
mv "$artifact_dir/$release" "$downloads/$release"
sed -i "s|$old_image|$new_image|g;s|$old_backend|$new_backend|g" .env.uat docker-compose.uat-superadmin.yml
compose up -d --no-deps --no-build frontend
docker exec restaurant-pos-uat-drill-nginx-1 nginx -s reload
ready=0
for attempt in 1 2 3 4 5; do
  if curl -fsS -H 'Host: theloft.foodchainservice.com' http://127.0.0.1:18081/retail/pos -o "$artifact_dir/served-index.html" && cmp -s "$artifact_dir/dist/index.html" "$artifact_dir/served-index.html"; then ready=1; break; fi
  sleep 2
done
test "$ready" = 1
ready=0
for attempt in {1..15}; do
  if docker exec restaurant-pos-uat-drill-backend-1 python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health/ready", timeout=3)' ; then ready=1; break; fi
  sleep 2
done
test "$ready" = 1
# Publish the signed update only after the immutable APK and web are ready.
cp "$artifact_dir/retail.json" "$downloads/native-pos-updates/retail.json.next"
chmod 644 "$downloads/native-pos-updates/retail.json.next"
mv "$downloads/native-pos-updates/retail.json.next" "$downloads/native-pos-updates/retail.json"
sha256sum -c "$artifact_dir/restaurant.before.sha256"
test "$(docker inspect --format '{{.Config.Image}}' restaurant-pos-uat-drill-backend-1)" = "$new_backend"
test "$(docker inspect --format '{{.Config.Image}}' restaurant-pos-prod-frontend-1)" = "$(<"$artifact_dir/production.before")"
test "$(docker inspect --format '{{.Config.Image}}' restaurant-pos-prod-backend-1)" = "$(<"$artifact_dir/production-backend.before")"
trap - ERR
echo "Deployed $new_image; rollback files: $artifact_dir"
