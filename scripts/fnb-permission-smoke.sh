#!/usr/bin/env bash
set -euo pipefail

INTERNAL_BASE_URL="${INTERNAL_BASE_URL:-http://127.0.0.1:8000}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SMOKE_PASSWORD="${SMOKE_PASSWORD:-SmokePass123!}"

cd "$PROJECT_DIR"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

psql_at() {
  docker compose exec -T postgres psql -U erp_user -d erp_pos_db -Atc "$1"
}

json_get() {
  node -e "const fs=require('fs'); const p=process.argv[1].split('.'); let v=JSON.parse(fs.readFileSync(0,'utf8')); for (const k of p) v=v?.[k]; if (v===undefined||v===null) process.exit(2); console.log(v)" "$1"
}

http_post_json() {
  local url="$1"
  local body="$2"
  docker compose exec -T backend python -c 'import sys, urllib.error, urllib.request; data=sys.argv[2].encode(); req=urllib.request.Request(sys.argv[1], data=data, headers={"Content-Type":"application/json"}, method="POST");
try:
    print(urllib.request.urlopen(req).read().decode())
except urllib.error.HTTPError as e:
    sys.stderr.write(e.read().decode() + "\n")
    raise' "$url" "$body"
}

http_auth_expect() {
  local method="$1"
  local url="$2"
  local token="$3"
  local expected="$4"
  local body="${5:-}"
  docker compose exec -T backend python -c 'import sys, urllib.error, urllib.request
method,url,token,expected,body=sys.argv[1:6]
data=body.encode() if body else None
req=urllib.request.Request(url, data=data, headers={"Content-Type":"application/json","Authorization":f"Bearer {token}"}, method=method)
try:
    response=urllib.request.urlopen(req)
    status=response.status
    payload=response.read().decode()
except urllib.error.HTTPError as e:
    status=e.code
    payload=e.read().decode()
if str(status) != expected:
    sys.stderr.write(f"Expected HTTP {expected} for {method} {url}, got {status}\n{payload}\n")
    sys.exit(1)
print(payload)' "$method" "$url" "$token" "$expected" "$body"
}

seed_roles_and_users() {
  docker compose exec -T -e SMOKE_PASSWORD="$SMOKE_PASSWORD" backend python -c 'import asyncio
import os
from sqlalchemy import select, delete, insert
from app.database import AsyncSessionLocal
from app.models.branch import Branch
from app.models.company import Company
from app.models.role import Permission, Role, role_permissions_table
from app.models.user import User, UserBranch
from app.utils.security import hash_password

PASSWORD = os.environ["SMOKE_PASSWORD"]
ROLE_DEFS = {
    "FNB Smoke Cashier": ["fb.menu.view", "fb.table.manage", "fb.order.create"],
    "FNB Smoke Kitchen": ["fb.menu.view", "fb.kitchen.manage"],
    "FNB Smoke Recipe": ["fb.menu.view", "fb.recipe.manage", "fb.report.view"],
    "FNB Smoke Manager": ["fb.menu.view", "fb.table.manage", "fb.order.create", "fb.kitchen.manage", "fb.recipe.manage", "fb.report.view", "fb.settings.manage"],
}
USER_DEFS = {
    "fnb_smoke_cashier": "FNB Smoke Cashier",
    "fnb_smoke_kitchen": "FNB Smoke Kitchen",
    "fnb_smoke_recipe": "FNB Smoke Recipe",
    "fnb_smoke_manager": "FNB Smoke Manager",
}

async def main():
    async with AsyncSessionLocal() as db:
        company = await db.scalar(select(Company).where(Company.is_active.is_(True)).order_by(Company.created_at).limit(1))
        if not company:
            raise RuntimeError("No active company found")
        branch = await db.scalar(
            select(Branch)
            .where(Branch.company_id == company.id, Branch.deleted_at.is_(None), Branch.is_active.is_(True))
            .order_by(Branch.sort_order, Branch.created_at)
            .limit(1)
        )
        if not branch:
            raise RuntimeError("No active branch found")

        permissions = {
            permission.code: permission
            for permission in (await db.scalars(select(Permission).where(Permission.code.in_({code for codes in ROLE_DEFS.values() for code in codes})))).all()
        }
        missing = sorted({code for codes in ROLE_DEFS.values() for code in codes} - set(permissions))
        if missing:
            raise RuntimeError(f"Missing permissions: {missing}")

        roles = {}
        for name, codes in ROLE_DEFS.items():
            role = await db.scalar(select(Role).where(Role.company_id == company.id, Role.name == name, Role.deleted_at.is_(None)))
            if not role:
                role = Role(company_id=company.id, name=name, description="F&B permission smoke test role", is_system=False)
                db.add(role)
                await db.flush()
            else:
                role.description = "F&B permission smoke test role"
            await db.execute(delete(role_permissions_table).where(role_permissions_table.c.role_id == role.id))
            await db.execute(insert(role_permissions_table).values([
                {"role_id": role.id, "permission_id": permissions[code].id}
                for code in codes
            ]))
            roles[name] = role

        hashed = hash_password(PASSWORD)
        for username, role_name in USER_DEFS.items():
            user = await db.scalar(select(User).where(User.company_id == company.id, User.username == username, User.deleted_at.is_(None)))
            if not user:
                user = User(
                    company_id=company.id,
                    username=username,
                    email=f"{username}@example.test",
                    hashed_password=hashed,
                    display_name=username.replace("_", " ").title(),
                    is_active=True,
                    is_superuser=False,
                )
                db.add(user)
                await db.flush()
            else:
                user.hashed_password = hashed
                user.is_active = True
                user.is_superuser = False

            assignment = await db.scalar(
                select(UserBranch).where(
                    UserBranch.user_id == user.id,
                    UserBranch.branch_id == branch.id,
                    UserBranch.deleted_at.is_(None),
                )
            )
            if not assignment:
                assignment = UserBranch(user_id=user.id, branch_id=branch.id, role_id=roles[role_name].id, is_default=True)
                db.add(assignment)
            else:
                assignment.role_id = roles[role_name].id
                assignment.is_default = True

        await db.commit()
        print(f"Seeded F&B permission smoke users for company={company.id} branch={branch.id}")

asyncio.run(main())'
}

login_as() {
  local username="$1"
  local company_id="$2"
  local branch_id="$3"
  local login_json
  login_json="$(http_post_json "$INTERNAL_BASE_URL/api/v1/auth/login" "{\"company_id\":\"$company_id\",\"branch_id\":\"$branch_id\",\"username\":\"$username\",\"password\":\"$SMOKE_PASSWORD\"}")"
  printf '%s' "$login_json" | json_get data.access_token
}

require_cmd docker
require_cmd node

echo "== F&B permission smoke: seed permissions and demo menu"
docker compose exec -T backend python -c '
import asyncio
from app.database import AsyncSessionLocal
from app.utils.seed_permissions import seed_default_permissions

async def main():
    async with AsyncSessionLocal() as db:
        await seed_default_permissions(db)

asyncio.run(main())
' >/dev/null
docker compose exec -T backend python -m app.utils.seed_fnb_demo >/dev/null
seed_roles_and_users

COMPANY_ID="$(psql_at "select id from companies order by created_at limit 1;")"
BRANCH_ID="$(psql_at "select id from branches where company_id='$COMPANY_ID' and deleted_at is null order by sort_order, created_at limit 1;")"
if [[ -z "$COMPANY_ID" || -z "$BRANCH_ID" ]]; then
  echo "Missing company or branch for permission smoke." >&2
  exit 1
fi

TODAY="$(date +%F)"
CASHIER_TOKEN="$(login_as fnb_smoke_cashier "$COMPANY_ID" "$BRANCH_ID")"
KITCHEN_TOKEN="$(login_as fnb_smoke_kitchen "$COMPANY_ID" "$BRANCH_ID")"
RECIPE_TOKEN="$(login_as fnb_smoke_recipe "$COMPANY_ID" "$BRANCH_ID")"
MANAGER_TOKEN="$(login_as fnb_smoke_manager "$COMPANY_ID" "$BRANCH_ID")"

echo "== F&B permission smoke: cashier"
http_auth_expect GET "$INTERNAL_BASE_URL/api/v1/restaurant/tables" "$CASHIER_TOKEN" 200 >/dev/null
http_auth_expect POST "$INTERNAL_BASE_URL/api/v1/restaurant/tables" "$CASHIER_TOKEN" 201 "{\"name\":\"PERM-CASHIER-$(date +%H%M%S)\",\"capacity\":2,\"table_type\":\"dine_in\"}" >/dev/null
http_auth_expect GET "$INTERNAL_BASE_URL/api/v1/restaurant/kitchen" "$CASHIER_TOKEN" 403 >/dev/null
http_auth_expect POST "$INTERNAL_BASE_URL/api/v1/restaurant/raw-materials" "$CASHIER_TOKEN" 403 '{"sku":"PERM-CASHIER-DENY","name":"Denied Material","cost_price":1,"unit":"g"}' >/dev/null
http_auth_expect POST "$INTERNAL_BASE_URL/api/v1/restaurant/qs-qr/generate" "$CASHIER_TOKEN" 403 '{}' >/dev/null

echo "== F&B permission smoke: kitchen"
http_auth_expect GET "$INTERNAL_BASE_URL/api/v1/restaurant/kitchen" "$KITCHEN_TOKEN" 200 >/dev/null
http_auth_expect POST "$INTERNAL_BASE_URL/api/v1/restaurant/tables" "$KITCHEN_TOKEN" 403 "{\"name\":\"PERM-KITCHEN-DENY\",\"capacity\":2,\"table_type\":\"dine_in\"}" >/dev/null
http_auth_expect POST "$INTERNAL_BASE_URL/api/v1/restaurant/raw-materials" "$KITCHEN_TOKEN" 403 '{"sku":"PERM-KITCHEN-DENY","name":"Denied Material","cost_price":1,"unit":"g"}' >/dev/null
http_auth_expect POST "$INTERNAL_BASE_URL/api/v1/restaurant/qs-qr/generate" "$KITCHEN_TOKEN" 403 '{}' >/dev/null

echo "== F&B permission smoke: recipe/cost"
RAW_SKU="PERM-RAW-$(date +%s)"
http_auth_expect POST "$INTERNAL_BASE_URL/api/v1/restaurant/raw-materials" "$RECIPE_TOKEN" 201 "{\"sku\":\"$RAW_SKU\",\"name\":\"Permission Raw Material\",\"cost_price\":1.23,\"unit\":\"g\"}" >/dev/null
http_auth_expect GET "$INTERNAL_BASE_URL/api/v1/restaurant/reports/ingredients?branch_id=$BRANCH_ID&date_from=$TODAY&date_to=$TODAY" "$RECIPE_TOKEN" 200 >/dev/null
http_auth_expect GET "$INTERNAL_BASE_URL/api/v1/restaurant/kitchen" "$RECIPE_TOKEN" 403 >/dev/null
http_auth_expect POST "$INTERNAL_BASE_URL/api/v1/restaurant/tables" "$RECIPE_TOKEN" 403 "{\"name\":\"PERM-RECIPE-DENY\",\"capacity\":2,\"table_type\":\"dine_in\"}" >/dev/null

echo "== F&B permission smoke: manager"
http_auth_expect GET "$INTERNAL_BASE_URL/api/v1/restaurant/kitchen" "$MANAGER_TOKEN" 200 >/dev/null
http_auth_expect POST "$INTERNAL_BASE_URL/api/v1/restaurant/qs-qr/generate" "$MANAGER_TOKEN" 200 '{}' >/dev/null
http_auth_expect GET "$INTERNAL_BASE_URL/api/v1/restaurant/reports/ingredients?branch_id=$BRANCH_ID&date_from=$TODAY&date_to=$TODAY" "$MANAGER_TOKEN" 200 >/dev/null

echo "PASS: F&B permission smoke OK company=$COMPANY_ID branch=$BRANCH_ID raw_sku=$RAW_SKU"
