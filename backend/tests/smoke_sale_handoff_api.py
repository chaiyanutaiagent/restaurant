from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
import os
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.main import app
from app.models.accounting import Account, JournalEntry
from app.models.hr import Employee
from app.models.integration import OperationalOutboxEvent
from app.models.pos import Payment, SaleOrder
from app.models.product import Product, Unit
from app.models.restaurant import Brand, BrandBranch
from app.models.role import Permission, Role
from app.models.staff_assignment import StaffRoleAssignment
from app.models.stock import StockBalance, StockLocation, StockMovement
from app.models.user import User
from app.utils.create_superuser import DEFAULT_COMPANY_ID, ensure_default_company_seed_in_session
from app.utils.seed_permissions import seed_default_permissions
from app.utils.security import hash_password


DATABASE_PREFIX = "restaurant_p4_core_"
PASSWORD = "P4HandoffSmoke123!"


def expect(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    return response.json()["data"]


async def prepare() -> dict[str, str]:
    configured_database = os.environ.get("P4_CORE_DATABASE_NAME", "")
    if not configured_database.startswith(DATABASE_PREFIX):
        raise RuntimeError("Phase 4 sale handoff smoke refuses to write a non-Phase-4 database")
    marker = uuid.uuid4().hex[:8]
    test_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as db:
        actual_database = await db.scalar(func.current_database())
        if actual_database != configured_database:
            raise RuntimeError(f"Phase 4 database mismatch: {actual_database} != {configured_database}")
        await seed_default_permissions(db)
        await ensure_default_company_seed_in_session(db)
        membership = await db.scalar(
            select(BrandBranch).where(
                BrandBranch.company_id == DEFAULT_COMPANY_ID,
                BrandBranch.is_active.is_(True),
            )
        )
        if membership is None:
            raise RuntimeError("Restaurant Brand/Branch fixture is missing")
        brand = await db.get(Brand, membership.brand_id)
        location = await db.scalar(
            select(StockLocation).where(
                StockLocation.company_id == DEFAULT_COMPANY_ID,
                StockLocation.branch_id == membership.branch_id,
                StockLocation.is_active.is_(True),
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
        if brand is None or location is None:
            raise RuntimeError("Restaurant sale fixture is incomplete")
        product = Product(
            company_id=DEFAULT_COMPANY_ID,
            brand_id=brand.id,
            unit_id=unit.id,
            sku=f"P4-SALE-{marker}",
            name="P4 Handoff Product",
            product_type="simple",
            cost_price=Decimal("20"),
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
                branch_id=membership.branch_id,
                location_id=location.id,
                product_id=product.id,
                variant_id=None,
                qty_on_hand=Decimal("10"),
                qty_reserved=Decimal("0"),
                cost_per_unit=Decimal("20"),
            )
        )
        permissions = list(
            (
                await db.scalars(
                    select(Permission).where(
                        Permission.code.in_(["pos.cashier.open_shift", "pos.sale.create"])
                    )
                )
            ).all()
        )
        if {permission.code for permission in permissions} != {
            "pos.cashier.open_shift",
            "pos.sale.create",
        }:
            raise RuntimeError("POS handoff permissions are missing")
        role = Role(
            company_id=DEFAULT_COMPANY_ID,
            name=f"p4_handoff_{marker}",
            is_branch_assignable=True,
        )
        role.permissions = permissions
        user = User(
            company_id=DEFAULT_COMPANY_ID,
            username=f"p4-handoff-{marker}",
            hashed_password=hash_password(PASSWORD),
            display_name="P4 Handoff Cashier",
            is_active=True,
        )
        db.add_all([role, user])
        await db.flush()
        db.add_all(
            [
                Employee(
                    company_id=DEFAULT_COMPANY_ID,
                    branch_id=membership.branch_id,
                    user_id=user.id,
                    employee_code=f"P4-SALE-{marker}"[:20],
                    first_name="P4",
                    last_name="Handoff Cashier",
                    hire_date=date.today(),
                    is_active=True,
                ),
                StaffRoleAssignment(
                    company_id=DEFAULT_COMPANY_ID,
                    user_id=user.id,
                    role_id=role.id,
                    scope_type="branch",
                    scope_key=str(membership.branch_id),
                    brand_id=brand.id,
                    branch_id=membership.branch_id,
                    station_key=None,
                    assignment_reason="Phase 4 sale handoff smoke",
                    assigned_by=user.id,
                ),
            ]
        )
        cash_account = await db.scalar(
            select(Account).where(
                Account.company_id == DEFAULT_COMPANY_ID,
                Account.code == "1101",
                Account.deleted_at.is_(None),
            )
        )
        if cash_account is None:
            raise RuntimeError("Default cash account is missing")
        cash_account.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        context = {
            "brand_id": str(brand.id),
            "branch_id": str(membership.branch_id),
            "location_id": str(location.id),
            "product_id": str(product.id),
            "cash_account_id": str(cash_account.id),
            "client_order_id": f"p4-handoff-{marker}",
            "username": user.username,
        }
    await test_engine.dispose()
    return context


async def restore_cash_account(context: dict[str, str]) -> None:
    test_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as db:
        account = await db.get(Account, uuid.UUID(context["cash_account_id"]))
        if account is None:
            raise RuntimeError("Cash account disappeared")
        account.deleted_at = None
        await db.commit()
    await test_engine.dispose()


async def verify(context: dict[str, str], order_id: str) -> None:
    test_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as db:
        filters = [
            SaleOrder.company_id == DEFAULT_COMPANY_ID,
            SaleOrder.client_order_id == context["client_order_id"],
        ]
        order_count = await db.scalar(select(func.count(SaleOrder.id)).where(*filters))
        payment_count = await db.scalar(
            select(func.count(Payment.id)).where(Payment.order_id == uuid.UUID(order_id))
        )
        movement_count = await db.scalar(
            select(func.count(StockMovement.id)).where(
                StockMovement.reference_type == "SaleOrder",
                StockMovement.reference_id == order_id,
                StockMovement.movement_type == "sale",
            )
        )
        event_rows = list(
            (
                await db.scalars(
                    select(OperationalOutboxEvent).where(
                        OperationalOutboxEvent.aggregate_id == uuid.UUID(order_id)
                    )
                )
            ).all()
        )
        journal_count = await db.scalar(
            select(func.count(JournalEntry.id)).where(
                JournalEntry.company_id == DEFAULT_COMPANY_ID,
                JournalEntry.entry_type == "sale",
                JournalEntry.reference_type == "SaleOrder",
                JournalEntry.reference_id == order_id,
            )
        )
        if (order_count, payment_count, movement_count, len(event_rows), journal_count) != (1, 1, 1, 1, 1):
            raise RuntimeError(
                "Sale handoff was not exactly once: "
                f"{order_count}/{payment_count}/{movement_count}/{len(event_rows)}/{journal_count}"
            )
        event = event_rows[0]
        if (
            event.event_type != "restaurant.sale.completed.v1"
            or str(event.brand_id) != context["brand_id"]
            or event.payload.get("total_amount") != "107.00"
        ):
            raise RuntimeError(f"Sale handoff contract is invalid: {event.payload}")
    await test_engine.dispose()


def run() -> None:
    context = asyncio.run(prepare())
    with TestClient(app) as client:
        login = expect(
            client.post(
                "/api/v1/auth/login",
                json={
                    "company_id": str(DEFAULT_COMPANY_ID),
                    "username": context["username"],
                    "password": PASSWORD,
                    "branch_id": context["branch_id"],
                },
            ),
            200,
            "admin login",
        )
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        shift = expect(
            client.post(
                "/api/v1/pos/shifts/open",
                headers=headers,
                json={"location_id": context["location_id"], "opening_cash": 0},
            ),
            201,
            "open shift",
        )
        payload = {
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
        }
        first = expect(
            client.post("/api/v1/pos/sales", headers=headers, json=payload),
            201,
            "first sale",
        )
        asyncio.run(restore_cash_account(context))
        duplicate = expect(
            client.post("/api/v1/pos/sales", headers=headers, json=payload),
            200,
            "duplicate sale repair",
        )
        if duplicate["id"] != first["id"]:
            raise RuntimeError("Duplicate sale did not return the original order")
    asyncio.run(verify(context, first["id"]))


if __name__ == "__main__":
    run()
