#!/usr/bin/env bash
set -euo pipefail

INTERNAL_BASE_URL="${INTERNAL_BASE_URL:-http://127.0.0.1:8000}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$PROJECT_DIR"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

psql_at() {
  docker compose exec -T postgres sh -c \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "$1"' sh "$1" \
    | sed '/^[A-Z][A-Z ]* [0-9][0-9]*$/d'
}

http_get() {
  docker compose exec -T backend python -c 'import sys, urllib.error, urllib.request; 
try:
    print(urllib.request.urlopen(sys.argv[1]).read().decode())
except urllib.error.HTTPError as e:
    sys.stderr.write(e.read().decode() + "\n")
    raise' "$1"
}

http_post_json() {
  docker compose exec -T backend python -c 'import sys, urllib.error, urllib.request; data=sys.argv[2].encode(); req=urllib.request.Request(sys.argv[1], data=data, headers={"Content-Type":"application/json"}, method="POST"); 
try:
    print(urllib.request.urlopen(req).read().decode())
except urllib.error.HTTPError as e:
    sys.stderr.write(e.read().decode() + "\n")
    raise' "$1" "$2"
}

http_auth_json() {
  local method="$1"
  local url="$2"
  local token="$3"
  local body="${4:-}"
  docker compose exec -T backend python -c 'import sys, urllib.error, urllib.request; method,url,token,body=sys.argv[1:5]; data=body.encode() if body else None; req=urllib.request.Request(url, data=data, headers={"Content-Type":"application/json","Authorization":f"Bearer {token}"}, method=method); 
try:
    print(urllib.request.urlopen(req).read().decode())
except urllib.error.HTTPError as e:
    sys.stderr.write(e.read().decode() + "\n")
    raise' "$method" "$url" "$token" "$body"
}

json_get() {
  node -e "const fs=require('fs'); const p=process.argv[1].split('.'); let v=JSON.parse(fs.readFileSync(0,'utf8')); for (const k of p) v=v?.[k]; if (v===undefined||v===null) process.exit(2); console.log(v)" "$1"
}

require_cmd docker
require_cmd node

echo "== F&B smoke: health"
http_get "$INTERNAL_BASE_URL/health" >/dev/null

echo "== F&B smoke: seed demo menu"
docker compose exec -T backend python -m app.utils.seed_fnb_demo >/dev/null

COMPANY_ID="$(psql_at "select id from companies order by created_at limit 1;")"
BRANCH_ID="$(psql_at "select id from branches where company_id='$COMPANY_ID' and deleted_at is null order by sort_order, created_at limit 1;")"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-$(docker compose exec -T backend python -c 'from app.config import settings; print(settings.default_admin_password or "")')}"
if [[ -z "$COMPANY_ID" || -z "$BRANCH_ID" || -z "$ADMIN_PASSWORD" ]]; then
  echo "Missing company, branch, or admin password for staff API smoke." >&2
  exit 1
fi

echo "== F&B smoke: staff login"
LOGIN_JSON="$(http_post_json "$INTERNAL_BASE_URL/api/v1/auth/login" "{\"company_id\":\"$COMPANY_ID\",\"branch_id\":\"$BRANCH_ID\",\"username\":\"admin\",\"password\":\"$ADMIN_PASSWORD\"}")"
ACCESS_TOKEN="$(printf '%s' "$LOGIN_JSON" | json_get data.access_token)"
if [[ -z "$ACCESS_TOKEN" ]]; then
  echo "Could not login as staff admin." >&2
  exit 1
fi

echo "== F&B smoke: configure restaurant workspace"
http_auth_json POST "$INTERNAL_BASE_URL/api/v1/restaurant/setup" "$ACCESS_TOKEN" \
  '{"has_tables":true,"table_zones":[{"zone_name":"Smoke Zone","table_count":1,"table_name_prefix":"AUTO","table_capacity":2}],"table_qr_enabled":true,"bill_at_table":true,"queue_reset":"daily","queue_prefix":"S","pickup_display_enabled":true,"kitchen_stations":["ครัวหลัก"]}' \
  >/dev/null

PRODUCT_ID="$(psql_at "select id from products where sku='FNB-DEMO-001' and product_type='menu_item' and is_active=true limit 1;")"
if [[ -z "$PRODUCT_ID" ]]; then
  echo "Demo product FNB-DEMO-001 was not found after seed." >&2
  exit 1
fi

echo "== F&B smoke: counter opens takeaway session and per-order QR"
TAKEAWAY_SESSION_JSON="$(http_auth_json POST "$INTERNAL_BASE_URL/api/v1/restaurant/sessions" "$ACCESS_TOKEN" '{"table_id":null,"guest_count":1,"customer_name":"Smoke Test","customer_phone":"0800000000"}')"
SESSION_ID="$(printf '%s' "$TAKEAWAY_SESSION_JSON" | json_get data.id)"
TAKEAWAY_QR_TOKEN="$(printf '%s' "$TAKEAWAY_SESSION_JSON" | json_get data.qr_token)"
QUEUE_NUMBER="$(printf '%s' "$TAKEAWAY_SESSION_JSON" | json_get data.queue_number)"
QUEUE_DISPLAY="S$(printf '%03d' "$QUEUE_NUMBER")"

echo "== F&B smoke: public takeaway menu"
MENU_JSON="$(http_get "$INTERNAL_BASE_URL/api/public/menu/$TAKEAWAY_QR_TOKEN")"
PRODUCT_COUNT="$(printf '%s' "$MENU_JSON" | json_get data.products.length)"
if [[ "$PRODUCT_COUNT" -lt 12 ]]; then
  echo "Expected at least 12 takeaway menu products, got $PRODUCT_COUNT" >&2
  exit 1
fi
MENU_SOURCE="$(printf '%s' "$MENU_JSON" | json_get data.source_type)"
if [[ "$MENU_SOURCE" != "quick_service" ]]; then
  echo "Expected takeaway menu source quick_service, got $MENU_SOURCE" >&2
  exit 1
fi

echo "== F&B smoke: place takeaway order from per-order QR"
ORDER_JSON="$(http_post_json "$INTERNAL_BASE_URL/api/public/menu/$TAKEAWAY_QR_TOKEN/orders" "{\"items\":[{\"product_id\":\"$PRODUCT_ID\",\"qty\":1,\"special_request\":\"smoke test\"}],\"note\":\"takeaway smoke script\"}")"
ORDER_SESSION_ID="$(printf '%s' "$ORDER_JSON" | json_get data.session_id)"
if [[ "$ORDER_SESSION_ID" != "$SESSION_ID" ]]; then
  echo "Expected takeaway order to use session $SESSION_ID, got $ORDER_SESSION_ID" >&2
  exit 1
fi

echo "== F&B smoke: public status"
STATUS_JSON="$(http_get "$INTERNAL_BASE_URL/api/public/menu/$TAKEAWAY_QR_TOKEN/status?session_id=$SESSION_ID")"
ITEM_STATUS="$(printf '%s' "$STATUS_JSON" | json_get data.items.0.status)"
if [[ "$ITEM_STATUS" != "pending" ]]; then
  echo "Expected initial item status pending, got $ITEM_STATUS" >&2
  exit 1
fi

ORDER_ITEM_ID="$(printf '%s' "$STATUS_JSON" | json_get data.items.0.id)"
TICKET_ID="$(psql_at "select id from kitchen_tickets where order_item_id='$ORDER_ITEM_ID' limit 1;")"
if [[ -z "$TICKET_ID" ]]; then
  echo "Kitchen ticket was not created for order item $ORDER_ITEM_ID" >&2
  exit 1
fi

echo "== F&B smoke: advance kitchen ticket pending -> cooking -> done"
psql_at "update kitchen_tickets set status='cooking' where id='$TICKET_ID'; update dining_order_items set status='cooking' where id='$ORDER_ITEM_ID';" >/dev/null
STATUS_JSON="$(http_get "$INTERNAL_BASE_URL/api/public/menu/$TAKEAWAY_QR_TOKEN/status?session_id=$SESSION_ID")"
ITEM_STATUS="$(printf '%s' "$STATUS_JSON" | json_get data.items.0.status)"
if [[ "$ITEM_STATUS" != "cooking" ]]; then
  echo "Expected item status cooking, got $ITEM_STATUS" >&2
  exit 1
fi

psql_at "update kitchen_tickets set status='done', done_at=now() where id='$TICKET_ID'; update dining_order_items set status='done' where id='$ORDER_ITEM_ID';" >/dev/null
STATUS_JSON="$(http_get "$INTERNAL_BASE_URL/api/public/menu/$TAKEAWAY_QR_TOKEN/status?session_id=$SESSION_ID")"
ITEM_STATUS="$(printf '%s' "$STATUS_JSON" | json_get data.items.0.status)"
if [[ "$ITEM_STATUS" != "done" ]]; then
  echo "Expected item status done, got $ITEM_STATUS" >&2
  exit 1
fi

echo "== F&B smoke: pickup queue"
PICKUP_SESSION_ID="$(psql_at "select s.id from dining_sessions s where s.id='$SESSION_ID' and s.table_id is null and s.status='open' and exists (select 1 from kitchen_tickets kt where kt.session_id=s.id and kt.status='done') and not exists (select 1 from kitchen_tickets kt where kt.session_id=s.id and kt.status in ('pending','cooking')) limit 1;")"
if [[ "$PICKUP_SESSION_ID" != "$SESSION_ID" ]]; then
  echo "Expected pickup queue to include session $SESSION_ID" >&2
  exit 1
fi

PICKUP_JSON="$(http_auth_json GET "$INTERNAL_BASE_URL/api/v1/restaurant/pickup-queue" "$ACCESS_TOKEN")"
PICKUP_MATCH="$(printf '%s' "$PICKUP_JSON" | node -e "const fs=require('fs'); const session=process.argv[1]; const rows=JSON.parse(fs.readFileSync(0,'utf8')).data||[]; const row=rows.find(r=>r.session_id===session); if(!row) process.exit(2); console.log(String(row.queue_number).padStart(3,'0'))" "$SESSION_ID")"
if [[ "$PICKUP_MATCH" != "${QUEUE_DISPLAY: -3}" ]]; then
  echo "Expected pickup API to include queue $QUEUE_DISPLAY, got $PICKUP_MATCH" >&2
  exit 1
fi

echo "== F&B smoke: dine-in customer order"
TABLE_JSON="$(http_auth_json POST "$INTERNAL_BASE_URL/api/v1/restaurant/tables" "$ACCESS_TOKEN" "{\"name\":\"SMOKE-$(date +%H%M%S)\",\"capacity\":2,\"table_type\":\"dine_in\"}")"
TABLE_ID="$(printf '%s' "$TABLE_JSON" | json_get data.id)"
DINE_SESSION_JSON="$(http_auth_json POST "$INTERNAL_BASE_URL/api/v1/restaurant/sessions" "$ACCESS_TOKEN" "{\"table_id\":\"$TABLE_ID\",\"guest_count\":2}")"
DINE_SESSION_ID="$(printf '%s' "$DINE_SESSION_JSON" | json_get data.id)"
DINE_QR_TOKEN="$(printf '%s' "$DINE_SESSION_JSON" | json_get data.qr_token)"
DINE_MENU_JSON="$(http_get "$INTERNAL_BASE_URL/api/public/menu/$DINE_QR_TOKEN")"
DINE_PRODUCT_COUNT="$(printf '%s' "$DINE_MENU_JSON" | json_get data.products.length)"
if [[ "$DINE_PRODUCT_COUNT" -lt 12 ]]; then
  echo "Expected at least 12 dine-in menu products, got $DINE_PRODUCT_COUNT" >&2
  exit 1
fi

DINE_ORDER_JSON="$(http_post_json "$INTERNAL_BASE_URL/api/public/menu/$DINE_QR_TOKEN/orders" "{\"items\":[{\"product_id\":\"$PRODUCT_ID\",\"qty\":2,\"special_request\":\"dine smoke\"}],\"note\":\"dine-in smoke script\"}")"
ORDER_SESSION_ID="$(printf '%s' "$DINE_ORDER_JSON" | json_get data.session_id)"
if [[ "$ORDER_SESSION_ID" != "$DINE_SESSION_ID" ]]; then
  echo "Expected dine-in order to use session $DINE_SESSION_ID, got $ORDER_SESSION_ID" >&2
  exit 1
fi
DINE_STATUS_JSON="$(http_get "$INTERNAL_BASE_URL/api/public/menu/$DINE_QR_TOKEN/status?session_id=$DINE_SESSION_ID")"
DINE_ITEM_ID="$(printf '%s' "$DINE_STATUS_JSON" | json_get data.items.0.id)"
DINE_ITEM_STATUS="$(printf '%s' "$DINE_STATUS_JSON" | json_get data.items.0.status)"
if [[ "$DINE_ITEM_STATUS" != "pending" ]]; then
  echo "Expected dine-in item status pending, got $DINE_ITEM_STATUS" >&2
  exit 1
fi

DINE_TICKET_ID="$(psql_at "select id from kitchen_tickets where order_item_id='$DINE_ITEM_ID' limit 1;")"
if [[ -z "$DINE_TICKET_ID" ]]; then
  echo "Kitchen ticket was not created for dine-in order item $DINE_ITEM_ID" >&2
  exit 1
fi

echo "== F&B smoke: dine-in kitchen and served workflow"
http_auth_json PATCH "$INTERNAL_BASE_URL/api/v1/restaurant/kitchen/$DINE_TICKET_ID" "$ACCESS_TOKEN" '{"status":"cooking"}' >/dev/null
http_auth_json PATCH "$INTERNAL_BASE_URL/api/v1/restaurant/kitchen/$DINE_TICKET_ID" "$ACCESS_TOKEN" '{"status":"done"}' >/dev/null
http_auth_json PATCH "$INTERNAL_BASE_URL/api/v1/restaurant/order-items/$DINE_ITEM_ID/status" "$ACCESS_TOKEN" '{"status":"served"}' >/dev/null
DINE_DETAIL_JSON="$(http_auth_json GET "$INTERNAL_BASE_URL/api/v1/restaurant/sessions/$DINE_SESSION_ID/detail" "$ACCESS_TOKEN")"
DINE_SERVED_COUNT="$(printf '%s' "$DINE_DETAIL_JSON" | json_get data.served_count)"
if [[ "$DINE_SERVED_COUNT" != "2" ]]; then
  echo "Expected dine-in served count 2, got $DINE_SERVED_COUNT" >&2
  exit 1
fi

echo "== F&B smoke: dine-in bill and checkout"
BILL_JSON="$(http_post_json "$INTERNAL_BASE_URL/api/public/menu/$DINE_QR_TOKEN/bill?session_id=$DINE_SESSION_ID" '{}')"
BILL_STATUS="$(printf '%s' "$BILL_JSON" | json_get data.status)"
if [[ "$BILL_STATUS" != "bill_requested" ]]; then
  echo "Expected bill_requested, got $BILL_STATUS" >&2
  exit 1
fi
DINE_TOTAL="$(printf '%s' "$DINE_DETAIL_JSON" | node -e "const fs=require('fs'); const d=JSON.parse(fs.readFileSync(0,'utf8')).data; const total=d.orders.flatMap(o=>o.items).filter(i=>i.status!=='cancelled').reduce((s,i)=>s+(Number(i.unit_price)*Number(i.qty)),0); console.log(total.toFixed(2))")"
CHECKOUT_JSON="$(http_auth_json POST "$INTERNAL_BASE_URL/api/v1/restaurant/sessions/$DINE_SESSION_ID/checkout" "$ACCESS_TOKEN" "{\"payment_method\":\"cash\",\"paid_amount\":\"$DINE_TOTAL\",\"payments\":[{\"payment_method\":\"cash\",\"amount\":\"$DINE_TOTAL\"}],\"note\":\"dine-in smoke checkout\"}")"
CHECKOUT_SOURCE="$(printf '%s' "$CHECKOUT_JSON" | json_get data.source_type)"
CHECKOUT_TOTAL="$(printf '%s' "$CHECKOUT_JSON" | json_get data.total_amount)"
if [[ "$CHECKOUT_SOURCE" != "dine_in" || "$CHECKOUT_TOTAL" != "$DINE_TOTAL" ]]; then
  echo "Expected dine-in checkout total $DINE_TOTAL, got source=$CHECKOUT_SOURCE total=$CHECKOUT_TOTAL" >&2
  exit 1
fi

echo "PASS: F&B smoke OK takeaway_session=$SESSION_ID queue=$QUEUE_DISPLAY takeaway_ticket=$TICKET_ID dine_session=$DINE_SESSION_ID dine_ticket=$DINE_TICKET_ID sale_total=$CHECKOUT_TOTAL"
