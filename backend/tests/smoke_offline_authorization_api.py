from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app
from app.models.branch import Branch
from app.models.restaurant import Brand, BrandBranch
from app.models.role import Permission, Role
from app.models.settings import BranchSettings
from app.models.stock import StockLocation
from app.models.user import User, UserBranch
from app.utils.create_superuser import DEFAULT_COMPANY_ID
from app.utils.security import decode_token, hash_password


DATABASE_PREFIX = "restaurant_p3_offline_"
PASSWORD = "OfflineAuthorization123!"


def expect(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    if expected >= 400:
        return response.json()
    return response.json()["data"]


async def prepare() -> dict[str, str]:
    configured_database = os.environ.get("P3_OFFLINE_DATABASE_NAME", "")
    if not configured_database.startswith(DATABASE_PREFIX):
        raise RuntimeError("Phase 3 offline smoke refuses to write a non-offline database")
    async with AsyncSessionLocal() as db:
        actual_database = await db.scalar(func.current_database())
        if actual_database != configured_database:
            raise RuntimeError(
                f"Phase 3 offline database mismatch: {actual_database} != {configured_database}"
            )
        marker = uuid.uuid4().hex[:8]
        branch = Branch(
            company_id=DEFAULT_COMPANY_ID,
            code=f"P3O-{marker}"[:20],
            name=f"P3 Offline Branch {marker}",
            is_active=True,
        )
        db.add(branch)
        await db.flush()
        db.add(StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=branch.id,
            code="STORE",
            name="Store Stock",
            is_active=True,
        ))
        brand = Brand(
            company_id=DEFAULT_COMPANY_ID,
            slug=f"p3-offline-{marker}",
            name=f"P3 Offline Brand {marker}",
            business_type="restaurant",
            is_active=True,
        )
        db.add(brand)
        await db.flush()
        db.add_all([
            BrandBranch(
                company_id=DEFAULT_COMPANY_ID,
                brand_id=brand.id,
                branch_id=branch.id,
                is_active=True,
            ),
            BranchSettings(
                company_id=DEFAULT_COMPANY_ID,
                branch_id=branch.id,
                fb_queue_prefix="O-",
                fb_kitchen_stations=["Main"],
            ),
        ])
        permission_rows = list((await db.scalars(
            select(Permission).where(Permission.code.in_([
                "fb.order.create",
                "system.device.view",
                "system.device.manage",
            ]))
        )).all())
        if {row.code for row in permission_rows} != {
            "fb.order.create",
            "system.device.view",
            "system.device.manage",
        }:
            raise RuntimeError("Offline authorization permissions are not seeded")
        role = Role(
            company_id=DEFAULT_COMPANY_ID,
            name=f"P3 Offline Cashier {marker}",
            is_branch_assignable=True,
            allowed_scope_types=["branch"],
        )
        role.permissions = permission_rows
        user = User(
            company_id=DEFAULT_COMPANY_ID,
            username=f"p3-offline-{marker}",
            hashed_password=hash_password(PASSWORD),
            display_name="P3 Offline Cashier",
            is_active=True,
            is_superuser=False,
        )
        db.add_all([role, user])
        await db.flush()
        db.add(UserBranch(
            user_id=user.id,
            branch_id=branch.id,
            brand_id=brand.id,
            business_type="restaurant",
            target_database="restaurant",
            role_id=role.id,
            is_default=True,
        ))
        await db.commit()
        return {
            "company_id": str(DEFAULT_COMPANY_ID),
            "branch_id": str(branch.id),
            "brand_id": str(brand.id),
            "username": user.username,
        }


def pair_device(
    client: TestClient,
    manager_headers: dict[str, str],
    context: dict[str, str],
    *,
    device_type: str,
) -> tuple[str, str]:
    payload = {
        "name": f"Offline {device_type.title()}",
        "device_type": device_type,
        "branch_id": context["branch_id"],
        "reason": "offline authorization smoke",
    }
    if device_type == "kitchen":
        payload["station_key"] = "Main"
    provision = expect(
        client.post("/api/v1/system/devices", headers=manager_headers, json=payload),
        201,
        f"create {device_type} device",
    )
    paired = expect(
        client.post("/api/v1/device-auth/pair", json={
            "company_id": context["company_id"],
            "device_code": provision["device"]["device_code"],
            "pairing_pin": provision["pairing_pin"],
        }),
        200,
        f"pair {device_type} device",
    )
    return provision["device"]["id"], paired["access_token"]


def offline_order(
    client_order_id: str,
    *,
    local_created_at: datetime,
    authorization: str | None,
    policy_version: int | None,
    shift_id: str | None = None,
    location_id: str | None = None,
) -> dict:
    payload = {
        "client_order_id": client_order_id,
        "items": [{"product_id": str(uuid.uuid4()), "qty": 1}],
        "payment_method": "cash",
        "paid_amount": 35,
        "local_created_at": local_created_at.isoformat(),
        "is_offline": True,
    }
    if authorization is not None:
        payload["offline_authorization"] = authorization
    if policy_version is not None:
        payload["offline_policy_version"] = policy_version
    if shift_id is not None:
        payload["shift_id"] = shift_id
    if location_id is not None:
        payload["location_id"] = location_id
    return payload


def run() -> None:
    if settings.identity_database != "legacy" or settings.restaurant_service_database != "legacy":
        raise RuntimeError("Phase 3 offline smoke must exercise rollback-safe legacy defaults")
    with TestClient(app) as client:
        if client.portal is None:
            raise RuntimeError("TestClient portal is unavailable")
        context = client.portal.call(prepare)
        login = expect(
            client.post("/api/v1/auth/login", json={
                "company_id": context["company_id"],
                "username": context["username"],
                "password": PASSWORD,
                "branch_id": context["branch_id"],
            }),
            200,
            "offline cashier login",
        )
        manager_headers = {"Authorization": f"Bearer {login['access_token']}"}
        counter_id, counter_token = pair_device(
            client,
            manager_headers,
            context,
            device_type="counter",
        )
        _, kitchen_token = pair_device(
            client,
            manager_headers,
            context,
            device_type="kitchen",
        )
        counter_headers = {
            **manager_headers,
            "X-Device-Authorization": f"Bearer {counter_token}",
        }
        menu = expect(
            client.get("/api/v1/restaurant/wap/menu", headers=counter_headers),
            200,
            "Counter-bound offline menu bootstrap",
        )
        claims = decode_token(menu["offline_authorization"])
        if (
            menu["offline_policy_version"] != 1
            or menu["offline_device_id"] != counter_id
            or claims["type"] != "offline_sale_authorization"
            or claims["sub"] != login["user"]["id"]
            or claims["company_id"] != context["company_id"]
            or claims["branch_id"] != context["branch_id"]
            or claims["device_id"] != counter_id
            or claims["policy_version"] != 1
        ):
            raise RuntimeError(f"Offline authorization is not server-bound: {menu}")
        expect(
            client.get(
                "/api/v1/restaurant/wap/menu",
                headers={
                    **manager_headers,
                    "X-Device-Authorization": f"Bearer {kitchen_token}",
                },
            ),
            403,
            "Kitchen device cannot bootstrap Counter offline lease",
        )
        user_only_menu = expect(
            client.get("/api/v1/restaurant/wap/menu", headers=manager_headers),
            200,
            "user-only offline menu bootstrap",
        )
        if user_only_menu["offline_device_id"] is not None:
            raise RuntimeError("User-only offline authorization unexpectedly impersonates a device")

        accepted_at = datetime.now(timezone.utc)
        authorization = menu["offline_authorization"]
        sync = expect(
            client.post(
                "/api/v1/restaurant/wap/orders/sync",
                headers=manager_headers,
                json={"orders": [
                    offline_order(
                        "p3-offline-valid",
                        local_created_at=accepted_at,
                        authorization=authorization,
                        policy_version=1,
                        shift_id=menu["shift_id"],
                        location_id=menu["location_id"],
                    ),
                    offline_order(
                        "p3-offline-missing",
                        local_created_at=accepted_at,
                        authorization=None,
                        policy_version=1,
                        shift_id=menu["shift_id"],
                        location_id=menu["location_id"],
                    ),
                    offline_order(
                        "p3-offline-tampered",
                        local_created_at=accepted_at,
                        authorization=authorization,
                        policy_version=1,
                        shift_id=str(uuid.uuid4()),
                        location_id=menu["location_id"],
                    ),
                    offline_order(
                        "p3-offline-legacy",
                        local_created_at=accepted_at,
                        authorization=None,
                        policy_version=None,
                    ),
                ]},
            ),
            200,
            "offline authorization matrix",
        )
        results = {row["client_order_id"]: row for row in sync["results"]}
        if "เมนู" not in (results["p3-offline-valid"]["error"] or ""):
            raise RuntimeError(f"Valid lease did not reach product validation: {results}")
        if "สิทธิ์ขายออฟไลน์ไม่ครบ" not in (results["p3-offline-missing"]["error"] or ""):
            raise RuntimeError(f"Missing current-policy lease was not rejected: {results}")
        if "กะ หรือคลัง" not in (results["p3-offline-tampered"]["error"] or ""):
            raise RuntimeError(f"Tampered lease scope was not rejected: {results}")
        if "เมนู" not in (results["p3-offline-legacy"]["error"] or ""):
            raise RuntimeError(f"Legacy durable queue was not rollout-compatible: {results}")

        expect(
            client.post(
                f"/api/v1/system/devices/{counter_id}/revoke",
                headers=manager_headers,
                json={"reason": "offline revoke boundary"},
            ),
            200,
            "revoke Counter after accepted offline order",
        )
        revoked_matrix = expect(
            client.post(
                "/api/v1/restaurant/wap/orders/sync",
                headers=manager_headers,
                json={"orders": [
                    offline_order(
                        "p3-offline-before-revoke",
                        local_created_at=accepted_at,
                        authorization=authorization,
                        policy_version=1,
                        shift_id=menu["shift_id"],
                        location_id=menu["location_id"],
                    ),
                    offline_order(
                        "p3-offline-after-revoke",
                        local_created_at=datetime.now(timezone.utc) + timedelta(seconds=1),
                        authorization=authorization,
                        policy_version=1,
                        shift_id=menu["shift_id"],
                        location_id=menu["location_id"],
                    ),
                ]},
            ),
            200,
            "offline revoke timing matrix",
        )
        revoked_results = {row["client_order_id"]: row for row in revoked_matrix["results"]}
        if "เมนู" not in (revoked_results["p3-offline-before-revoke"]["error"] or ""):
            raise RuntimeError(f"Pre-revoke paid order was discarded: {revoked_results}")
        if "อุปกรณ์ไม่มีสิทธิ์" not in (revoked_results["p3-offline-after-revoke"]["error"] or ""):
            raise RuntimeError(f"Post-revoke offline order was not isolated: {revoked_results}")

    print(
        "p3_offline_authorization_api=ok "
        "signed_expiry=true staff_branch_shift_location=true counter_device=true "
        "per_order_review=true legacy_queue_preserved=true revoke_timing=true"
    )


if __name__ == "__main__":
    run()
