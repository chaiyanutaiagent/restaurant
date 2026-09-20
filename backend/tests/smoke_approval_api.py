from __future__ import annotations

import asyncio
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import (
    AsyncSessionLocal,
    PlatformSessionLocal,
    engine,
    platform_engine,
    restaurant_engine,
    retail_engine,
    takeaway_engine,
)
from app.main import app
from app.models.approval import ApprovalGrantUsage, ManagerPinCredential
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.company import Company
from app.models.pos import Payment
from app.models.product import Product, Unit
from app.models.restaurant import (
    Brand,
    BrandBranch,
    DiningOrder,
    DiningOrderItem,
    DiningSession,
)
from app.models.role import Permission, Role
from app.models.settings import BranchSettings
from app.models.stock import StockBalance, StockLocation
from app.models.user import User, UserBranch
from app.utils.create_superuser import DEFAULT_COMPANY_ID, ensure_default_company_seed_in_session
from app.utils.security import hash_password, verify_password
from app.utils.seed_permissions import seed_default_permissions
from app.services.platform_reference_projection import process_projection_batch, seed_snapshot_events
from app.services.retail_reference_projector import project_retail_reference_snapshot


PASSWORD = "ApprovalSmoke123!"
MANAGER_PIN = "482915"


def expect(response, expected: int):
    if response.status_code != expected:
        raise RuntimeError(
            f"Expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    return response.json().get("data")


def expect_detail_code(response, expected_status: int, code: str) -> None:
    if response.status_code != expected_status:
        raise RuntimeError(
            f"Expected HTTP {expected_status}, got {response.status_code}: {response.text}"
        )
    detail = response.json().get("detail")
    if not isinstance(detail, dict) or detail.get("code") != code:
        raise RuntimeError(f"Expected detail code {code}, got: {response.text}")


async def prepare() -> dict[str, str]:
    marker = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        await seed_default_permissions(db)
        await ensure_default_company_seed_in_session(db)
        branch = Branch(
            company_id=DEFAULT_COMPANY_ID,
            code=f"APPROVAL-{marker}",
            name=f"Approval Smoke {marker}",
            is_active=True,
        )
        db.add(branch)
        await db.flush()
        location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=branch.id,
            code=f"STORE-{marker}",
            name=f"Approval Store {marker}",
            is_active=True,
        )
        db.add(location)
        await db.flush()
        brand = Brand(
            company_id=DEFAULT_COMPANY_ID,
            slug=f"approval-smoke-{marker}",
            name=f"Approval Smoke {marker}",
            business_type="restaurant",
            is_active=True,
        )
        db.add(brand)
        await db.flush()
        db.add(
            BrandBranch(
                company_id=DEFAULT_COMPANY_ID,
                brand_id=brand.id,
                branch_id=branch.id,
                store_location_id=location.id,
                is_active=True,
            )
        )
        unit = Unit(
            company_id=DEFAULT_COMPANY_ID,
            code=f"EA-{marker}",
            name="ชิ้น",
            decimal_places=0,
            is_active=True,
        )
        db.add(unit)
        await db.flush()
        product = Product(
            company_id=DEFAULT_COMPANY_ID,
            brand_id=brand.id,
            unit_id=unit.id,
            sku=f"APPROVAL-SKU-{marker}",
            name=f"Approval Product {marker}",
            product_type="simple",
            selling_price=Decimal("100"),
            cost_price=Decimal("20"),
            vat_type="included",
            vat_rate=Decimal("7"),
            is_active=True,
            is_for_sale=True,
            is_for_purchase=False,
        )
        db.add(product)
        await db.flush()
        db.add(
            StockBalance(
                company_id=DEFAULT_COMPANY_ID,
                branch_id=branch.id,
                location_id=location.id,
                product_id=product.id,
                variant_id=None,
                qty_on_hand=Decimal("100"),
                qty_reserved=Decimal("0"),
                cost_per_unit=Decimal("20"),
            )
        )
        db.add(
            BranchSettings(
                company_id=DEFAULT_COMPANY_ID,
                branch_id=branch.id,
                pos_allow_discount=True,
                pos_max_discount_pct=Decimal("50"),
                pos_cashier_discount_limit_pct=Decimal("10"),
                pos_price_override_auto_limit_pct=Decimal("10"),
                pos_price_override_auto_limit_amount=Decimal("100"),
                pos_price_override_max_deviation_pct=Decimal("50"),
                pos_price_override_min_margin_pct=Decimal("0"),
                pos_price_override_self_approval=False,
                stock_adjust_approval_threshold_qty=Decimal("1"),
            )
        )

        permission_codes = {
            "pos.sale.view",
            "pos.sale.create",
            "pos.sale.void",
            "pos.sale.void.request",
            "pos.discount.apply",
            "pos.discount.override",
            "pos.price.override",
            "pos.price.override.request",
            "pos.refund.create",
            "pos.refund.request",
            "pos.cashier.open_shift",
            "inventory.stock.view",
            "inventory.stock.adjust",
            "inventory.stock.adjust.request",
            "fb.order.create",
            "system.role.view",
            "system.device.view",
            "system.device.manage",
        }
        permissions = {
            permission.code: permission
            for permission in (
                await db.scalars(
                    select(Permission).where(Permission.code.in_(permission_codes))
                )
            ).all()
        }
        if set(permissions) != permission_codes:
            raise RuntimeError(
                f"Permission seed incomplete: {sorted(permission_codes - set(permissions))}"
            )
        manager_role = Role(
            company_id=DEFAULT_COMPANY_ID,
            name=f"approval_manager_{marker}",
            is_branch_assignable=True,
            allowed_scope_types=["branch"],
        )
        manager_role.permissions = [
            permissions["pos.sale.create"],
            permissions["pos.sale.void"],
            permissions["pos.discount.override"],
            permissions["pos.price.override"],
            permissions["pos.price.override.request"],
            permissions["pos.refund.create"],
            permissions["inventory.stock.adjust"],
            permissions["inventory.stock.view"],
            permissions["system.role.view"],
        ]
        cashier_role = Role(
            company_id=DEFAULT_COMPANY_ID,
            name=f"approval_cashier_{marker}",
            is_branch_assignable=True,
            allowed_scope_types=["branch"],
        )
        cashier_role.permissions = [
            permissions["pos.sale.view"],
            permissions["pos.sale.create"],
            permissions["pos.sale.void.request"],
            permissions["pos.discount.apply"],
            permissions["pos.price.override.request"],
            permissions["pos.refund.request"],
            permissions["pos.cashier.open_shift"],
            permissions["inventory.stock.view"],
            permissions["inventory.stock.adjust.request"],
            permissions["fb.order.create"],
        ]
        db.add_all([manager_role, cashier_role])
        await db.flush()

        manager_username = f"approval-manager-{marker}"
        cashier_username = f"approval-cashier-{marker}"
        manager = User(
            company_id=DEFAULT_COMPANY_ID,
            username=manager_username,
            display_name="Approval Manager",
            hashed_password=hash_password(PASSWORD),
            is_active=True,
        )
        cashier = User(
            company_id=DEFAULT_COMPANY_ID,
            username=cashier_username,
            display_name="Approval Cashier",
            hashed_password=hash_password(PASSWORD),
            is_active=True,
        )
        db.add_all([manager, cashier])
        await db.flush()
        db.add_all(
            [
                UserBranch(
                    user_id=manager.id,
                    branch_id=branch.id,
                    brand_id=brand.id,
                    business_type="restaurant",
                    target_database="restaurant",
                    role_id=manager_role.id,
                    is_default=True,
                ),
                UserBranch(
                    user_id=cashier.id,
                    branch_id=branch.id,
                    brand_id=brand.id,
                    business_type="restaurant",
                    target_database="restaurant",
                    role_id=cashier_role.id,
                    is_default=True,
                ),
            ]
        )
        restaurant_session = DiningSession(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=branch.id,
            opened_by=cashier.id,
            status="open",
            guest_count=1,
        )
        db.add(restaurant_session)
        await db.flush()
        dining_order = DiningOrder(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=branch.id,
            session_id=restaurant_session.id,
            order_number=f"APPROVAL-FB-{marker}",
            source="staff",
            status="completed",
        )
        db.add(dining_order)
        await db.flush()
        db.add(
            DiningOrderItem(
                order_id=dining_order.id,
                product_id=product.id,
                product_name=product.name,
                qty=1,
                unit_price=Decimal("100"),
                status="served",
            )
        )
        await db.commit()
        result = {
            "branch_id": str(branch.id),
            "location_id": str(location.id),
            "product_id": str(product.id),
            "brand_id": str(brand.id),
            "manager_role_id": str(manager_role.id),
            "cashier_role_id": str(cashier_role.id),
            "manager_id": str(manager.id),
            "manager_username": manager_username,
            "cashier_id": str(cashier.id),
            "cashier_username": cashier_username,
            "restaurant_session_id": str(restaurant_session.id),
        }
    if settings.platform_database_url_effective != settings.database_url:
        async with PlatformSessionLocal() as identity_db:
            await seed_default_permissions(identity_db)
            identity_company = await identity_db.get(Company, DEFAULT_COMPANY_ID)
            if identity_company is None:
                identity_db.add(
                    Company(
                        id=DEFAULT_COMPANY_ID,
                        name="Restaurant POS UAT",
                        business_slug=f"approval-smoke-company-{marker}",
                        is_active=True,
                    )
                )
                await identity_db.flush()
            branch_id = uuid.UUID(result["branch_id"])
            brand_id = uuid.UUID(result["brand_id"])
            identity_db.add_all(
                [
                    Branch(
                        id=branch_id,
                        company_id=DEFAULT_COMPANY_ID,
                        code=f"APPROVAL-{marker}",
                        name=f"Approval Smoke {marker}",
                        is_active=True,
                    ),
                    Brand(
                        id=brand_id,
                        company_id=DEFAULT_COMPANY_ID,
                        slug=f"approval-smoke-{marker}",
                        name=f"Approval Smoke {marker}",
                        business_type="restaurant",
                        is_active=True,
                    ),
                ]
            )
            identity_permissions = {
                permission.code: permission
                for permission in (
                    await identity_db.scalars(
                        select(Permission).where(Permission.code.in_(permission_codes))
                    )
                ).all()
            }
            identity_manager_role = Role(
                id=uuid.UUID(result["manager_role_id"]),
                company_id=DEFAULT_COMPANY_ID,
                name=f"approval_manager_{marker}",
                is_branch_assignable=True,
                allowed_scope_types=["branch"],
            )
            identity_manager_role.permissions = [
                identity_permissions[code]
                for code in (
                    "pos.sale.create",
                    "pos.sale.void",
                    "pos.discount.override",
                    "pos.price.override",
                    "pos.price.override.request",
                    "pos.refund.create",
                    "inventory.stock.adjust",
                    "inventory.stock.view",
                    "system.role.view",
                )
            ]
            identity_cashier_role = Role(
                id=uuid.UUID(result["cashier_role_id"]),
                company_id=DEFAULT_COMPANY_ID,
                name=f"approval_cashier_{marker}",
                is_branch_assignable=True,
                allowed_scope_types=["branch"],
            )
            identity_cashier_role.permissions = [
                identity_permissions[code]
                for code in (
                    "pos.sale.view",
                    "pos.sale.create",
                    "pos.sale.void.request",
                    "pos.discount.apply",
                    "pos.price.override.request",
                    "pos.refund.request",
                    "pos.cashier.open_shift",
                    "inventory.stock.view",
                    "inventory.stock.adjust.request",
                    "fb.order.create",
                )
            ]
            identity_db.add_all([identity_manager_role, identity_cashier_role])
            await identity_db.flush()
            identity_manager = User(
                id=uuid.UUID(result["manager_id"]),
                company_id=DEFAULT_COMPANY_ID,
                username=result["manager_username"],
                display_name="Approval Manager",
                hashed_password=hash_password(PASSWORD),
                is_active=True,
            )
            identity_cashier = User(
                id=uuid.UUID(result["cashier_id"]),
                company_id=DEFAULT_COMPANY_ID,
                username=result["cashier_username"],
                display_name="Approval Cashier",
                hashed_password=hash_password(PASSWORD),
                is_active=True,
            )
            identity_db.add_all([identity_manager, identity_cashier])
            await identity_db.flush()
            identity_db.add_all(
                [
                    UserBranch(
                        user_id=identity_manager.id,
                        branch_id=branch_id,
                        brand_id=brand_id,
                        business_type="restaurant",
                        target_database="restaurant",
                        role_id=identity_manager_role.id,
                        is_default=True,
                    ),
                    UserBranch(
                        user_id=identity_cashier.id,
                        branch_id=branch_id,
                        brand_id=brand_id,
                        business_type="restaurant",
                        target_database="restaurant",
                        role_id=identity_cashier_role.id,
                        is_default=True,
                    ),
                ]
            )
            await identity_db.commit()
        async with PlatformSessionLocal() as identity_db:
            await seed_snapshot_events(identity_db)
            await identity_db.commit()
        while True:
            batch = await process_projection_batch(limit=100)
            if batch.failed:
                raise RuntimeError("Restaurant reference projection failed during approval smoke setup")
            if batch.claimed == 0:
                break
        await project_retail_reference_snapshot()
    database_engines = {
        id(database_engine): database_engine
        for database_engine in (
            engine,
            platform_engine,
            restaurant_engine,
            retail_engine,
            takeaway_engine,
        )
        if database_engine is not None
    }
    await asyncio.gather(*(database_engine.dispose() for database_engine in database_engines.values()))
    return result


def login(client: TestClient, username: str) -> dict[str, str]:
    data = expect(
        client.post(
            "/api/v1/auth/login",
            json={
                "company_id": str(DEFAULT_COMPANY_ID),
                "username": username,
                "password": PASSWORD,
            },
        ),
        200,
    )
    return {"Authorization": f"Bearer {data['access_token']}"}


def issue_approval(
    client: TestClient,
    headers: dict[str, str],
    context: dict[str, str],
    *,
    action: str,
    request_payload: dict,
    reason: str,
    pin: str = MANAGER_PIN,
):
    return client.post(
        "/api/v1/approvals/sessions",
        headers=headers,
        json={
            "approver_username": context["manager_username"],
            "manager_pin": pin,
            "action": action,
            "reason": reason,
            "request_payload": request_payload,
        },
    )


async def verify(context: dict[str, str]) -> None:
    verify_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(verify_engine, expire_on_commit=False)
    async with session_factory() as db:
        credential = await db.scalar(
            select(ManagerPinCredential).where(
                ManagerPinCredential.user_id == uuid.UUID(context["manager_id"])
            )
        )
        if credential is None or credential.pin_hash == MANAGER_PIN:
            raise RuntimeError("Manager PIN was not stored as a hash")
        if not verify_password("583026", credential.pin_hash):
            raise RuntimeError("Manager PIN rotation did not persist")

        usage_count = await db.scalar(select(func.count(ApprovalGrantUsage.id))) or 0
        if usage_count != 6:
            raise RuntimeError(f"Expected 6 consumed approval grants, got {usage_count}")
        refund_audit = await db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "pos.sale.refund")
            .order_by(AuditLog.created_at.desc())
        )
        approval = refund_audit.new_value.get("approval") if refund_audit else None
        if not approval or approval.get("approver_id") != context["manager_id"]:
            raise RuntimeError("Refund audit is missing manager approval evidence")
        if not refund_audit.new_value.get("original_payment_ids"):
            raise RuntimeError("Refund audit is missing original payment IDs")
        refund_payment = await db.scalar(
            select(Payment)
            .where(Payment.amount < 0)
            .order_by(Payment.paid_at.desc())
        )
        if refund_payment is None or refund_payment.original_payment_id is None:
            raise RuntimeError("Refund payment is not linked to its original payment")
    await verify_engine.dispose()


def run() -> None:
    context = asyncio.run(prepare())
    with TestClient(app) as client:
        manager_headers = login(client, context["manager_username"])
        cashier_headers = login(client, context["cashier_username"])

        presets = expect(
            client.get("/api/v1/system/role-presets", headers=manager_headers),
            200,
        )
        if [preset["key"] for preset in presets] != [
            "company-owner",
            "brand-manager",
            "branch-manager",
            "accountant",
            "purchasing",
            "warehouse",
            "hr",
            "auditor",
            "area-manager",
            "service-staff",
            "kitchen-manager",
            "cashier",
            "kitchen-staff",
        ]:
            raise RuntimeError("Phase 2 role preset order is invalid")
        if any(
            preset["policy_version"] != "2026-09-20.1"
            or not preset["is_available"]
            for preset in presets
        ):
            raise RuntimeError("Phase 2 role preset policy is unavailable or stale")
        preset_by_key = {preset["key"]: preset for preset in presets}
        cashier_codes = set(preset_by_key["cashier"]["permission_codes"])
        if not {"pos.sale.void.request", "pos.refund.request"}.issubset(cashier_codes):
            raise RuntimeError("Cashier preset is missing approval request permissions")
        if cashier_codes.intersection(
            {"pos.sale.void", "pos.discount.override", "pos.refund.create"}
        ):
            raise RuntimeError("Cashier preset contains direct approval permissions")
        if set(preset_by_key["kitchen-staff"]["permission_codes"]) != {
            "fb.menu.view",
            "fb.kitchen.ticket.manage",
            "takeaway.kitchen.manage",
        }:
            raise RuntimeError("Kitchen Staff escaped the station kitchen boundary")

        status_data = expect(
            client.get("/api/v1/approvals/manager-pin", headers=manager_headers),
            200,
        )
        if status_data["is_set"]:
            raise RuntimeError("Manager PIN unexpectedly existed before setup")
        expect(
            client.put(
                "/api/v1/approvals/manager-pin",
                headers=manager_headers,
                json={"current_password": PASSWORD, "pin": MANAGER_PIN},
            ),
            200,
        )

        stock_payload = {
            "location_id": context["location_id"],
            "product_id": context["product_id"],
            "qty": 2,
            "note": "approval stock correction",
        }
        expect_detail_code(
            client.post("/api/v1/stock/adjust", headers=cashier_headers, json=stock_payload),
            403,
            "approval_required",
        )
        self_approval = client.post(
            "/api/v1/approvals/sessions",
            headers=cashier_headers,
            json={
                "approver_username": context["cashier_username"],
                "manager_pin": MANAGER_PIN,
                "action": "inventory.stock.adjust",
                "reason": "self approval must fail",
                "request_payload": stock_payload,
            },
        )
        if self_approval.status_code != 403:
            raise RuntimeError(f"Self approval was not rejected: {self_approval.text}")

        stock_approval = expect(
            issue_approval(
                client,
                cashier_headers,
                context,
                action="inventory.stock.adjust",
                request_payload=stock_payload,
                reason="approve stock correction",
            ),
            200,
        )
        approved_stock_payload = {
            **stock_payload,
            "approval_token": stock_approval["approval_token"],
        }
        expect(
            client.post(
                "/api/v1/stock/adjust",
                headers=cashier_headers,
                json=approved_stock_payload,
            ),
            201,
        )
        expect_detail_code(
            client.post(
                "/api/v1/stock/adjust",
                headers=cashier_headers,
                json=approved_stock_payload,
            ),
            409,
            "approval_already_used",
        )

        mismatch_approval = expect(
            issue_approval(
                client,
                cashier_headers,
                context,
                action="inventory.stock.adjust",
                request_payload=stock_payload,
                reason="approve exact stock payload",
            ),
            200,
        )

        expect_detail_code(
            client.post(
                "/api/v1/stock/adjust",
                headers=cashier_headers,
                json={
                    **stock_payload,
                    "qty": 3,
                    "approval_token": mismatch_approval["approval_token"],
                },
            ),
            403,
            "approval_mismatch",
        )
        expect(
            client.post(
                "/api/v1/stock/adjust",
                headers=cashier_headers,
                json={
                    **stock_payload,
                    "approval_token": mismatch_approval["approval_token"],
                },
            ),
            201,
        )
        expect(
            client.post("/api/v1/stock/adjust", headers=manager_headers, json=stock_payload),
            201,
        )

        shift = expect(
            client.post(
                "/api/v1/pos/shifts/open",
                headers=cashier_headers,
                json={"location_id": context["location_id"], "opening_cash": 0},
            ),
            201,
        )
        restaurant_checkout_payload = {
            "shift_id": shift["id"],
            "location_id": context["location_id"],
            "payment_method": "cash",
            "paid_amount": 80,
            "client_order_id": f"approval-sale-{uuid.uuid4()}",
            "payments": [],
            "discount_amount": 20,
        }
        expect_detail_code(
            client.post(
                f"/api/v1/restaurant/sessions/{context['restaurant_session_id']}/checkout",
                headers=cashier_headers,
                json=restaurant_checkout_payload,
            ),
            403,
            "approval_required",
        )
        restaurant_checkout_approval = expect(
            issue_approval(
                client,
                cashier_headers,
                context,
                action="pos.discount.override",
                request_payload={
                    "session_id": context["restaurant_session_id"],
                    **restaurant_checkout_payload,
                },
                reason="approve restaurant checkout discount",
            ),
            200,
        )
        expect(
            client.post(
                f"/api/v1/restaurant/sessions/{context['restaurant_session_id']}/checkout",
                headers=cashier_headers,
                json={
                    **restaurant_checkout_payload,
                    "approval_token": restaurant_checkout_approval["approval_token"],
                },
            ),
            200,
        )
        sale_payload = {
            "shift_id": shift["id"],
            "location_id": context["location_id"],
            "items": [
                {
                    "product_id": context["product_id"],
                    "qty": 1,
                    "unit_price": 100,
                    "original_price": 100,
                    "discount_amount": 0,
                    "discount_type": "amount",
                    "vat_type": "none",
                    "vat_rate": 0,
                }
            ],
            "discount_amount": 20,
            "discount_type": "amount",
            "payment_method": "cash",
            "paid_amount": 80,
            "client_order_id": f"approval-pos-{uuid.uuid4()}",
        }
        expect_detail_code(
            client.post("/api/v1/pos/sales", headers=cashier_headers, json=sale_payload),
            403,
            "approval_required",
        )
        hard_max_payload = {
            **sale_payload,
            "discount_amount": 60,
            "paid_amount": 40,
        }
        hard_max_approval = expect(
            issue_approval(
                client,
                cashier_headers,
                context,
                action="pos.discount.override",
                request_payload=hard_max_payload,
                reason="hard maximum must still reject",
            ),
            200,
        )
        expect_detail_code(
            client.post(
                "/api/v1/pos/sales",
                headers=cashier_headers,
                json={
                    **hard_max_payload,
                    "approval_token": hard_max_approval["approval_token"],
                },
            ),
            400,
            "discount_limit_exceeded",
        )
        discount_approval = expect(
            issue_approval(
                client,
                cashier_headers,
                context,
                action="pos.discount.override",
                request_payload=sale_payload,
                reason="approve discount override",
            ),
            200,
        )
        sale = expect(
            client.post(
                "/api/v1/pos/sales",
                headers=cashier_headers,
                json={**sale_payload, "approval_token": discount_approval["approval_token"]},
            ),
            201,
        )

        void_payload = {
            "order_id": sale["id"],
            "void_reason": "customer cancelled approved sale",
        }
        expect_detail_code(
            client.post(
                f"/api/v1/pos/sales/{sale['id']}/void",
                headers=cashier_headers,
                json={"void_reason": void_payload["void_reason"]},
            ),
            403,
            "approval_required",
        )
        void_approval = expect(
            issue_approval(
                client,
                cashier_headers,
                context,
                action="pos.sale.void",
                request_payload=void_payload,
                reason="approve sale void",
            ),
            200,
        )
        expect(
            client.post(
                f"/api/v1/pos/sales/{sale['id']}/void",
                headers=cashier_headers,
                json={
                    "void_reason": void_payload["void_reason"],
                    "approval_token": void_approval["approval_token"],
                },
            ),
            200,
        )

        refundable_sale_payload = {
            **sale_payload,
            "discount_amount": 0,
            "paid_amount": 100,
            "client_order_id": f"approval-refund-{uuid.uuid4()}",
        }
        refundable_sale = expect(
            client.post(
                "/api/v1/pos/sales",
                headers=cashier_headers,
                json=refundable_sale_payload,
            ),
            201,
        )
        refund_payload = {
            "order_id": refundable_sale["id"],
            "refund_reason": "approved customer refund",
        }
        expect_detail_code(
            client.post(
                f"/api/v1/pos/sales/{refundable_sale['id']}/refund",
                headers=cashier_headers,
                json={"refund_reason": refund_payload["refund_reason"]},
            ),
            403,
            "approval_required",
        )
        refund_approval = expect(
            issue_approval(
                client,
                cashier_headers,
                context,
                action="pos.refund.create",
                request_payload=refund_payload,
                reason="approve customer refund",
            ),
            200,
        )
        expect(
            client.post(
                f"/api/v1/pos/sales/{refundable_sale['id']}/refund",
                headers=cashier_headers,
                json={
                    "refund_reason": refund_payload["refund_reason"],
                    "approval_token": refund_approval["approval_token"],
                },
            ),
            200,
        )

        for _ in range(settings.manager_pin_max_failed_attempts):
            response = issue_approval(
                client,
                cashier_headers,
                context,
                action="inventory.stock.adjust",
                request_payload=stock_payload,
                reason="lockout attempt audit",
                pin="000001",
            )
            if response.status_code != 401:
                raise RuntimeError(f"Wrong PIN attempt was not rejected: {response.text}")
        locked = issue_approval(
            client,
            cashier_headers,
            context,
            action="inventory.stock.adjust",
            request_payload=stock_payload,
            reason="locked PIN check",
        )
        expect_detail_code(locked, 423, "manager_pin_locked")
        expect(
            client.put(
                "/api/v1/approvals/manager-pin",
                headers=manager_headers,
                json={"current_password": PASSWORD, "pin": "583026"},
            ),
            200,
        )

    asyncio.run(verify(context))
    print(
        "p2_approval_api_smoke=ok "
        "role_presets=true pin_hash_lockout=true single_use=true fingerprint=true "
        "discount_void_refund_stock=true restaurant_checkout=true "
        "original_payment_link=true"
    )


if __name__ == "__main__":
    run()
