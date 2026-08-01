from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.restaurant import (
    Brand,
    BrandBranch,
    DiningOrder,
    DiningOrderItem,
    DiningSession,
    KitchenTicket,
)
from app.models.role import Permission, Role
from app.models.settings import BranchSettings
from app.models.stock import StockLocation
from app.models.user import User, UserBranch
from app.utils.create_superuser import DEFAULT_COMPANY_ID
from app.utils.security import hash_password


DATABASE_PREFIX = "restaurant_p3_workspace_"
PASSWORD = "DeviceWorkspace123!"


def expect(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    if expected >= 400:
        return response.json()
    return response.json()["data"]


async def prepare() -> dict[str, str]:
    configured_database = os.environ.get("P3_WORKSPACE_DATABASE_NAME", "")
    if not configured_database.startswith(DATABASE_PREFIX):
        raise RuntimeError("Phase 3 workspace smoke refuses to write a non-workspace database")

    async with AsyncSessionLocal() as db:
        actual_database = await db.scalar(func.current_database())
        if actual_database != configured_database:
            raise RuntimeError(
                f"Phase 3 workspace database mismatch: {actual_database} != {configured_database}"
            )

        marker = uuid.uuid4().hex[:8]
        branch_a = Branch(
            company_id=DEFAULT_COMPANY_ID,
            code=f"P3WA-{marker}"[:20],
            name=f"P3 Workspace Branch A {marker}",
            is_active=True,
        )
        branch_b = Branch(
            company_id=DEFAULT_COMPANY_ID,
            code=f"P3WB-{marker}"[:20],
            name=f"P3 Workspace Branch B {marker}",
            is_active=True,
        )
        db.add_all([branch_a, branch_b])
        await db.flush()
        brand = Brand(
            company_id=DEFAULT_COMPANY_ID,
            slug=f"p3-workspace-{marker}",
            name=f"P3 Workspace Brand {marker}",
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
                    fb_queue_prefix="A-",
                    fb_kitchen_stations=["Main", "Bar"],
                ),
                BranchSettings(
                    company_id=DEFAULT_COMPANY_ID,
                    branch_id=branch_b.id,
                    fb_queue_prefix="B-",
                    fb_kitchen_stations=["Main"],
                ),
            ]
        )

        permissions = list(
            (
                await db.scalars(
                    select(Permission).where(
                        Permission.code.in_([
                            "system.device.view",
                            "system.device.manage",
                            "fb.order.create",
                        ])
                    )
                )
            ).all()
        )
        if {permission.code for permission in permissions} != {
            "system.device.view",
            "system.device.manage",
            "fb.order.create",
        }:
            raise RuntimeError("Device/staff permissions are not seeded")
        role = Role(
            company_id=DEFAULT_COMPANY_ID,
            name=f"P3 Workspace Manager {marker}",
            is_branch_assignable=True,
            allowed_scope_types=["branch"],
        )
        role.permissions = permissions
        manager = User(
            company_id=DEFAULT_COMPANY_ID,
            username=f"p3-workspace-manager-{marker}",
            hashed_password=hash_password(PASSWORD),
            display_name="P3 Workspace Manager",
            is_active=True,
            is_superuser=False,
        )
        db.add_all([role, manager])
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
        location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=branch_a.id,
            code=f"P3W-{marker}"[:20],
            name=f"P3 Workspace Counter {marker}",
            is_active=True,
        )
        db.add(location)

        product_id = await db.scalar(
            select(DiningOrderItem.product_id).where(DiningOrderItem.product_id.isnot(None)).limit(1)
        )
        if product_id is None:
            from app.models.product import Product

            product_id = await db.scalar(
                select(Product.id).where(
                    Product.company_id == DEFAULT_COMPANY_ID,
                    Product.deleted_at.is_(None),
                ).limit(1)
            )
        if product_id is None:
            raise RuntimeError("Canonical product fixture is missing")

        async def add_ticket(
            branch_id: uuid.UUID,
            *,
            station: str,
            status: str,
            queue_number: int,
            product_name: str,
        ) -> tuple[DiningSession, KitchenTicket]:
            session = DiningSession(
                company_id=DEFAULT_COMPANY_ID,
                branch_id=branch_id,
                queue_number=queue_number,
                status="open",
            )
            db.add(session)
            await db.flush()
            order = DiningOrder(
                company_id=DEFAULT_COMPANY_ID,
                branch_id=branch_id,
                session_id=session.id,
                order_number=f"P3W-{marker}-{queue_number}-{station}",
                status="pending",
            )
            db.add(order)
            await db.flush()
            item = DiningOrderItem(
                order_id=order.id,
                product_id=product_id,
                product_name=product_name,
                qty=1,
                unit_price=0,
                station=station,
                status=status,
            )
            db.add(item)
            await db.flush()
            ticket = KitchenTicket(
                company_id=DEFAULT_COMPANY_ID,
                branch_id=branch_id,
                session_id=session.id,
                order_item_id=item.id,
                product_name=product_name,
                qty=1,
                station=station,
                queue_number=queue_number,
                status=status,
                done_at=datetime.now(timezone.utc) if status == "done" else None,
            )
            db.add(ticket)
            await db.flush()
            return session, ticket

        _, main_ticket = await add_ticket(
            branch_a.id,
            station="Main",
            status="pending",
            queue_number=41,
            product_name="Main Kitchen Item",
        )
        _, bar_ticket = await add_ticket(
            branch_a.id,
            station="Bar",
            status="pending",
            queue_number=42,
            product_name="Bar Kitchen Item",
        )
        pickup_session, _ = await add_ticket(
            branch_a.id,
            station="Main",
            status="done",
            queue_number=43,
            product_name="Ready Branch A Item",
        )
        foreign_pickup_session, _ = await add_ticket(
            branch_b.id,
            station="Main",
            status="done",
            queue_number=99,
            product_name="Ready Branch B Item",
        )
        await db.commit()
        return {
            "company_id": str(DEFAULT_COMPANY_ID),
            "branch_a_id": str(branch_a.id),
            "branch_b_id": str(branch_b.id),
            "manager_id": str(manager.id),
            "manager_username": manager.username,
            "location_id": str(location.id),
            "main_ticket_id": str(main_ticket.id),
            "bar_ticket_id": str(bar_ticket.id),
            "pickup_session_id": str(pickup_session.id),
            "foreign_pickup_session_id": str(foreign_pickup_session.id),
        }


async def verify_device_audit(
    counter_device_id: str,
    counter_device_code: str,
    manager_id: str,
    branch_id: str,
    staff_shift_id: str,
    kitchen_device_id: str,
    pickup_device_id: str,
    ticket_id: str,
    session_id: str,
) -> None:
    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.scalars(
                    select(AuditLog)
                    .where(
                        AuditLog.action.in_([
                            "restaurant.staff_shift.open",
                            "pos.shift.close",
                            "device.kitchen.ticket.update",
                            "device.pickup.queue.serve",
                        ])
                    )
                    .order_by(AuditLog.created_at, AuditLog.id)
                )
            ).all()
        )
        kitchen_rows = [row for row in rows if row.resource_id == ticket_id]
        pickup_rows = [row for row in rows if row.resource_id == session_id]
        if [row.new_value.get("status") for row in kitchen_rows] != ["cooking", "done"]:
            raise RuntimeError(f"Kitchen device audit is incomplete: {kitchen_rows}")
        if len(pickup_rows) != 1 or pickup_rows[0].new_value.get("status") != "served":
            raise RuntimeError(f"Pickup device audit is incomplete: {pickup_rows}")
        if any(row.user_id is not None for row in kitchen_rows + pickup_rows):
            raise RuntimeError("Device operational audit must not impersonate a user")
        if any(
            row.new_value.get("device_id") != kitchen_device_id for row in kitchen_rows
        ) or pickup_rows[0].new_value.get("device_id") != pickup_device_id:
            raise RuntimeError("Operational audit does not identify the device actor")

        staff_rows = [row for row in rows if row.resource_id == staff_shift_id]
        if [row.action for row in staff_rows] != [
            "restaurant.staff_shift.open",
            "pos.shift.close",
        ]:
            raise RuntimeError(f"Counter staff handover audit is incomplete: {staff_rows}")
        expected_manager = uuid.UUID(manager_id)
        expected_branch = uuid.UUID(branch_id)
        for row in staff_rows:
            evidence = {
                "action": row.action,
                "user_id": str(row.user_id) if row.user_id else None,
                "branch_id": str(row.branch_id) if row.branch_id else None,
                "new_value": row.new_value,
                "ip_address": row.ip_address,
                "user_agent": row.user_agent,
            }
            if (
                row.user_id != expected_manager
                or row.branch_id != expected_branch
                or row.new_value.get("device_id") != counter_device_id
                or row.new_value.get("device_code") != counter_device_code
                # Starlette's in-process TestClient may omit the network peer.
                # A real ASGI server supplies request.client.host; if the test
                # transport does expose a peer, require a non-empty value.
                or (row.ip_address is not None and not row.ip_address.strip())
                or row.user_agent != "Codex-P3-Gate/1.0"
            ):
                raise RuntimeError(
                    "Counter staff/device audit evidence is incomplete: "
                    f"actual={evidence} expected_user_id={manager_id} "
                    f"expected_branch_id={branch_id} "
                    f"expected_device_id={counter_device_id} "
                    f"expected_device_code={counter_device_code}"
                )


def pair_device(
    client: TestClient,
    headers: dict[str, str],
    context: dict[str, str],
    data: dict,
) -> tuple[str, str, str]:
    provision = expect(
        client.post("/api/v1/system/devices", headers=headers, json=data),
        201,
        f"create {data['device_type']} device",
    )
    paired = expect(
        client.post(
            "/api/v1/device-auth/pair",
            json={
                "company_id": context["company_id"],
                "device_code": provision["device"]["device_code"],
                "pairing_pin": provision["pairing_pin"],
            },
        ),
        200,
        f"pair {data['device_type']} device",
    )
    return (
        provision["device"]["id"],
        paired["access_token"],
        provision["device"]["device_code"],
    )


def run() -> None:
    if settings.identity_database != "legacy" or settings.restaurant_service_database != "legacy":
        raise RuntimeError("Phase 3 workspace smoke must exercise rollback-safe legacy defaults")

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
        manager_headers = {"Authorization": f"Bearer {login['access_token']}"}
        counter_id, counter_token, counter_code = pair_device(
            client,
            manager_headers,
            context,
            {
                "name": "Counter Tablet",
                "device_type": "counter",
                "branch_id": context["branch_a_id"],
                "reason": "workspace smoke",
            },
        )
        kitchen_id, kitchen_token, _ = pair_device(
            client,
            manager_headers,
            context,
            {
                "name": "Main Kitchen Tablet",
                "device_type": "kitchen",
                "branch_id": context["branch_a_id"],
                "station_key": "Main",
                "reason": "workspace smoke",
            },
        )
        pickup_id, pickup_token, _ = pair_device(
            client,
            manager_headers,
            context,
            {
                "name": "Pickup Tablet",
                "device_type": "pickup",
                "branch_id": context["branch_a_id"],
                "reason": "workspace smoke",
            },
        )
        counter_headers = {"Authorization": f"Bearer {counter_token}"}
        kitchen_headers = {"Authorization": f"Bearer {kitchen_token}"}
        pickup_headers = {"Authorization": f"Bearer {pickup_token}"}

        counter = expect(
            client.get("/api/v1/device-workspaces/counter/bootstrap", headers=counter_headers),
            200,
            "counter bootstrap",
        )
        if (
            counter["branch"]["id"] != context["branch_a_id"]
            or not counter["requires_staff_login"]
            or "pos_handoff" not in counter["capabilities"]
        ):
            raise RuntimeError(f"Counter workspace is not server-bound: {counter}")
        expect(
            client.get("/api/v1/device-workspaces/kitchen/tickets", headers=counter_headers),
            403,
            "counter token at Kitchen workspace",
        )
        expect(
            client.get("/api/v1/device-workspaces/counter/bootstrap", headers=manager_headers),
            401,
            "user token at Counter workspace",
        )

        staff_counter_headers = {
            **manager_headers,
            "X-Device-Authorization": f"Bearer {counter_token}",
            "User-Agent": "Codex-P3-Gate/1.0",
        }
        menu = expect(
            client.get("/api/v1/restaurant/wap/menu", headers=staff_counter_headers),
            200,
            "Counter staff menu and shift bootstrap",
        )
        if (
            not menu["shift_id"]
            or menu["location_id"] != context["location_id"]
            or menu["offline_device_id"] != counter_id
        ):
            raise RuntimeError(f"Counter staff shift is not bound to the device: {menu}")
        expect(
            client.post(
                "/api/v1/restaurant/wap/staff-shift/handover",
                headers=manager_headers,
                json={"closing_cash": "0.00", "note": "missing device gate"},
            ),
            403,
            "handover without Counter device",
        )
        handover = expect(
            client.post(
                "/api/v1/restaurant/wap/staff-shift/handover",
                headers=staff_counter_headers,
                json={"closing_cash": "0.00", "note": "phase 3 gate handover"},
            ),
            200,
            "Counter staff handover",
        )
        if (
            handover["id"] != menu["shift_id"]
            or handover["status"] != "closed"
            or handover["user_id"] != context["manager_id"]
            or handover["branch_id"] != context["branch_a_id"]
        ):
            raise RuntimeError(f"Counter staff handover result is invalid: {handover}")
        expect(
            client.post(
                "/api/v1/restaurant/wap/staff-shift/handover",
                headers=staff_counter_headers,
                json={"closing_cash": "0.00", "note": "closed shift replay"},
            ),
            404,
            "handover replay after shift close",
        )

        kitchen = expect(
            client.get("/api/v1/device-workspaces/kitchen/bootstrap", headers=kitchen_headers),
            200,
            "kitchen bootstrap",
        )
        if kitchen["station_key"] != "Main" or kitchen["branch"]["id"] != context["branch_a_id"]:
            raise RuntimeError(f"Kitchen bootstrap escaped Branch/Station: {kitchen}")
        tickets = expect(
            client.get("/api/v1/device-workspaces/kitchen/tickets", headers=kitchen_headers),
            200,
            "station-locked Kitchen tickets",
        )
        listed_ids = {ticket["id"] for ticket in tickets}
        if context["main_ticket_id"] not in listed_ids or context["bar_ticket_id"] in listed_ids:
            raise RuntimeError(f"Kitchen ticket list escaped Station: {tickets}")
        expect(
            client.patch(
                f"/api/v1/device-workspaces/kitchen/tickets/{context['bar_ticket_id']}",
                headers=kitchen_headers,
                json={"status": "cooking"},
            ),
            404,
            "cross-Station Kitchen mutation",
        )
        for next_status in ("cooking", "done"):
            expect(
                client.patch(
                    f"/api/v1/device-workspaces/kitchen/tickets/{context['main_ticket_id']}",
                    headers=kitchen_headers,
                    json={"status": next_status},
                ),
                200,
                f"Kitchen transition to {next_status}",
            )
        expect(
            client.patch(
                f"/api/v1/device-workspaces/kitchen/tickets/{context['main_ticket_id']}",
                headers=kitchen_headers,
                json={"status": "served"},
            ),
            400,
            "Kitchen device cannot serve",
        )

        pickup = expect(
            client.get("/api/v1/device-workspaces/pickup/bootstrap", headers=pickup_headers),
            200,
            "pickup bootstrap",
        )
        if pickup["queue_prefix"] != "A-" or pickup["branch"]["id"] != context["branch_a_id"]:
            raise RuntimeError(f"Pickup bootstrap escaped Branch settings: {pickup}")
        queues = expect(
            client.get("/api/v1/device-workspaces/pickup/queue", headers=pickup_headers),
            200,
            "Branch-locked Pickup queue",
        )
        queue_ids = {queue["session_id"] for queue in queues}
        if context["pickup_session_id"] not in queue_ids or context["foreign_pickup_session_id"] in queue_ids:
            raise RuntimeError(f"Pickup queue escaped Branch: {queues}")
        expect(
            client.post(
                f"/api/v1/device-workspaces/pickup/queue/{context['foreign_pickup_session_id']}/served",
                headers=pickup_headers,
            ),
            400,
            "cross-Branch Pickup mutation",
        )
        expect(
            client.post(
                f"/api/v1/device-workspaces/pickup/queue/{context['pickup_session_id']}/served",
                headers=pickup_headers,
            ),
            200,
            "Pickup serve",
        )
        expect(
            client.get("/api/v1/device-workspaces/pickup/queue", headers=kitchen_headers),
            403,
            "Kitchen token at Pickup workspace",
        )

        client.portal.call(
            verify_device_audit,
            counter_id,
            counter_code,
            context["manager_id"],
            context["branch_a_id"],
            menu["shift_id"],
            kitchen_id,
            pickup_id,
            context["main_ticket_id"],
            context["pickup_session_id"],
        )
        expect(
            client.post(
                f"/api/v1/system/devices/{kitchen_id}/revoke",
                headers=manager_headers,
                json={"reason": "workspace revoke test"},
            ),
            200,
            "revoke Kitchen device",
        )
        expect(
            client.get("/api/v1/device-workspaces/kitchen/tickets", headers=kitchen_headers),
            401,
            "revoked device workspace",
        )
        if not counter_id or not pickup_id:
            raise RuntimeError("Device identifiers were not created")

    print(
        "p3_device_workspaces_api=ok "
        "counter_staff_gate=true kitchen_station_scope=true pickup_branch_scope=true "
        "type_guard=true revoke=true operational_audit=true "
        "staff_handover=true staff_device_audit=true"
    )


if __name__ == "__main__":
    run()
