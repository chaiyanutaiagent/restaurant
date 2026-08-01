from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
import os
import uuid
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.main import app
from app.models.accounting import JournalEntry
from app.models.branch import Branch
from app.models.integration import OperationalOutboxEvent
from app.models.pos import CashierShift, Payment, SaleOrder
from app.models.product import Product, Unit
from app.models.restaurant import Brand, BrandBranch
from app.models.role import Permission, Role
from app.models.staff_assignment import StaffRoleAssignment
from app.models.stock import StockBalance, StockLocation, StockMovement
from app.models.user import User
from app.services.role_preset_service import COMPANY_OWNER_PERMISSION_CODES
from app.utils.create_superuser import DEFAULT_COMPANY_ID, ensure_default_company_seed_in_session
from app.utils.security import hash_password
from app.utils.seed_permissions import seed_default_permissions


PROJECT_PREFIX = "restaurant-p5-completion"
PASSWORD = "P5RetailCompatibility123!"


def expect(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    payload = response.json()
    return payload.get("data", payload)


async def prepare() -> dict[str, str]:
    compose_project = os.environ.get("P5_COMPLETION_PROJECT_NAME", "")
    if not compose_project.startswith(PROJECT_PREFIX):
        raise RuntimeError(
            "Retail compatibility smoke refuses to write outside an isolated Phase 5 completion project"
        )

    marker = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        actual_database = str(await db.scalar(func.current_database()) or "")
        if actual_database != settings.postgres_db:
            raise RuntimeError(
                f"Retail compatibility database mismatch: {actual_database} != {settings.postgres_db}"
            )
        await seed_default_permissions(db)
        await ensure_default_company_seed_in_session(db)

        branch = Branch(
            company_id=DEFAULT_COMPANY_ID,
            code=f"RET-{marker}",
            name=f"Retail Compatibility {marker}",
            is_active=True,
        )
        db.add(branch)
        await db.flush()
        location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=branch.id,
            code=f"RET-STOCK-{marker}",
            name=f"Retail Stock {marker}",
            is_active=True,
        )
        db.add(location)
        await db.flush()
        brand = Brand(
            company_id=DEFAULT_COMPANY_ID,
            slug=f"retail-compat-{marker}",
            name=f"Retail Compatibility {marker}",
            business_type="retail_pos",
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

        unit = await db.scalar(
            select(Unit).where(Unit.company_id == DEFAULT_COMPANY_ID, Unit.code == "piece")
        )
        if unit is None:
            unit = Unit(
                company_id=DEFAULT_COMPANY_ID,
                code="piece",
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
            sku=f"RET-SKU-{marker}",
            barcode=f"885{marker[:7]}",
            name=f"Retail Compatibility Product {marker}",
            product_type="simple",
            cost_price=Decimal("40"),
            selling_price=Decimal("107"),
            vat_type="included",
            vat_rate=Decimal("7"),
            is_active=True,
            is_for_sale=True,
            is_for_purchase=True,
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
                qty_on_hand=Decimal("10"),
                qty_reserved=Decimal("0"),
                cost_per_unit=Decimal("40"),
            )
        )

        permissions = list(
            (
                await db.scalars(
                    select(Permission).where(
                        Permission.code.in_(COMPANY_OWNER_PERMISSION_CODES)
                    )
                )
            ).all()
        )
        if {permission.code for permission in permissions} != set(
            COMPANY_OWNER_PERMISSION_CODES
        ):
            raise RuntimeError("Company Owner permission catalog is incomplete")
        owner_role = Role(
            company_id=DEFAULT_COMPANY_ID,
            name=f"Retail Company Owner {marker}",
            description="Phase 5 retail compatibility owner",
            is_system=False,
            is_branch_assignable=False,
            allowed_scope_types=["company"],
        )
        owner_role.permissions = permissions
        owner = User(
            company_id=DEFAULT_COMPANY_ID,
            username=f"retail-owner-{marker}",
            hashed_password=hash_password(PASSWORD),
            display_name="Retail Compatibility Owner",
            is_active=True,
            is_superuser=False,
        )
        db.add_all([owner_role, owner])
        await db.flush()
        db.add(
            StaffRoleAssignment(
                company_id=DEFAULT_COMPANY_ID,
                user_id=owner.id,
                role_id=owner_role.id,
                scope_type="company",
                scope_key=str(DEFAULT_COMPANY_ID),
                brand_id=None,
                branch_id=None,
                station_key=None,
                assignment_reason="Phase 5 retail compatibility owner regression",
                assigned_by=owner.id,
            )
        )
        await db.commit()
        context = {
            "branch_id": str(branch.id),
            "brand_id": str(brand.id),
            "location_id": str(location.id),
            "product_id": str(product.id),
            "username": owner.username,
            "client_order_id": f"retail-compat-{marker}",
        }
    await engine.dispose()
    return context


async def verify(context: dict[str, str], sale_order_id: str, shift_id: str) -> None:
    verify_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(verify_engine, expire_on_commit=False)
    async with session_factory() as db:
        order_id = uuid.UUID(sale_order_id)
        order_count = int(
            await db.scalar(
                select(func.count(SaleOrder.id)).where(
                    SaleOrder.company_id == DEFAULT_COMPANY_ID,
                    SaleOrder.branch_id == uuid.UUID(context["branch_id"]),
                    SaleOrder.client_order_id == context["client_order_id"],
                )
            )
            or 0
        )
        payment_count = int(
            await db.scalar(select(func.count(Payment.id)).where(Payment.order_id == order_id))
            or 0
        )
        movement_count = int(
            await db.scalar(
                select(func.count(StockMovement.id)).where(
                    StockMovement.reference_type == "SaleOrder",
                    StockMovement.reference_id == sale_order_id,
                    StockMovement.movement_type == "sale",
                )
            )
            or 0
        )
        journal_count = int(
            await db.scalar(
                select(func.count(JournalEntry.id)).where(
                    JournalEntry.company_id == DEFAULT_COMPANY_ID,
                    JournalEntry.entry_type == "sale",
                    JournalEntry.reference_type == "SaleOrder",
                    JournalEntry.reference_id == sale_order_id,
                )
            )
            or 0
        )
        outbox_count = int(
            await db.scalar(
                select(func.count(OperationalOutboxEvent.id)).where(
                    OperationalOutboxEvent.aggregate_id == order_id
                )
            )
            or 0
        )
        balance = await db.scalar(
            select(StockBalance).where(
                StockBalance.location_id == uuid.UUID(context["location_id"]),
                StockBalance.product_id == uuid.UUID(context["product_id"]),
            )
        )
        shift = await db.get(CashierShift, uuid.UUID(shift_id))
        if (order_count, payment_count, movement_count, journal_count, outbox_count) != (
            1,
            1,
            1,
            1,
            1,
        ):
            raise RuntimeError(
                "Retail sale was not exactly once across order/payment/stock/accounting/outbox: "
                f"{order_count}/{payment_count}/{movement_count}/{journal_count}/{outbox_count}"
            )
        if balance is None or Decimal(balance.qty_on_hand) != Decimal("9"):
            raise RuntimeError("Retail sale did not decrement legacy-compatible stock exactly once")
        if (
            shift is None
            or shift.status != "closed"
            or Decimal(shift.expected_cash or 0) != Decimal("107.00")
            or Decimal(shift.cash_difference or 0) != Decimal("0.00")
        ):
            raise RuntimeError("Retail cashier shift did not close and reconcile cash")
    await verify_engine.dispose()


def run() -> None:
    context = asyncio.run(prepare())
    with TestClient(app) as client:
        login = expect(
            client.post(
                "/api/v1/auth/login",
                json={
                    "company_id": str(DEFAULT_COMPANY_ID),
                    "branch_id": context["branch_id"],
                    "username": context["username"],
                    "password": PASSWORD,
                },
            ),
            200,
            "retail owner login",
        )
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        me = expect(client.get("/api/v1/auth/me", headers=headers), 200, "retail auth context")
        if (
            me["business_type"] != "retail_pos"
            or me["target_database"] != "retail_pos"
            or "company" not in me["scope_types"]
            or me["brand_id"] != context["brand_id"]
        ):
            raise RuntimeError(f"Retail owner context is not canonical: {me}")

        expect(
            client.get("/api/v1/restaurant/tables", headers=headers),
            403,
            "retail owner restaurant boundary",
        )
        expect(
            client.get("/api/v1/platform/companies", headers=headers),
            401,
            "retail owner platform boundary",
        )
        shift = expect(
            client.post(
                "/api/v1/pos/shifts/open",
                headers=headers,
                json={"location_id": context["location_id"], "opening_cash": 0},
            ),
            201,
            "retail shift open",
        )
        sale_payload = {
            "shift_id": shift["id"],
            "location_id": context["location_id"],
            "items": [
                {
                    "product_id": context["product_id"],
                    "qty": 1,
                    "unit_price": 107,
                    "original_price": 107,
                    "discount_amount": 0,
                    "discount_type": "amount",
                    "vat_type": "included",
                    "vat_rate": 7,
                }
            ],
            "payment_method": "cash",
            "payments": [{"payment_method": "cash", "amount": 107}],
            "paid_amount": 107,
            "client_order_id": context["client_order_id"],
            "customer_name": "Retail Compatibility Customer",
        }
        first = expect(
            client.post("/api/v1/pos/sales", headers=headers, json=sale_payload),
            201,
            "retail sale",
        )
        duplicate = expect(
            client.post("/api/v1/pos/sales", headers=headers, json=sale_payload),
            200,
            "retail idempotent retry",
        )
        if duplicate["id"] != first["id"]:
            raise RuntimeError("Retail idempotent retry did not return the original sale")

        sales = expect(
            client.get(
                f"/api/v1/pos/sales?shift_id={shift['id']}",
                headers=headers,
            ),
            200,
            "retail sales list",
        )
        if [row["id"] for row in sales].count(first["id"]) != 1:
            raise RuntimeError("Retail sales list did not contain exactly one idempotent sale")
        balances = expect(
            client.get(
                f"/api/v1/stock/balances?branch_id={context['branch_id']}&location_id={context['location_id']}&product_id={context['product_id']}",
                headers=headers,
            ),
            200,
            "retail stock balance",
        )
        if len(balances) != 1 or Decimal(str(balances[0]["qty_on_hand"])) != Decimal("9"):
            raise RuntimeError("Retail stock API did not show the post-sale quantity")
        daily = expect(
            client.get(
                f"/api/v1/reports/sales/daily?date={datetime.now(ZoneInfo('Asia/Bangkok')).date().isoformat()}&branch_id={context['branch_id']}",
                headers=headers,
            ),
            200,
            "retail daily report",
        )
        if Decimal(str(daily["total_amount"])) != Decimal("107.00"):
            raise RuntimeError(f"Retail daily report did not reconcile: {daily}")
        closed = expect(
            client.post(
                f"/api/v1/pos/shifts/{shift['id']}/close",
                headers=headers,
                json={"closing_cash": 107, "note": "Retail compatibility close"},
            ),
            200,
            "retail shift close",
        )
        if closed["status"] != "closed" or Decimal(str(closed["cash_difference"])) != 0:
            raise RuntimeError("Retail close-shift response did not reconcile cash")

    asyncio.run(verify(context, first["id"], shift["id"]))
    print(
        "PASS: Retail POS compatibility smoke "
        f"business_type=retail_pos branch={context['branch_id']} sale={first['id']} "
        "total=107.00 stock=9 owner_scope=company restaurant_boundary=403 platform_boundary=401"
    )


if __name__ == "__main__":
    run()
