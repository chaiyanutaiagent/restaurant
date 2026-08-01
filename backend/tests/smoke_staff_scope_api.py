from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
import secrets
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.company import Company
from app.models.pos import CashierShift
from app.models.product import Product
from app.models.restaurant import (
    Brand,
    BrandBranch,
    DiningOrder,
    DiningOrderItem,
    DiningSession,
    KitchenTicket,
)
from app.models.settings import BranchSettings
from app.models.stock import StockLocation
from app.models.user import User
from app.utils.create_superuser import DEFAULT_COMPANY_ID
from app.utils.security import decode_token, hash_password


DATABASE_PREFIXES = ("restaurant_p2_scope_", "restaurant_p2_approval_")
TEST_PASSWORD = f"Aa1!{secrets.token_urlsafe(24)}"


@dataclass(frozen=True)
class ScopeContext:
    company_id: uuid.UUID
    brand_a_id: uuid.UUID
    brand_a_slug: str
    brand_b_id: uuid.UUID
    brand_b_slug: str
    branch_a1_id: uuid.UUID
    branch_a2_id: uuid.UUID
    branch_b1_id: uuid.UUID
    foreign_brand_id: uuid.UUID
    foreign_branch_id: uuid.UUID
    company_user_id: uuid.UUID
    brand_user_id: uuid.UUID
    branch_user_id: uuid.UUID
    kitchen_user_id: uuid.UUID
    multi_user_id: uuid.UUID
    usernames: dict[str, str]
    main_ticket_id: uuid.UUID
    other_ticket_id: uuid.UUID
    branch_a1_shift_id: uuid.UUID
    branch_a2_shift_id: uuid.UUID


def expect(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    if expected >= 400:
        return response.json()
    return response.json()["data"]


async def seed_scope_context() -> ScopeContext:
    configured_database = os.environ.get("P2_SCOPE_DATABASE_NAME", "")
    if not configured_database.startswith(DATABASE_PREFIXES):
        raise RuntimeError(
            "Phase 2 scope smoke refuses to write a non-Phase-2 temporary database"
        )

    async with AsyncSessionLocal() as db:
        actual_database = await db.scalar(func.current_database())
        if actual_database != configured_database:
            raise RuntimeError(
                f"Phase 2 scope database mismatch: {actual_database} != {configured_database}"
            )

        company = await db.scalar(
            select(Company).where(Company.id == DEFAULT_COMPANY_ID, Company.is_active.is_(True))
        )
        brand_a = await db.scalar(
            select(Brand).where(
                Brand.company_id == DEFAULT_COMPANY_ID,
                Brand.business_type == "restaurant",
                Brand.is_active.is_(True),
            )
        )
        branch_a1 = await db.scalar(
            select(Branch)
            .join(BrandBranch, BrandBranch.branch_id == Branch.id)
            .where(
                Branch.company_id == DEFAULT_COMPANY_ID,
                Branch.code == "BKK-01",
                Branch.deleted_at.is_(None),
                BrandBranch.brand_id == brand_a.id if brand_a else False,
                BrandBranch.is_active.is_(True),
            )
        )
        if company is None or brand_a is None or branch_a1 is None:
            raise RuntimeError("Canonical company/Brand/BKK-01 fixture is missing")

        marker = uuid.uuid4().hex[:8]
        branch_a2 = Branch(
            company_id=company.id,
            code=f"S2A-{marker}"[:20],
            name="P2 Scope Brand A Branch",
            is_active=True,
        )
        branch_b1 = Branch(
            company_id=company.id,
            code=f"S2B-{marker}"[:20],
            name="P2 Scope Brand B Branch",
            is_active=True,
        )
        db.add_all([branch_a2, branch_b1])
        await db.flush()
        brand_b = Brand(
            company_id=company.id,
            slug=f"p2-scope-brand-{marker}",
            name="P2 Scope Brand B",
            business_type="restaurant",
            is_active=True,
        )
        db.add(brand_b)
        await db.flush()
        db.add_all(
            [
                BrandBranch(
                    company_id=company.id,
                    brand_id=brand_a.id,
                    branch_id=branch_a2.id,
                    is_active=True,
                ),
                BrandBranch(
                    company_id=company.id,
                    brand_id=brand_b.id,
                    branch_id=branch_b1.id,
                    is_active=True,
                ),
            ]
        )

        settings_a1 = await db.scalar(
            select(BranchSettings).where(BranchSettings.branch_id == branch_a1.id)
        )
        if settings_a1 is None:
            settings_a1 = BranchSettings(company_id=company.id, branch_id=branch_a1.id)
            db.add(settings_a1)
        settings_a1.fb_kitchen_stations = ["Main", "Bar"]
        db.add_all(
            [
                BranchSettings(
                    company_id=company.id,
                    branch_id=branch_a2.id,
                    fb_kitchen_stations=["Grill"],
                ),
                BranchSettings(
                    company_id=company.id,
                    branch_id=branch_b1.id,
                    fb_kitchen_stations=["Foreign Brand Kitchen"],
                ),
            ]
        )

        usernames = {
            key: f"p2_{key}_{marker}"
            for key in ("company", "brand", "branch", "kitchen", "multi")
        }
        users = {
            key: User(
                company_id=company.id,
                username=username,
                hashed_password=hash_password(TEST_PASSWORD),
                display_name=f"P2 Scope {key.title()}",
                is_active=True,
                is_superuser=False,
            )
            for key, username in usernames.items()
        }
        db.add_all(list(users.values()))

        foreign_company = Company(name=f"P2 Foreign Tenant {marker}", is_active=True)
        db.add(foreign_company)
        await db.flush()
        foreign_branch = Branch(
            company_id=foreign_company.id,
            code=f"FOREIGN-{marker}"[:20],
            name="P2 Foreign Branch",
            is_active=True,
        )
        db.add(foreign_branch)
        await db.flush()
        foreign_brand = Brand(
            company_id=foreign_company.id,
            slug=f"p2-foreign-{marker}",
            name="P2 Foreign Brand",
            business_type="restaurant",
            is_active=True,
        )
        db.add(foreign_brand)
        await db.flush()
        db.add(
            BrandBranch(
                company_id=foreign_company.id,
                brand_id=foreign_brand.id,
                branch_id=foreign_branch.id,
                is_active=True,
            )
        )

        product_id = await db.scalar(
            select(Product.id).where(
                Product.company_id == company.id,
                Product.deleted_at.is_(None),
            )
        )
        if product_id is None:
            raise RuntimeError("Canonical product fixture is missing")
        session = DiningSession(
            company_id=company.id,
            branch_id=branch_a1.id,
            status="open",
        )
        db.add(session)
        await db.flush()
        order = DiningOrder(
            company_id=company.id,
            branch_id=branch_a1.id,
            session_id=session.id,
            order_number=f"P2-SCOPE-{marker}",
            status="pending",
        )
        db.add(order)
        await db.flush()
        main_item = DiningOrderItem(
            order_id=order.id,
            product_id=product_id,
            product_name="P2 Main Ticket",
            qty=1,
            unit_price=0,
            station="Main",
            status="pending",
        )
        other_item = DiningOrderItem(
            order_id=order.id,
            product_id=product_id,
            product_name="P2 Other Ticket",
            qty=1,
            unit_price=0,
            station="Bar",
            status="pending",
        )
        db.add_all([main_item, other_item])
        await db.flush()
        main_ticket = KitchenTicket(
            company_id=company.id,
            branch_id=branch_a1.id,
            session_id=session.id,
            order_item_id=main_item.id,
            product_name=main_item.product_name,
            qty=1,
            station="Main",
            status="pending",
        )
        other_ticket = KitchenTicket(
            company_id=company.id,
            branch_id=branch_a1.id,
            session_id=session.id,
            order_item_id=other_item.id,
            product_name=other_item.product_name,
            qty=1,
            station="Bar",
            status="pending",
        )
        db.add_all([main_ticket, other_ticket])
        location_a1 = StockLocation(
            company_id=company.id,
            branch_id=branch_a1.id,
            code=f"P2RA-{marker}"[:20],
            name="P2 Report Branch A1",
            is_active=True,
        )
        location_a2 = StockLocation(
            company_id=company.id,
            branch_id=branch_a2.id,
            code=f"P2RB-{marker}"[:20],
            name="P2 Report Branch A2",
            is_active=True,
        )
        db.add_all([location_a1, location_a2])
        await db.flush()
        now = datetime.now(timezone.utc)
        branch_a1_shift = CashierShift(
            company_id=company.id,
            branch_id=branch_a1.id,
            location_id=location_a1.id,
            user_id=users["branch"].id,
            shift_number=f"P2RA{marker}"[:20],
            status="closed",
            opened_at=now,
            closed_at=now,
        )
        branch_a2_shift = CashierShift(
            company_id=company.id,
            branch_id=branch_a2.id,
            location_id=location_a2.id,
            user_id=users["company"].id,
            shift_number=f"P2RB{marker}"[:20],
            status="closed",
            opened_at=now,
            closed_at=now,
        )
        db.add_all([branch_a1_shift, branch_a2_shift])
        await db.commit()

        return ScopeContext(
            company_id=company.id,
            brand_a_id=brand_a.id,
            brand_a_slug=brand_a.slug,
            brand_b_id=brand_b.id,
            brand_b_slug=brand_b.slug,
            branch_a1_id=branch_a1.id,
            branch_a2_id=branch_a2.id,
            branch_b1_id=branch_b1.id,
            foreign_brand_id=foreign_brand.id,
            foreign_branch_id=foreign_branch.id,
            company_user_id=users["company"].id,
            brand_user_id=users["brand"].id,
            branch_user_id=users["branch"].id,
            kitchen_user_id=users["kitchen"].id,
            multi_user_id=users["multi"].id,
            usernames=usernames,
            main_ticket_id=main_ticket.id,
            other_ticket_id=other_ticket.id,
            branch_a1_shift_id=branch_a1_shift.id,
            branch_a2_shift_id=branch_a2_shift.id,
        )


async def verify_audit(
    context: ScopeContext,
    assignment_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.scalars(
                select(AuditLog)
                .where(
                    AuditLog.resource == "StaffRoleAssignment",
                    AuditLog.resource_id == str(assignment_id),
                )
                .order_by(AuditLog.created_at.asc())
            )
        ).all()
        if [row.action for row in rows] != [
            "system.staff_assignment.create",
            "system.staff_assignment.revoke",
        ]:
            raise RuntimeError(f"Unexpected assignment audit actions: {rows}")
        if any(row.user_id != actor_id or row.company_id != context.company_id for row in rows):
            raise RuntimeError("Assignment audit actor or tenant is incorrect")
        created, revoked = rows
        if created.old_value is not None or created.new_value.get("reason") != "temporary coverage":
            raise RuntimeError(f"Create audit before/after is incomplete: {created.new_value}")
        if (
            revoked.old_value.get("revoked_at") is not None
            or revoked.new_value.get("reason") != "coverage ended"
            or revoked.new_value.get("revoked_at") is None
        ):
            raise RuntimeError("Revoke audit before/after is incomplete")


def login(
    client: TestClient,
    context: ScopeContext,
    key: str,
    branch_id: uuid.UUID,
    *,
    station_key: str | None = None,
    expected: int = 200,
):
    payload = {
        "company_id": str(context.company_id),
        "username": context.usernames[key],
        "password": TEST_PASSWORD,
        "branch_id": str(branch_id),
    }
    if station_key is not None:
        payload["station_key"] = station_key
    return expect(
        client.post("/api/v1/auth/login", json=payload),
        expected,
        f"{key} login {branch_id}/{station_key}",
    )


def create_assignment(
    client: TestClient,
    headers: dict[str, str],
    user_id: uuid.UUID,
    role_id: str,
    scope_type: str,
    reason: str,
    *,
    brand_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    station_key: str | None = None,
    expected: int = 201,
):
    payload: dict[str, str] = {
        "role_id": role_id,
        "scope_type": scope_type,
        "reason": reason,
    }
    if brand_id is not None:
        payload["brand_id"] = str(brand_id)
    if branch_id is not None:
        payload["branch_id"] = str(branch_id)
    if station_key is not None:
        payload["station_key"] = station_key
    return expect(
        client.post(
            f"/api/v1/system/users/{user_id}/role-assignments",
            headers=headers,
            json=payload,
        ),
        expected,
        f"create {scope_type} assignment",
    )


def run() -> None:
    if settings.identity_database != "legacy" or settings.restaurant_service_database != "legacy":
        raise RuntimeError("Phase 2 scope smoke must exercise rollback-safe legacy defaults")
    if not settings.default_admin_password:
        raise RuntimeError("DEFAULT_ADMIN_PASSWORD is required")

    with TestClient(app) as client:
        if client.portal is None:
            raise RuntimeError("TestClient portal is unavailable")
        context = client.portal.call(seed_scope_context)

        admin_login = expect(
            client.post(
                "/api/v1/auth/login",
                json={
                    "company_id": str(context.company_id),
                    "username": "admin",
                    "password": settings.default_admin_password,
                    "branch_id": str(context.branch_a1_id),
                },
            ),
            200,
            "admin login",
        )
        admin_payload = decode_token(admin_login["access_token"])
        admin_id = uuid.UUID(admin_payload["sub"])
        headers = {"Authorization": f"Bearer {admin_login['access_token']}"}

        presets = expect(client.get("/api/v1/system/role-presets", headers=headers), 200, "presets")
        roles: dict[str, dict] = {}
        for preset in presets:
            roles[preset["key"]] = expect(
                client.post(
                    "/api/v1/system/roles",
                    headers=headers,
                    json={
                        "name": f"P2 {preset['name']} {uuid.uuid4().hex[:6]}",
                        "description": preset["description"],
                        "permission_ids": preset["permission_ids"],
                        "is_branch_assignable": preset["is_branch_assignable"],
                        "allowed_scope_types": preset["allowed_scopes"],
                    },
                ),
                201,
                f"create role {preset['key']}",
            )

        options = expect(
            client.get("/api/v1/system/staff-assignment-options", headers=headers),
            200,
            "assignment options",
        )
        option_by_branch = {row["id"]: row for row in options["branches"]}
        if option_by_branch[str(context.branch_a1_id)]["stations"] != ["Main", "Bar"]:
            raise RuntimeError(f"Station options are not canonical: {option_by_branch}")

        create_assignment(
            client,
            headers,
            context.brand_user_id,
            roles["brand-manager"]["id"],
            "brand",
            "cross-tenant brand",
            brand_id=context.foreign_brand_id,
            expected=404,
        )
        create_assignment(
            client,
            headers,
            context.branch_user_id,
            roles["branch-manager"]["id"],
            "branch",
            "cross-tenant branch",
            branch_id=context.foreign_branch_id,
            expected=404,
        )
        create_assignment(
            client,
            headers,
            context.kitchen_user_id,
            roles["kitchen-staff"]["id"],
            "station",
            "invalid station",
            branch_id=context.branch_a1_id,
            station_key="Not Configured",
            expected=400,
        )
        create_assignment(
            client,
            headers,
            context.branch_user_id,
            roles["branch-manager"]["id"],
            "company",
            "scope escalation",
            expected=400,
        )

        create_assignment(
            client,
            headers,
            context.company_user_id,
            roles["company-owner"]["id"],
            "company",
            "tenant owner",
        )
        create_assignment(
            client,
            headers,
            context.brand_user_id,
            roles["brand-manager"]["id"],
            "brand",
            "brand operations",
            brand_id=context.brand_a_id,
        )
        create_assignment(
            client,
            headers,
            context.branch_user_id,
            roles["branch-manager"]["id"],
            "branch",
            "branch operations",
            branch_id=context.branch_a1_id,
        )
        create_assignment(
            client,
            headers,
            context.kitchen_user_id,
            roles["kitchen-staff"]["id"],
            "station",
            "main kitchen",
            branch_id=context.branch_a1_id,
            station_key=" main ",
        )
        cashier_assignment = create_assignment(
            client,
            headers,
            context.multi_user_id,
            roles["cashier"]["id"],
            "branch",
            "temporary coverage",
            branch_id=context.branch_a1_id,
        )
        create_assignment(
            client,
            headers,
            context.multi_user_id,
            roles["kitchen-staff"]["id"],
            "station",
            "multi-role kitchen",
            branch_id=context.branch_a1_id,
            station_key="Main",
        )
        compatibility_username = f"p2_compat_kitchen_{uuid.uuid4().hex[:8]}"
        compatibility_user = expect(
            client.post(
                "/api/v1/system/users",
                headers=headers,
                json={
                    "username": compatibility_username,
                    "password": TEST_PASSWORD,
                    "display_name": "P2 Compatibility Kitchen",
                    "branch_id": str(context.branch_a1_id),
                    "role_id": roles["kitchen-staff"]["id"],
                },
            ),
            201,
            "create compatibility kitchen user",
        )
        create_assignment(
            client,
            headers,
            uuid.UUID(compatibility_user["id"]),
            roles["kitchen-staff"]["id"],
            "station",
            "compatibility station lock",
            branch_id=context.branch_a1_id,
            station_key="Main",
        )

        def compatibility_login(station_key: str | None, expected: int):
            payload = {
                "company_id": str(context.company_id),
                "username": compatibility_username,
                "password": TEST_PASSWORD,
                "branch_id": str(context.branch_a1_id),
            }
            if station_key is not None:
                payload["station_key"] = station_key
            return expect(
                client.post("/api/v1/auth/login", json=payload),
                expected,
                f"compatibility kitchen login {station_key}",
            )

        compatibility_login(None, 403)
        compatibility_login("Bar", 403)
        compatibility_login("Main", 200)

        company_login = login(client, context, "company", context.branch_a1_id)
        company_headers = {"Authorization": f"Bearer {company_login['access_token']}"}
        expect(client.get("/api/v1/auth/me", headers=company_headers), 200, "company me")
        expect(
            client.get("/api/v1/system/me/branches", headers=company_headers),
            200,
            "company accessible branches",
        )
        company_branches = expect(
            client.get(
                "/api/v1/system/branches",
                headers=company_headers,
            ),
            200,
            "company branch list",
        )
        if not {
            str(context.branch_a1_id),
            str(context.branch_a2_id),
            str(context.branch_b1_id),
        }.issubset({row["id"] for row in company_branches}):
            raise RuntimeError(f"Company scope branch list is incomplete: {company_branches}")
        for branch_id in (context.branch_a2_id, context.branch_b1_id):
            login(client, context, "company", branch_id)
        login(client, context, "company", context.foreign_branch_id, expected=404)
        expect(
            client.get("/api/v1/reports/dashboard", headers=company_headers),
            200,
            "company aggregate dashboard",
        )
        expect(
            client.get(
                "/api/v1/reports/dashboard",
                headers=company_headers,
                params={"branch_id": str(context.branch_b1_id)},
            ),
            200,
            "company selected-branch dashboard",
        )
        expect(
            client.get(
                f"/api/v1/reports/shifts/{context.branch_a2_shift_id}",
                headers=company_headers,
            ),
            200,
            "company cross-branch shift report",
        )

        brand_login = login(client, context, "brand", context.branch_a1_id)
        brand_headers = {"Authorization": f"Bearer {brand_login['access_token']}"}
        brand_branches = expect(
            client.get(
                "/api/v1/system/branches",
                headers=brand_headers,
            ),
            200,
            "brand branch list",
        )
        brand_branch_ids = {row["id"] for row in brand_branches}
        if not {
            str(context.branch_a1_id),
            str(context.branch_a2_id),
        }.issubset(brand_branch_ids) or str(context.branch_b1_id) in brand_branch_ids:
            raise RuntimeError(f"Brand scope branch list escaped Brand A: {brand_branches}")
        login(client, context, "brand", context.branch_a2_id)
        login(client, context, "brand", context.branch_b1_id, expected=403)
        expect(
            client.get("/api/v1/reports/dashboard", headers=brand_headers),
            200,
            "brand current-branch dashboard",
        )
        expect(
            client.get(
                "/api/v1/reports/dashboard",
                headers=brand_headers,
                params={"branch_id": str(context.branch_a2_id)},
            ),
            404,
            "brand generic dashboard cannot switch branch by query",
        )
        expect(
            client.get(
                f"/api/v1/restaurant/central/{context.brand_a_slug}/reports/operations",
                headers=brand_headers,
            ),
            200,
            "brand consolidated operations report",
        )
        expect(
            client.get(
                f"/api/v1/restaurant/central/{context.brand_b_slug}/reports/operations",
                headers=brand_headers,
            ),
            404,
            "brand consolidated report assignment boundary",
        )

        branch_login = login(client, context, "branch", context.branch_a1_id)
        branch_headers = {"Authorization": f"Bearer {branch_login['access_token']}"}
        branch_rows = expect(
            client.get(
                "/api/v1/system/branches",
                headers=branch_headers,
            ),
            200,
            "branch scope branch list",
        )
        if [row["id"] for row in branch_rows] != [str(context.branch_a1_id)]:
            raise RuntimeError(f"Branch scope list escaped Branch A1: {branch_rows}")
        expect(
            client.get(
                f"/api/v1/system/users/{context.company_user_id}/role-assignments",
                headers=branch_headers,
            ),
            403,
            "branch manager cannot inspect company assignments",
        )
        login(client, context, "branch", context.branch_a2_id, expected=403)
        expect(
            client.get(
                "/api/v1/reports/dashboard",
                headers=branch_headers,
                params={"branch_id": str(context.branch_a1_id)},
            ),
            200,
            "branch own dashboard",
        )
        expect(
            client.get(
                "/api/v1/reports/dashboard",
                headers=branch_headers,
                params={"branch_id": str(context.branch_a2_id)},
            ),
            404,
            "branch cross-branch dashboard",
        )
        expect(
            client.get(
                f"/api/v1/restaurant/central/{context.brand_a_slug}/reports/operations",
                headers=branch_headers,
            ),
            404,
            "branch cannot open consolidated Brand report",
        )
        expect(
            client.get(
                f"/api/v1/reports/shifts/{context.branch_a1_shift_id}",
                headers=branch_headers,
            ),
            200,
            "branch own shift report",
        )
        expect(
            client.get(
                f"/api/v1/reports/shifts/{context.branch_a2_shift_id}",
                headers=branch_headers,
            ),
            404,
            "branch cross-branch shift report",
        )
        expect(
            client.get(
                f"/api/v1/reports/shifts/{context.branch_a2_shift_id}/pdf",
                headers=branch_headers,
            ),
            404,
            "branch cross-branch shift PDF",
        )

        login(client, context, "kitchen", context.branch_a1_id, station_key="Main")
        login(client, context, "kitchen", context.branch_a1_id, station_key="Bar", expected=403)
        login(client, context, "kitchen", context.branch_a1_id, expected=403)
        login(client, context, "kitchen", context.branch_a2_id, station_key="Grill", expected=403)

        kitchen_login = login(
            client,
            context,
            "kitchen",
            context.branch_a1_id,
            station_key="MAIN",
        )
        kitchen_claims = decode_token(kitchen_login["access_token"])
        if (
            kitchen_claims.get("station_key") != "Main"
            or kitchen_claims.get("scope_types") != ["station"]
            or set(kitchen_claims.get("permissions", []))
            != {"fb.menu.view", "fb.kitchen.ticket.manage"}
        ):
            raise RuntimeError(f"Kitchen token escaped scope: {kitchen_claims}")
        kitchen_headers = {"Authorization": f"Bearer {kitchen_login['access_token']}"}
        tickets = expect(
            client.get("/api/v1/restaurant/kitchen", headers=kitchen_headers),
            200,
            "station kitchen list",
        )
        ticket_ids = {row["id"] for row in tickets}
        if str(context.main_ticket_id) not in ticket_ids or str(context.other_ticket_id) in ticket_ids:
            raise RuntimeError(f"Kitchen station list leaked tickets: {tickets}")
        expect(
            client.get(
                "/api/v1/restaurant/kitchen",
                headers=kitchen_headers,
                params={"station": "Bar"},
            ),
            403,
            "station kitchen query mismatch",
        )
        expect(
            client.patch(
                f"/api/v1/restaurant/kitchen/{context.other_ticket_id}",
                headers=kitchen_headers,
                json={"status": "cooking"},
            ),
            404,
            "station kitchen mutation isolation",
        )
        expect(
            client.patch(
                f"/api/v1/restaurant/kitchen/{context.main_ticket_id}",
                headers=kitchen_headers,
                json={"status": "cooking"},
            ),
            200,
            "station kitchen own mutation",
        )
        expect(
            client.get("/api/v1/restaurant/central/orders", headers=kitchen_headers),
            403,
            "kitchen central boundary",
        )
        expect(
            client.get("/api/v1/accounting/accounts", headers=kitchen_headers),
            403,
            "kitchen finance boundary",
        )
        expect(
            client.patch("/api/v1/restaurant/settings", headers=kitchen_headers, json={}),
            403,
            "kitchen settings boundary",
        )

        multi_branch = login(client, context, "multi", context.branch_a1_id)
        multi_branch_claims = decode_token(multi_branch["access_token"])
        if "pos.sale.create" not in multi_branch_claims["permissions"]:
            raise RuntimeError("Branch Cashier permission is missing")
        if "fb.kitchen.ticket.manage" in multi_branch_claims["permissions"]:
            raise RuntimeError("Station permission leaked into branch-only context")
        multi_station = login(
            client,
            context,
            "multi",
            context.branch_a1_id,
            station_key="Main",
        )
        multi_station_claims = decode_token(multi_station["access_token"])
        if not {"pos.sale.create", "fb.kitchen.ticket.manage"}.issubset(
            multi_station_claims["permissions"]
        ) or set(multi_station_claims["scope_types"]) != {"branch", "station"}:
            raise RuntimeError(f"Applicable multi-role union is incorrect: {multi_station_claims}")

        revoked = expect(
            client.post(
                f"/api/v1/system/users/{context.multi_user_id}/role-assignments/"
                f"{cashier_assignment['id']}/revoke",
                headers=headers,
                json={"reason": "coverage ended"},
            ),
            200,
            "revoke assignment",
        )
        if revoked["revoked_at"] is None or revoked["revocation_reason"] != "coverage ended":
            raise RuntimeError(f"Revocation result is incomplete: {revoked}")
        login(client, context, "multi", context.branch_a1_id, expected=403)
        active_rows = expect(
            client.get(
                f"/api/v1/system/users/{context.multi_user_id}/role-assignments",
                headers=headers,
            ),
            200,
            "active assignment list",
        )
        if any(row["id"] == cashier_assignment["id"] for row in active_rows):
            raise RuntimeError("Revoked assignment remained active")
        history = expect(
            client.get(
                f"/api/v1/system/users/{context.multi_user_id}/role-assignments",
                headers=headers,
                params={"include_revoked": "true"},
            ),
            200,
            "assignment history",
        )
        if not any(row["id"] == cashier_assignment["id"] for row in history):
            raise RuntimeError("Revoked assignment disappeared from history")
        client.portal.call(
            verify_audit,
            context,
            uuid.UUID(cashier_assignment["id"]),
            admin_id,
        )

        print("p2_scope_company_brand_branch=ok")
        print("p2_scope_station_isolation=ok")
        print("p2_scope_multi_role_union=ok")
        print("p2_scope_audit_revoke=ok")
        print("p2_scope_kitchen_boundary=ok")
        print("p4_report_scope=ok company=true brand=true branch=true shift=true")


if __name__ == "__main__":
    run()
