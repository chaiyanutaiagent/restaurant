from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from urllib.parse import parse_qs, urlparse
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.device import DeviceRegistration
from app.models.restaurant import Brand, BrandBranch
from app.models.role import Permission, Role
from app.models.settings import BranchSettings
from app.models.user import User, UserBranch
from app.utils.create_superuser import DEFAULT_COMPANY_ID
from app.utils.security import hash_password, verify_password


DATABASE_PREFIX = "restaurant_p3_device_"
PASSWORD = "DeviceSmoke123!"


def expect(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    if expected >= 400:
        return response.json()
    return response.json()["data"]


async def prepare() -> dict[str, str]:
    configured_database = os.environ.get("P3_DEVICE_DATABASE_NAME", "")
    if not configured_database.startswith(DATABASE_PREFIX):
        raise RuntimeError("Phase 3 device smoke refuses to write a non-device database")

    async with AsyncSessionLocal() as db:
        actual_database = await db.scalar(func.current_database())
        if actual_database != configured_database:
            raise RuntimeError(
                f"Phase 3 device database mismatch: {actual_database} != {configured_database}"
            )

        marker = uuid.uuid4().hex[:8]
        branch_a = Branch(
            company_id=DEFAULT_COMPANY_ID,
            code=f"P3A-{marker}"[:20],
            name=f"P3 Device Branch A {marker}",
            is_active=True,
        )
        branch_b = Branch(
            company_id=DEFAULT_COMPANY_ID,
            code=f"P3B-{marker}"[:20],
            name=f"P3 Device Branch B {marker}",
            is_active=True,
        )
        db.add_all([branch_a, branch_b])
        await db.flush()
        brand = Brand(
            company_id=DEFAULT_COMPANY_ID,
            slug=f"p3-device-{marker}",
            name=f"P3 Device Brand {marker}",
            business_type="restaurant",
            is_active=True,
        )
        db.add(brand)
        await db.flush()
        db.add_all(
            [
                BrandBranch(
                    company_id=DEFAULT_COMPANY_ID,
                    brand_id=brand.id,
                    branch_id=branch_a.id,
                    is_active=True,
                ),
                BrandBranch(
                    company_id=DEFAULT_COMPANY_ID,
                    brand_id=brand.id,
                    branch_id=branch_b.id,
                    is_active=True,
                ),
                BranchSettings(
                    company_id=DEFAULT_COMPANY_ID,
                    branch_id=branch_a.id,
                    fb_kitchen_stations=["Main", "Bar"],
                ),
                BranchSettings(
                    company_id=DEFAULT_COMPANY_ID,
                    branch_id=branch_b.id,
                    fb_kitchen_stations=["Grill"],
                ),
            ]
        )

        permission_rows = (
            await db.scalars(
                select(Permission).where(
                    Permission.code.in_(["system.device.view", "system.device.manage"])
                )
            )
        ).all()
        if {row.code for row in permission_rows} != {
            "system.device.view",
            "system.device.manage",
        }:
            raise RuntimeError("Device permission seed is incomplete")
        role = Role(
            company_id=DEFAULT_COMPANY_ID,
            name=f"P3 Device Manager {marker}",
            is_branch_assignable=True,
            allowed_scope_types=["branch"],
        )
        role.permissions = list(permission_rows)
        db.add(role)
        await db.flush()
        manager = User(
            company_id=DEFAULT_COMPANY_ID,
            username=f"p3-device-manager-{marker}",
            hashed_password=hash_password(PASSWORD),
            display_name="P3 Device Manager",
            is_active=True,
            is_superuser=False,
        )
        db.add(manager)
        await db.flush()
        db.add(
            UserBranch(
                user_id=manager.id,
                branch_id=branch_a.id,
                brand_id=brand.id,
                business_type="restaurant",
                target_database="restaurant",
                role_id=role.id,
                is_default=True,
            )
        )
        foreign_device = DeviceRegistration(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=branch_b.id,
            device_code=f"P-{uuid.uuid4().hex[:10].upper()}",
            name="Other Branch Pickup",
            device_type="pickup",
            pairing_pin_hash=hash_password("593824"),
            pairing_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            created_by=manager.id,
        )
        db.add(foreign_device)
        await db.commit()
        return {
            "company_id": str(DEFAULT_COMPANY_ID),
            "brand_id": str(brand.id),
            "branch_a_id": str(branch_a.id),
            "branch_b_id": str(branch_b.id),
            "manager_id": str(manager.id),
            "manager_username": manager.username,
            "foreign_device_id": str(foreign_device.id),
        }


async def verify_pairing_hash(device_id: str, pairing_pin: str) -> None:
    async with AsyncSessionLocal() as db:
        device = await db.get(DeviceRegistration, uuid.UUID(device_id))
        if (
            device is None
            or device.pairing_pin_hash is None
            or device.pairing_pin_hash == pairing_pin
            or not verify_password(pairing_pin, device.pairing_pin_hash)
        ):
            raise RuntimeError("Pairing PIN is not stored as a one-way hash")


async def expire_pairing(device_id: str) -> None:
    async with AsyncSessionLocal() as db:
        device = await db.get(DeviceRegistration, uuid.UUID(device_id))
        if device is None:
            raise RuntimeError("Expiring device was not found")
        device.pairing_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()


async def age_last_seen(device_id: str) -> None:
    async with AsyncSessionLocal() as db:
        device = await db.get(DeviceRegistration, uuid.UUID(device_id))
        if device is None:
            raise RuntimeError("Heartbeat device was not found")
        device.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        await db.commit()


async def verify_recent_last_seen(device_id: str) -> None:
    async with AsyncSessionLocal() as db:
        device = await db.get(DeviceRegistration, uuid.UUID(device_id))
        if (
            device is None
            or device.last_seen_at is None
            or device.last_seen_at <= datetime.now(timezone.utc) - timedelta(minutes=1)
        ):
            raise RuntimeError("Device heartbeat did not refresh last-seen evidence")


async def verify_evidence(context: dict[str, str], device_id: str) -> None:
    async with AsyncSessionLocal() as db:
        device = await db.get(DeviceRegistration, uuid.UUID(device_id))
        if (
            device is None
            or device.credential_version != 4
            or device.revoked_at is None
            or device.revoked_by != uuid.UUID(context["manager_id"])
            or device.revocation_reason != "tablet retired"
            or device.pairing_pin_hash is not None
            or device.last_seen_at is None
        ):
            raise RuntimeError(f"Final device lifecycle evidence is incomplete: {device}")

        audit_rows = (
            await db.scalars(
                select(AuditLog)
                .where(
                    AuditLog.resource == "DeviceRegistration",
                    AuditLog.resource_id == device_id,
                )
                .order_by(AuditLog.created_at.asc())
            )
        ).all()
        expected_actions = [
            "system.device.create",
            "system.device.pairing.rotate",
            "device.pair",
            "system.device.pairing.rotate",
            "device.pair",
            "system.device.revoke",
        ]
        if [row.action for row in audit_rows] != expected_actions:
            raise RuntimeError(f"Unexpected device audit actions: {audit_rows}")
        manager_id = uuid.UUID(context["manager_id"])
        branch_id = uuid.UUID(context["branch_a_id"])
        for row in audit_rows:
            expected_actor = None if row.action == "device.pair" else manager_id
            if (
                row.user_id != expected_actor
                or row.company_id != DEFAULT_COMPANY_ID
                or row.branch_id != branch_id
                or not row.new_value.get("reason")
                or {"pairing_pin", "pairing_pin_hash"}.intersection(row.new_value)
            ):
                raise RuntimeError(f"Device audit evidence escaped policy: {row.action}")


def pair_payload(context: dict[str, str], provision: dict, pairing_pin: str) -> dict[str, str]:
    return {
        "company_id": context["company_id"],
        "device_code": provision["device"]["device_code"],
        "pairing_pin": pairing_pin,
    }


def run() -> None:
    if settings.identity_database != "legacy" or settings.restaurant_service_database != "legacy":
        raise RuntimeError("Phase 3 device smoke must exercise rollback-safe legacy defaults")

    with TestClient(app) as client:
        if client.portal is None:
            raise RuntimeError("TestClient portal is unavailable")
        context = client.portal.call(prepare)
        login = expect(
            client.post(
                "/api/v1/auth/login",
                json={
                    "company_id": context["company_id"],
                    "username": context["manager_username"],
                    "password": PASSWORD,
                    "branch_id": context["branch_a_id"],
                },
            ),
            200,
            "manager login",
        )
        headers = {"Authorization": f"Bearer {login['access_token']}"}

        expect(
            client.post(
                "/api/v1/system/devices",
                headers=headers,
                json={
                    "name": "Cross Branch Counter",
                    "device_type": "counter",
                    "branch_id": context["branch_b_id"],
                    "reason": "must not cross Branch",
                },
            ),
            404,
            "cross-Branch registration",
        )
        expect(
            client.post(
                "/api/v1/system/devices",
                headers=headers,
                json={
                    "name": "Unknown Kitchen",
                    "device_type": "kitchen",
                    "branch_id": context["branch_a_id"],
                    "station_key": "Not Configured",
                    "reason": "invalid station",
                },
            ),
            400,
            "invalid Kitchen Station",
        )

        provision = expect(
            client.post(
                "/api/v1/system/devices",
                headers=headers,
                json={
                    "name": "Main Kitchen Tablet",
                    "device_type": "kitchen",
                    "branch_id": context["branch_a_id"],
                    "station_key": " main ",
                    "reason": "install kitchen tablet",
                },
            ),
            201,
            "register Kitchen device",
        )
        device_id = provision["device"]["id"]
        if (
            provision["device"]["station_key"] != "Main"
            or provision["device"]["status"] != "pending_pairing"
            or len(provision["pairing_pin"]) != 6
        ):
            raise RuntimeError(f"Device provisioning result is invalid: {provision}")
        parsed_qr = urlparse(provision["pairing_qr_payload"])
        qr_query = parse_qs(parsed_qr.query)
        if (
            parsed_qr.scheme != "restaurant-pos"
            or parsed_qr.netloc != "pair"
            or set(qr_query) != {"company_id", "device_code", "pin"}
            or qr_query["company_id"] != [context["company_id"]]
            or qr_query["device_code"] != [provision["device"]["device_code"]]
            or qr_query["pin"] != [provision["pairing_pin"]]
        ):
            raise RuntimeError(f"Pairing QR payload escaped one-time credential scope: {parsed_qr}")
        client.portal.call(verify_pairing_hash, device_id, provision["pairing_pin"])

        devices = expect(
            client.get("/api/v1/system/devices", headers=headers),
            200,
            "Branch device list",
        )
        listed_ids = {row["id"] for row in devices}
        if device_id not in listed_ids or context["foreign_device_id"] in listed_ids:
            raise RuntimeError(f"Branch device list escaped scope: {devices}")

        wrong_payload = pair_payload(context, provision, "000000")
        if wrong_payload["pairing_pin"] == provision["pairing_pin"]:
            wrong_payload["pairing_pin"] = "999999"
        for attempt in range(1, settings.device_pairing_max_failed_attempts + 1):
            expect(
                client.post("/api/v1/device-auth/pair", json=wrong_payload),
                429 if attempt == settings.device_pairing_max_failed_attempts else 401,
                f"wrong pairing attempt {attempt}",
            )
        expect(
            client.post(
                "/api/v1/device-auth/pair",
                json=pair_payload(context, provision, provision["pairing_pin"]),
            ),
            429,
            "locked pairing",
        )

        rotated = expect(
            client.post(
                f"/api/v1/system/devices/{device_id}/pairing-code",
                headers=headers,
                json={"reason": "unlock and reissue"},
            ),
            200,
            "rotate pairing code after lockout",
        )
        if rotated["device"]["credential_version"] != 2:
            raise RuntimeError(f"Pairing rotation did not bump credential version: {rotated}")
        paired = expect(
            client.post(
                "/api/v1/device-auth/pair",
                json=pair_payload(context, rotated, rotated["pairing_pin"]),
            ),
            200,
            "pair Kitchen device",
        )
        device_headers = {"Authorization": f"Bearer {paired['access_token']}"}
        client.portal.call(age_last_seen, device_id)
        device_me = expect(
            client.get("/api/v1/device-auth/me", headers=device_headers),
            200,
            "device self context",
        )
        if (
            device_me["branch_id"] != context["branch_a_id"]
            or device_me["brand_id"] != context["brand_id"]
            or device_me["station_key"] != "Main"
            or device_me["device_type"] != "kitchen"
            or device_me["target_database"] != "restaurant"
        ):
            raise RuntimeError(f"Device self context is not server-bound: {device_me}")
        client.portal.call(verify_recent_last_seen, device_id)
        expect(
            client.get("/api/v1/device-auth/me", headers=headers),
            401,
            "user token rejected by device endpoint",
        )
        expect(
            client.post(
                "/api/v1/device-auth/pair",
                json=pair_payload(context, rotated, rotated["pairing_pin"]),
            ),
            401,
            "single-use pairing PIN",
        )

        rotated_again = expect(
            client.post(
                f"/api/v1/system/devices/{device_id}/pairing-code",
                headers=headers,
                json={"reason": "replace tablet credential"},
            ),
            200,
            "rotate active credential",
        )
        expect(
            client.get("/api/v1/device-auth/me", headers=device_headers),
            401,
            "old token after credential rotation",
        )
        paired_again = expect(
            client.post(
                "/api/v1/device-auth/pair",
                json=pair_payload(context, rotated_again, rotated_again["pairing_pin"]),
            ),
            200,
            "pair rotated credential",
        )
        current_device_headers = {
            "Authorization": f"Bearer {paired_again['access_token']}"
        }
        expect(
            client.get("/api/v1/device-auth/me", headers=current_device_headers),
            200,
            "rotated device heartbeat",
        )

        expired = expect(
            client.post(
                "/api/v1/system/devices",
                headers=headers,
                json={
                    "name": "Expired Pickup Display",
                    "device_type": "pickup",
                    "branch_id": context["branch_a_id"],
                    "reason": "expiry test",
                },
            ),
            201,
            "register expiring device",
        )
        client.portal.call(expire_pairing, expired["device"]["id"])
        expect(
            client.post(
                "/api/v1/device-auth/pair",
                json=pair_payload(context, expired, expired["pairing_pin"]),
            ),
            401,
            "expired pairing PIN",
        )
        cross_tenant = pair_payload(context, expired, expired["pairing_pin"])
        cross_tenant["company_id"] = str(uuid.uuid4())
        expect(
            client.post("/api/v1/device-auth/pair", json=cross_tenant),
            401,
            "cross-tenant pairing",
        )

        revoked = expect(
            client.post(
                f"/api/v1/system/devices/{device_id}/revoke",
                headers=headers,
                json={"reason": "tablet retired"},
            ),
            200,
            "revoke device",
        )
        if revoked["status"] != "revoked" or revoked["credential_version"] != 4:
            raise RuntimeError(f"Revocation result is incomplete: {revoked}")
        expect(
            client.get("/api/v1/device-auth/me", headers=current_device_headers),
            401,
            "revoked token",
        )
        expect(
            client.post(
                "/api/v1/device-auth/pair",
                json=pair_payload(context, rotated_again, rotated_again["pairing_pin"]),
            ),
            401,
            "revoked device pairing",
        )
        client.portal.call(verify_evidence, context, device_id)

    print(
        "p3_device_pairing_api=ok "
        "branch_scope=true station_scope=true pin_hash_expiry_lockout=true "
        "single_use=true rotation=true revoke=true last_seen=true audit=true"
    )


if __name__ == "__main__":
    run()
