from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
import os
import uuid
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.config import settings
from app.database import (
    AsyncSessionLocal,
    PlatformSessionLocal,
    RetailSessionLocal,
    engine,
    platform_engine,
    retail_engine,
    retail_service_session_factory_for,
)
from app.main import app
from app.models.branch import Branch
from app.models.company import Company
from app.models.integration import OperationalOutboxEvent
from app.models.platform import CompanyReportingFact
from app.models.pos import CashierShift, Payment, SaleOrder
from app.models.product import (
    Category,
    PriceList,
    PriceListItem,
    Product,
    ProductImage,
    ProductVariant,
    Unit,
)
from app.models.restaurant import Brand, BrandBranch
from app.models.settings import BranchSettings
from app.models.stock import StockBalance, StockLocation, StockMovement
from app.models.user import User
from app.services.retail_migration_service import (
    RETAIL_OPERATIONAL_TABLES,
    migrate_retail_operational_data,
    reconcile_retail_operational_data,
)
from app.services.retail_reference_projector import (
    RETAIL_USER_PASSWORD_SENTINEL,
    project_retail_reference_snapshot,
    verify_retail_reference_parity,
)
from app.services.shared_reporting_service import process_reporting_source_batch
from app.utils.security import hash_password


PROJECT_PREFIX = "restaurant-wp8-retail"
PASSWORD = os.environ.get("WP8_RETAIL_SMOKE_PASSWORD", "")
BANGKOK = ZoneInfo("Asia/Bangkok")


def expect(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    payload = response.json()
    return payload.get("data", payload)


def _reference_rows(context: dict[str, uuid.UUID | str]) -> list[object]:
    return [
        Company(
            id=context["company_id"],
            name="WP8 Retail Canary",
            business_slug=context["business_slug"],
            phone="0812345678",
            is_active=True,
        ),
        Branch(
            id=context["branch_id"],
            company_id=context["company_id"],
            code="WP8-RET",
            name="WP8 Retail Branch",
            is_active=True,
        ),
        Brand(
            id=context["brand_id"],
            company_id=context["company_id"],
            central_branch_id=context["branch_id"],
            slug=context["brand_slug"],
            name="WP8 Retail Brand",
            business_type="retail_pos",
            storefront_mode="retail",
            theme_config={"canary": True},
            is_active=True,
        ),
        BrandBranch(
            id=context["brand_branch_id"],
            company_id=context["company_id"],
            brand_id=context["brand_id"],
            branch_id=context["branch_id"],
            branch_type="company_owned",
            is_active=True,
        ),
        User(
            id=context["user_id"],
            company_id=context["company_id"],
            username=context["username"],
            hashed_password=hash_password(PASSWORD),
            display_name="WP8 Retail Owner",
            is_active=True,
            is_superuser=True,
        ),
    ]


async def prepare() -> dict[str, str]:
    compose_project = os.environ.get("WP8_RETAIL_PROJECT_NAME", "")
    if not compose_project.startswith(PROJECT_PREFIX):
        raise RuntimeError("WP8 smoke refuses to write outside its isolated Compose project")
    if len(PASSWORD) < 16:
        raise RuntimeError("WP8 smoke requires a temporary password of at least 16 characters")
    if settings.identity_database != "platform_core":
        raise RuntimeError("WP8 canary requires Platform identity")
    if settings.retail_service_database != "retail":
        raise RuntimeError("WP8 canary requires Retail operational routing")
    if not settings.reference_projector_enabled or not settings.retail_reference_projector_enabled:
        raise RuntimeError("WP8 canary requires both reference projectors")
    if RetailSessionLocal is None or retail_engine is None:
        raise RuntimeError("WP8 canary requires an explicit Retail database")

    marker = uuid.uuid4().hex[:10]
    ids: dict[str, uuid.UUID | str] = {
        "company_id": uuid.uuid4(),
        "branch_id": uuid.uuid4(),
        "brand_id": uuid.uuid4(),
        "brand_branch_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "location_id": uuid.uuid4(),
        "unit_id": uuid.uuid4(),
        "category_id": uuid.uuid4(),
        "product_id": uuid.uuid4(),
        "variant_id": uuid.uuid4(),
        "price_list_id": uuid.uuid4(),
        "business_slug": f"wp8-retail-{marker}",
        "brand_slug": f"wp8-retail-brand-{marker}",
        "username": f"wp8-retail-owner-{marker}",
        "barcode": f"8858{marker[:8]}",
    }

    async with PlatformSessionLocal() as platform_db:
        platform_db.add_all(_reference_rows(ids))
        await platform_db.commit()

    async with AsyncSessionLocal() as legacy_db:
        legacy_rows = _reference_rows(ids)
        legacy_db.add_all(legacy_rows)
        await legacy_db.flush()
        location = StockLocation(
            id=ids["location_id"],
            company_id=ids["company_id"],
            branch_id=ids["branch_id"],
            code="STORE",
            name="Retail Store",
            is_active=True,
        )
        unit = Unit(
            id=ids["unit_id"],
            company_id=ids["company_id"],
            code="piece",
            name="ชิ้น",
            decimal_places=0,
            is_active=True,
        )
        category = Category(
            id=ids["category_id"],
            company_id=ids["company_id"],
            code="GENERAL",
            name="สินค้าทั่วไป",
            is_active=True,
        )
        price_list = PriceList(
            id=ids["price_list_id"],
            company_id=ids["company_id"],
            name="ราคาหน้าร้าน",
            valid_from=date(2026, 1, 1),
            is_default=True,
            is_active=True,
        )
        legacy_db.add_all([location, unit, category, price_list])
        await legacy_db.flush()
        product = Product(
            id=ids["product_id"],
            company_id=ids["company_id"],
            brand_id=ids["brand_id"],
            category_id=ids["category_id"],
            unit_id=ids["unit_id"],
            sku=f"WP8-SKU-{marker}",
            barcode=ids["barcode"],
            name="WP8 Retail Product",
            product_type="simple",
            cost_price=Decimal("40"),
            selling_price=Decimal("107"),
            vat_type="included",
            vat_rate=Decimal("7"),
            is_active=True,
            is_for_sale=True,
            is_for_purchase=True,
        )
        legacy_db.add(product)
        await legacy_db.flush()
        legacy_db.add_all(
            [
                ProductVariant(
                    id=ids["variant_id"],
                    company_id=ids["company_id"],
                    product_id=ids["product_id"],
                    sku=f"WP8-VAR-{marker}",
                    barcode=f"8859{marker[:8]}",
                    name="แพ็กทดสอบ",
                    selling_price=Decimal("214"),
                    is_active=True,
                ),
                ProductImage(
                    company_id=ids["company_id"],
                    product_id=ids["product_id"],
                    url="/uploads/wp8-retail-canary.png",
                    filename="wp8-retail-canary.png",
                    is_primary=True,
                ),
                PriceListItem(
                    company_id=ids["company_id"],
                    price_list_id=ids["price_list_id"],
                    product_id=ids["product_id"],
                    price=Decimal("107"),
                    min_qty=Decimal("1"),
                ),
                StockBalance(
                    company_id=ids["company_id"],
                    branch_id=ids["branch_id"],
                    location_id=ids["location_id"],
                    product_id=ids["product_id"],
                    qty_on_hand=Decimal("20"),
                    qty_reserved=Decimal("0"),
                    cost_per_unit=Decimal("40"),
                ),
                BranchSettings(
                    company_id=ids["company_id"],
                    branch_id=ids["branch_id"],
                    pos_default_price_list_id=ids["price_list_id"],
                    pos_receipt_header="WP8 Retail Canary",
                    pos_receipt_footer="Thank you",
                ),
            ]
        )
        brand = next(row for row in legacy_rows if isinstance(row, Brand))
        brand.central_location_id = ids["location_id"]
        brand.central_ready_location_id = ids["location_id"]
        brand_branch = next(row for row in legacy_rows if isinstance(row, BrandBranch))
        brand_branch.store_location_id = ids["location_id"]
        await legacy_db.commit()

    first_projection = await project_retail_reference_snapshot(
        company_id=ids["company_id"],
    )
    second_projection = await project_retail_reference_snapshot(
        company_id=ids["company_id"],
    )
    if first_projection.applied != 5 or second_projection.unchanged != 5:
        raise RuntimeError(
            "Retail reference projection was not complete and idempotent: "
            f"{first_projection}/{second_projection}"
        )
    reference_parity = await verify_retail_reference_parity(company_id=ids["company_id"])
    if any(row[0] != row[1] or row[2] for row in reference_parity.values()):
        raise RuntimeError(f"Retail reference parity failed: {reference_parity}")

    # A receipt alone must not hide target drift; the projector must repair it.
    async with RetailSessionLocal() as retail_db:
        await retail_db.execute(
            text("UPDATE branches SET name = 'DRIFT' WHERE id = :branch_id"),
            {"branch_id": ids["branch_id"]},
        )
        await retail_db.commit()
    drifted_parity = await verify_retail_reference_parity(company_id=ids["company_id"])
    if not drifted_parity["branch"][2]:
        raise RuntimeError("Retail reference parity did not detect target row drift")
    repaired_projection = await project_retail_reference_snapshot(
        company_id=ids["company_id"],
    )
    repaired_parity = await verify_retail_reference_parity(company_id=ids["company_id"])
    if repaired_projection.applied != 1 or any(
        row[0] != row[1] or row[2] for row in repaired_parity.values()
    ):
        raise RuntimeError("Retail reference projector did not repair target row drift")

    first_migration = await migrate_retail_operational_data(company_id=ids["company_id"])
    second_migration = await migrate_retail_operational_data(company_id=ids["company_id"])
    _, parity = await reconcile_retail_operational_data(company_id=ids["company_id"])
    if len(first_migration.table_parity) != len(RETAIL_OPERATIONAL_TABLES):
        raise RuntimeError("Retail operational manifest was not fully reconciled")
    if any(not row.matches for row in second_migration.table_parity + parity):
        raise RuntimeError("Retail operational migration replay did not reconcile")

    async with RetailSessionLocal() as retail_db:
        target_password = await retail_db.scalar(
            select(User.hashed_password).where(User.id == ids["user_id"])
        )
        target_link = await retail_db.get(BrandBranch, ids["brand_branch_id"])
        target_brand = await retail_db.get(Brand, ids["brand_id"])
        completed_runs = int(
            await retail_db.scalar(
                text(
                    "SELECT count(*) FROM retail_migration_runs "
                    "WHERE company_id = :company_id AND status = 'completed'"
                ),
                {"company_id": ids["company_id"]},
            )
            or 0
        )
        if target_password != RETAIL_USER_PASSWORD_SENTINEL:
            raise RuntimeError("Retail reference projection copied an authentication credential")
        if target_link is None or target_link.store_location_id != ids["location_id"]:
            raise RuntimeError("Retail Brand/Branch operational location was not restored")
        if target_brand is None or target_brand.central_location_id != ids["location_id"]:
            raise RuntimeError("Retail Brand operational location was not restored")
        if completed_runs != 2:
            raise RuntimeError("Retail migration replay was not recorded exactly twice")

    await asyncio.gather(engine.dispose(), platform_engine.dispose(), retail_engine.dispose())
    return {key: str(value) for key, value in ids.items()}


def run_sales(context: dict[str, str]) -> tuple[str, list[str]]:
    with TestClient(app) as client:
        login = expect(
            client.post(
                "/api/v1/auth/login",
                json={
                    "company_id": context["company_id"],
                    "branch_id": context["branch_id"],
                    "username": context["username"],
                    "password": PASSWORD,
                },
            ),
            200,
            "Retail Platform login",
        )
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        me = expect(client.get("/api/v1/auth/me", headers=headers), 200, "Retail auth context")
        if (
            me["business_type"] != "retail_pos"
            or me["target_database"] != "retail_pos"
            or me["brand_id"] != context["brand_id"]
        ):
            raise RuntimeError(f"Retail signed context is not canonical: {me}")

        expect(
            client.get("/api/v1/restaurant/tables", headers=headers),
            403,
            "Retail to Restaurant boundary",
        )
        expect(
            client.get("/api/v1/platform/companies", headers=headers),
            401,
            "Retail to Platform operator boundary",
        )
        products = expect(
            client.get(f"/api/v1/products?search={context['barcode']}", headers=headers),
            200,
            "Retail barcode search",
        )
        if [row["id"] for row in products] != [context["product_id"]]:
            raise RuntimeError(f"Retail barcode did not select the migrated product: {products}")

        shift = expect(
            client.post(
                "/api/v1/pos/shifts/open",
                headers=headers,
                json={"location_id": context["location_id"], "opening_cash": 0},
            ),
            201,
            "Retail shift open",
        )

        order_ids: list[str] = []
        for index in range(1, 4):
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
                "client_order_id": f"wp8-retail-sale-{index}-{context['product_id']}",
                "customer_name": "WP8 Retail Customer",
            }
            sale = expect(
                client.post("/api/v1/pos/sales", headers=headers, json=sale_payload),
                201,
                f"Retail sale {index}",
            )
            replay = expect(
                client.post("/api/v1/pos/sales", headers=headers, json=sale_payload),
                200,
                f"Retail sale replay {index}",
            )
            if replay["id"] != sale["id"]:
                raise RuntimeError("Retail sale idempotency returned a different order")
            receipt = expect(
                client.get(f"/api/v1/pos/sales/{sale['id']}", headers=headers),
                200,
                f"Retail receipt source {index}",
            )
            if receipt["payments"][0]["amount"] != "107.00":
                raise RuntimeError(f"Retail receipt payment is incorrect: {receipt}")
            order_ids.append(sale["id"])

        refunded = expect(
            client.post(
                f"/api/v1/pos/sales/{order_ids[1]}/refund",
                headers=headers,
                json={"refund_reason": "WP8 canary full refund"},
            ),
            200,
            "Retail full refund",
        )
        if refunded["status"] != "refunded" or refunded["refund_amount"] != "107.00":
            raise RuntimeError(f"Retail refund did not reconcile: {refunded}")

        voided = expect(
            client.post(
                f"/api/v1/pos/sales/{order_ids[2]}/void",
                headers=headers,
                json={"void_reason": "WP8 canary void"},
            ),
            200,
            "Retail void",
        )
        if voided["status"] != "voided":
            raise RuntimeError(f"Retail void did not reconcile: {voided}")

        balances = expect(
            client.get(
                "/api/v1/stock/balances"
                f"?branch_id={context['branch_id']}"
                f"&location_id={context['location_id']}"
                f"&product_id={context['product_id']}",
                headers=headers,
            ),
            200,
            "Retail stock after sale/refund/void",
        )
        if len(balances) != 1 or Decimal(str(balances[0]["qty_on_hand"])) != Decimal("19"):
            raise RuntimeError(f"Retail stock did not reconcile to 19: {balances}")

        today = datetime.now(BANGKOK).date().isoformat()
        daily = expect(
            client.get(
                f"/api/v1/reports/sales/daily?date={today}&branch_id={context['branch_id']}",
                headers=headers,
            ),
            200,
            "Retail daily report",
        )
        if Decimal(str(daily["total_amount"])) != Decimal("107.00"):
            raise RuntimeError(f"Retail daily report did not reconcile: {daily}")

        closed = expect(
            client.post(
                f"/api/v1/pos/shifts/{shift['id']}/close",
                headers=headers,
                json={"closing_cash": 107, "note": "WP8 retail canary close"},
            ),
            200,
            "Retail shift close",
        )
        if closed["status"] != "closed" or Decimal(str(closed["cash_difference"])) != 0:
            raise RuntimeError(f"Retail shift did not reconcile: {closed}")
    return shift["id"], order_ids


async def verify_runtime(
    context: dict[str, str],
    shift_id: str,
    order_ids: list[str],
) -> None:
    if RetailSessionLocal is None:
        raise RuntimeError("Retail database is unavailable")
    async with RetailSessionLocal() as retail_db, PlatformSessionLocal() as platform_db:
        batch = await process_reporting_source_batch(
            retail_db,
            platform_db,
            source_stream="retail_pos",
            source_kind="legacy",
            limit=100,
        )
        if batch.failed or batch.dead_lettered or batch.projected != 5:
            raise RuntimeError(f"Retail shared-report projection failed: {batch}")

    async with RetailSessionLocal() as retail_db:
        orders = list(
            await retail_db.scalars(
                select(SaleOrder).where(
                    SaleOrder.id.in_([uuid.UUID(value) for value in order_ids])
                )
            )
        )
        payment_count = int(
            await retail_db.scalar(
                select(func.count(Payment.id)).where(
                    Payment.order_id.in_([uuid.UUID(value) for value in order_ids])
                )
            )
            or 0
        )
        movement_count = int(
            await retail_db.scalar(
                select(func.count(StockMovement.id)).where(
                    StockMovement.reference_type == "SaleOrder",
                    StockMovement.reference_id.in_(order_ids),
                )
            )
            or 0
        )
        outbox_count = int(
            await retail_db.scalar(
                select(func.count(OperationalOutboxEvent.id)).where(
                    OperationalOutboxEvent.aggregate_id.in_(
                        [uuid.UUID(value) for value in order_ids]
                    )
                )
            )
            or 0
        )
        balance = await retail_db.scalar(
            select(StockBalance).where(
                StockBalance.location_id == uuid.UUID(context["location_id"]),
                StockBalance.product_id == uuid.UUID(context["product_id"]),
            )
        )
        shift = await retail_db.get(CashierShift, uuid.UUID(shift_id))
        statuses = sorted(order.status for order in orders)
        if statuses != ["completed", "refunded", "voided"]:
            raise RuntimeError(f"Retail final order states are incorrect: {statuses}")
        if payment_count != 4 or movement_count != 5 or outbox_count != 5:
            raise RuntimeError(
                "Retail transaction counts are incorrect: "
                f"payments={payment_count} movements={movement_count} outbox={outbox_count}"
            )
        if balance is None or Decimal(balance.qty_on_hand) != Decimal("19"):
            raise RuntimeError("Retail target stock does not equal 19")
        if (
            shift is None
            or shift.status != "closed"
            or Decimal(shift.expected_cash or 0) != Decimal("107.00")
            or Decimal(shift.cash_difference or 0) != Decimal("0.00")
        ):
            raise RuntimeError("Retail target cashier shift did not reconcile")

    async with AsyncSessionLocal() as legacy_db:
        legacy_order_count = int(
            await legacy_db.scalar(
                select(func.count(SaleOrder.id)).where(
                    SaleOrder.client_order_id.like("wp8-retail-sale-%")
                )
            )
            or 0
        )
        legacy_balance = await legacy_db.scalar(
            select(StockBalance).where(
                StockBalance.location_id == uuid.UUID(context["location_id"]),
                StockBalance.product_id == uuid.UUID(context["product_id"]),
            )
        )
        if legacy_order_count != 0 or legacy_balance is None:
            raise RuntimeError("Retail cutover wrote sale data back to Legacy")
        if Decimal(legacy_balance.qty_on_hand) != Decimal("20"):
            raise RuntimeError("Retail cutover changed Legacy stock")

    async with PlatformSessionLocal() as platform_db:
        facts = list(
            await platform_db.scalars(
                select(CompanyReportingFact).where(
                    CompanyReportingFact.company_id == uuid.UUID(context["company_id"]),
                    CompanyReportingFact.module_key == "retail_pos",
                )
            )
        )
        if len(facts) != 3:
            raise RuntimeError(f"Shared ERP report expected 3 Retail documents, got {len(facts)}")
        if sum((Decimal(fact.net_sales) for fact in facts), Decimal("0")) != Decimal("107.00"):
            raise RuntimeError("Shared ERP Retail net sales did not reconcile to 107.00")

    if retail_service_session_factory_for("legacy") is not AsyncSessionLocal:
        raise RuntimeError("Retail rollback no longer resolves to the Legacy database")


def run() -> None:
    context = asyncio.run(prepare())
    shift_id, order_ids = run_sales(context)
    # TestClient owns a dedicated event loop. Drop its pooled connections before
    # the final asyncio.run so asyncpg never reuses a connection across loops.
    for database_engine in (engine, platform_engine, retail_engine):
        if database_engine is not None:
            database_engine.sync_engine.dispose(close=False)
    asyncio.run(verify_runtime(context, shift_id, order_ids))
    print(
        "PASS: WP8 Retail selective migration and local canary "
        "reference_projection=exact migration_replay=exact barcode=passed "
        "sale_refund_void_stock_report=passed legacy_isolated=true rollback=legacy"
    )


if __name__ == "__main__":
    run()
