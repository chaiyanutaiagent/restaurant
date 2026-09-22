from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any, Sequence, TypeVar
import uuid
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal, PlatformSessionLocal, RetailSessionLocal, TakeawaySessionLocal
from app.dependencies import TokenData
from app.models.accounting import Account, JournalEntry, JournalLine
from app.models.api_integration import APIKey, ExternalOrder, WebhookDelivery, WebhookEndpoint
from app.models.branch import Branch
from app.models.company import Company
from app.models.crm import Customer, CustomerTag, CustomerTagAssignment, CustomerTier, PointsTransaction
from app.models.device import DeviceRegistration
from app.models.distribution import CompanyDistributionDemand, CompanyDistributionEvent, CompanyDistributionShipment
from app.models.hr import (
    AttendanceRecord,
    Department,
    Employee,
    EmployeeSalary,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    PayrollItem,
    PayrollItemLine,
    PayrollRun,
    Position,
    SalaryComponent,
    WorkSchedule,
)
from app.models.logistics import Carrier, Shipment, ShipmentEvent, ShipmentItem
from app.models.platform import PlatformOperationsSnapshot, PlatformOperator, PlatformTenantUsageSnapshot
from app.models.pos import CashierShift, Payment, SaleOrder, SaleOrderItem
from app.models.product import Category, PriceList, PriceListItem, Product, Unit
from app.models.purchase import GoodsReceipt, GoodsReceiptItem, PurchaseOrder, PurchaseOrderItem, Supplier
from app.models.restaurant import (
    Brand,
    BrandBranch,
    DiningOrder,
    DiningOrderItem,
    DiningSession,
    DiningTable,
    KitchenTicket,
    Recipe,
)
from app.models.shared_kitchen import (
    CompanyIngredient,
    CompanyIngredientLot,
    CompanyKitchen,
    CompanyKitchenMovement,
    CompanyProductionDemand,
    CompanyProductionInput,
    CompanyProductionOrder,
)
from app.models.saas_billing import SaasBillingEvent, SaasInvoice, SaasPlan, SaasSubscription
from app.models.saas_privacy_support import SaasPrivacyRequest, SaasSupportMessage, SaasSupportTicket
from app.models.stock import StockBalance, StockLocation, StockMovement
from app.models.stock_count import StockCountItem, StockCountSession
from app.models.takeaway import (
    TakeawayBranchCatalogItem,
    TakeawayCatalogItem,
    TakeawayCategory,
    TakeawayCentralOrder,
    TakeawayCentralOrderItem,
    TakeawayCentralOrderRound,
    TakeawayCreditAccount,
    TakeawayCreditEntry,
    TakeawayKitchenTicket,
    TakeawayOrder,
    TakeawayOrderItem,
    TakeawayPayment,
    TakeawayPickupToken,
    TakeawayProductionBatch,
    TakeawayProductionLine,
    TakeawayReceipt,
    TakeawayShift,
    TakeawayStockBalance,
    TakeawayStockLocation,
    TakeawayStockMovement,
    TakeawayTransfer,
    TakeawayTransferItem,
    TakeawayUnit,
)
from app.utils.integration_security import encrypt_integration_secret
from app.models.transfer import TransferOrder, TransferOrderItem
from app.models.user import User
from app.schemas.company_workspace import CompanyWorkspaceProvisionRequest
from app.services.company_workspace_service import CompanyWorkspaceService
from app.services.platform_reference_projection import process_projection_batch, seed_snapshot_events, verify_projection_parity
from app.services.retail_reference_projector import project_retail_reference_snapshot, verify_retail_reference_parity
from app.services.takeaway_reference_projector import project_takeaway_reference_snapshot, verify_takeaway_reference_parity
from app.utils.seed_accounts import seed_default_accounts
from app.utils.seed_crm import seed_default_tiers, seed_loyalty_settings
from app.utils.seed_fnb_demo import seed_fnb_demo_menu
from app.utils.seed_hr import (
    seed_default_hr_components,
    seed_default_leave_types,
    seed_default_work_schedule,
    seed_public_holidays_2026,
)
from app.utils.seed_logistics import seed_default_carriers, seed_default_shipping_rates


SHOWCASE_NAMESPACE = uuid.UUID("3e156ada-5c9e-4ba4-a060-824de21df13a")
SHOWCASE_PREFIX = "UI-DEMO"
ModelT = TypeVar("ModelT")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed an idempotent, non-production UI showcase dataset.")
    parser.add_argument("--company-id", type=uuid.UUID, required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--yes", action="store_true")
    return parser


def require_uat(args: argparse.Namespace) -> None:
    hostname = urlsplit(settings.saas_public_base_url).hostname or ""
    if not args.yes:
        raise RuntimeError("Pass --yes to seed persistent UI showcase data")
    if settings.environment != "development" or not hostname.startswith("uat-"):
        raise RuntimeError("UI showcase seeding is restricted to the HTTPS uat-* development environment")
    if settings.identity_database != "platform_core":
        raise RuntimeError("UI showcase seeding requires Platform identity")
    if settings.restaurant_service_database != "legacy":
        raise RuntimeError("This UAT showcase currently expects Restaurant runtime on Legacy")
    if settings.retail_service_database != "retail" or RetailSessionLocal is None:
        raise RuntimeError("UI showcase seeding requires the dedicated Retail UAT database")
    if not settings.takeaway_feature_enabled or TakeawaySessionLocal is None:
        raise RuntimeError("UI showcase seeding requires the dedicated Takeaway UAT database")


def fixture_id(group: str, key: str) -> uuid.UUID:
    return uuid.uuid5(SHOWCASE_NAMESPACE, f"{group}:{key}")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def put(
    db: AsyncSession,
    model: type[ModelT],
    group: str,
    key: str,
    **values: Any,
) -> tuple[ModelT, bool]:
    object_id = fixture_id(group, key)
    row = await db.get(model, object_id)
    created = row is None
    if row is None:
        row = model(id=object_id, **values)
        db.add(row)
    else:
        for field, value in values.items():
            setattr(row, field, value)
    await db.flush()
    return row, created


def count(summary: dict[str, int], key: str, amount: int = 1) -> None:
    summary[key] = summary.get(key, 0) + amount


async def require_platform_context(company_id: uuid.UUID, username: str) -> tuple[Company, User]:
    async with PlatformSessionLocal() as db:
        company = await db.get(Company, company_id)
        user = await db.scalar(
            select(User).where(
                User.company_id == company_id,
                User.username == username,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        if company is None or not company.is_active:
            raise RuntimeError("Active UAT Company was not found")
        if user is None or not user.is_superuser:
            raise RuntimeError("Active UAT superuser was not found")
        return company, user


async def provision_restaurant_showcase_branch(company_id: uuid.UUID, user_id: uuid.UUID) -> None:
    current = TokenData(
        user_id=user_id,
        company_id=company_id,
        branch_id=None,
        brand_id=None,
        business_type=None,
        target_database=None,
        permissions=["*"],
        scope_types=["company"],
    )
    async with PlatformSessionLocal() as db:
        brand = await db.scalar(
            select(Brand).where(
                Brand.company_id == company_id,
                Brand.business_type == "restaurant",
                Brand.is_active.is_(True),
            )
        )
        if brand is None:
            raise RuntimeError("Restaurant UAT Brand was not found")
        await CompanyWorkspaceService(db).provision(
            current,
            CompanyWorkspaceProvisionRequest(
                idempotency_key="ui-showcase-restaurant-branch-v1",
                module_key="restaurant_pos",
                brand_slug=brand.slug,
                brand_name=brand.name,
                branch_code="BKK-UI-02",
                branch_name="สาขาสาธิต UI",
                branch_type="company_owned",
                storefront_mode=brand.storefront_mode,
            ),
            ip_address=None,
            user_agent="seed-ui-showcase",
        )


async def project_references(company_id: uuid.UUID) -> dict[str, int]:
    async with PlatformSessionLocal() as db:
        seeded = await seed_snapshot_events(db)
        await db.commit()
    applied = failed = 0
    while True:
        batch = await process_projection_batch(limit=100)
        applied += batch.applied
        failed += batch.failed
        if batch.claimed == 0 or batch.failed:
            break
    parity = await verify_projection_parity()
    if failed or any(not row.matches for row in parity):
        raise RuntimeError("Platform reference projection failed while preparing UI showcase")
    retail = await project_retail_reference_snapshot(company_id=company_id)
    retail_parity = await verify_retail_reference_parity(company_id=company_id)
    if any(source != target or mismatches for source, target, mismatches in retail_parity.values()):
        raise RuntimeError("Retail reference parity failed while preparing UI showcase")
    takeaway = await project_takeaway_reference_snapshot()
    takeaway_parity = await verify_takeaway_reference_parity()
    if any(source != target or mismatches for source, target, mismatches in takeaway_parity.values()):
        raise RuntimeError("Takeaway reference parity failed while preparing UI showcase")
    return {
        "platform_seeded": seeded,
        "platform_applied": applied,
        "retail_applied": retail.applied,
        "takeaway_applied": takeaway.applied,
    }


async def platform_reference_snapshot(company_id: uuid.UUID) -> dict[str, list[dict[str, Any]]]:
    async with PlatformSessionLocal() as db:
        branches = (
            await db.scalars(select(Branch).where(Branch.company_id == company_id, Branch.deleted_at.is_(None)))
        ).all()
        brands = (await db.scalars(select(Brand).where(Brand.company_id == company_id))).all()
        links = (await db.scalars(select(BrandBranch).where(BrandBranch.company_id == company_id))).all()
        return {
            "branches": [
                {
                    "id": row.id,
                    "code": row.code,
                    "name": row.name,
                    "is_warehouse": row.is_warehouse,
                    "is_active": row.is_active,
                    "sort_order": row.sort_order,
                }
                for row in branches
            ],
            "brands": [
                {
                    "id": row.id,
                    "central_branch_id": row.central_branch_id,
                    "slug": row.slug,
                    "name": row.name,
                    "business_type": row.business_type,
                    "storefront_mode": row.storefront_mode,
                    "theme_config": row.theme_config or {},
                    "is_active": row.is_active,
                }
                for row in brands
            ],
            "links": [
                {
                    "id": row.id,
                    "brand_id": row.brand_id,
                    "branch_id": row.branch_id,
                    "branch_type": row.branch_type,
                    "is_active": row.is_active,
                }
                for row in links
            ],
        }


async def seed_platform_showcase(company_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, int]:
    summary: dict[str, int] = {}
    now = utc_now()
    async with PlatformSessionLocal() as db:
        plan = await db.scalar(select(SaasPlan).where(SaasPlan.code == "uat-multibusiness"))
        if plan is None:
            raise RuntimeError("UAT multi-business plan was not found")
        subscription, _ = await put(
            db,
            SaasSubscription,
            "platform-subscription",
            "active",
            company_id=company_id,
            plan_id=plan.id,
            status="active",
            current_period_start=now - timedelta(days=16),
            current_period_end=now + timedelta(days=15),
            cancel_at_period_end=False,
        )
        count(summary, "subscriptions")
        invoice_rows = [
            ("paid", "paid", 290000, 20300, 310300, 310300, now - timedelta(days=42), now - timedelta(days=35)),
            ("open", "open", 290000, 20300, 310300, 0, now - timedelta(days=12), None),
            ("draft", "draft", 150000, 10500, 160500, 0, now, None),
        ]
        for key, status_value, subtotal, tax, total, paid, issued, paid_at in invoice_rows:
            invoice, _ = await put(
                db,
                SaasInvoice,
                "platform-invoice",
                key,
                subscription_id=subscription.id,
                company_id=company_id,
                invoice_number=f"UI-SAAS-2026-{key.upper()}",
                status=status_value,
                currency="THB",
                subtotal_satang=subtotal,
                tax_satang=tax,
                total_satang=total,
                paid_satang=paid,
                period_start=issued,
                period_end=issued + timedelta(days=30),
                due_at=issued + timedelta(days=14),
                paid_at=paid_at,
                memo="ข้อมูลตัวอย่างสำหรับจัด UI เท่านั้น",
                created_at=issued,
            )
            count(summary, "invoices")
            await put(
                db,
                SaasBillingEvent,
                "platform-billing-event",
                key,
                event_key=f"ui-showcase-billing-{key}",
                event_type="invoice.paid" if status_value == "paid" else "invoice.opened",
                source="ui_showcase",
                company_id=company_id,
                subscription_id=subscription.id,
                invoice_id=invoice.id,
                amount_satang=total,
                currency="THB",
                occurred_at=issued,
                processed_at=issued,
                result_status="applied",
                payload_sha256=digest(f"billing:{key}"),
                created_at=issued,
            )
            count(summary, "billing_events")

        tickets = [
            ("OPEN", "technical", "high", "open", "หน้าจอ KDS ต้องการปรับขนาดตัวอักษร"),
            ("WAIT", "billing", "normal", "waiting_tenant", "ขอตรวจสอบรายละเอียดใบแจ้งหนี้"),
            ("DONE", "account", "low", "resolved", "เพิ่มผู้จัดการสาขาเรียบร้อย"),
        ]
        for index, (key, category, priority, status_value, subject) in enumerate(tickets, start=1):
            ticket, _ = await put(
                db,
                SaasSupportTicket,
                "platform-ticket",
                key,
                ticket_number=f"UI-SUP-2026-{index:03d}",
                company_id=company_id,
                requester_user_id=user_id,
                category=category,
                priority=priority,
                status=status_value,
                subject=subject,
                closed_at=now - timedelta(days=1) if status_value == "resolved" else None,
                created_at=now - timedelta(days=index),
            )
            await put(
                db,
                SaasSupportMessage,
                "platform-ticket-message",
                key,
                ticket_id=ticket.id,
                company_id=company_id,
                sender_type="tenant_owner",
                sender_user_id=user_id,
                sender_operator_id=None,
                body="ข้อความตัวอย่างเพื่อทดสอบรูปแบบรายการสนทนาและสถานะงาน",
                created_at=now - timedelta(days=index, hours=-1),
            )
            count(summary, "support_tickets")

        for index, (request_type, status_value) in enumerate(
            (("export", "submitted"), ("correction", "in_review"), ("access", "fulfilled")),
            start=1,
        ):
            await put(
                db,
                SaasPrivacyRequest,
                "platform-privacy",
                request_type,
                company_id=company_id,
                requester_user_id=user_id,
                request_type=request_type,
                subject_email=f"ui-demo-{index}@example.invalid",
                description="คำขอตัวอย่างสำหรับจัดหน้า Privacy & Support",
                status=status_value,
                identity_verification="authenticated_owner",
                target_at=now + timedelta(days=30),
                response_summary="ดำเนินการด้วยข้อมูลจำลองแล้ว" if status_value == "fulfilled" else None,
                completed_at=now - timedelta(hours=8) if status_value == "fulfilled" else None,
                created_at=now - timedelta(days=index * 2),
            )
            count(summary, "privacy_requests")

        branches = (await db.scalars(select(Branch).where(Branch.company_id == company_id))).all()
        device_rows = (
            ("counter-main", "counter", "เครื่องขายหน้าร้าน", None),
            ("kitchen-main", "kitchen", "จอครัว", "ครัวร้อน"),
            ("pickup-revoked", "pickup", "จอเรียกรับสินค้า", None),
            ("counter-pairing", "counter", "เครื่องขายสำรอง", None),
        )
        for index, (device_key, device_type, device_name, station_key) in enumerate(device_rows, start=1):
            branch = branches[(index - 1) % len(branches)]
            await put(
                db,
                DeviceRegistration,
                "platform-device",
                device_key,
                company_id=company_id,
                branch_id=branch.id,
                device_code=f"UI-DEVICE-{index:02d}",
                name=device_name,
                device_type=device_type,
                station_key=station_key,
                created_by=user_id,
                paired_at=now - timedelta(days=index) if index < 4 else None,
                last_seen_at=now - timedelta(minutes=index * 7) if index < 3 else None,
                revoked_at=now - timedelta(days=1) if index == 3 else None,
                revoked_by=user_id if index == 3 else None,
                revocation_reason="ตัวอย่างสถานะยกเลิกอุปกรณ์" if index == 3 else None,
            )
            count(summary, "devices")

        operator = await db.scalar(select(PlatformOperator).order_by(PlatformOperator.created_at).limit(1))
        if operator is not None:
            await put(
                db,
                PlatformTenantUsageSnapshot,
                "platform-usage",
                str(date.today()),
                company_id=company_id,
                captured_on=date.today(),
                plan_code=plan.code,
                feature_flags=plan.feature_flags,
                plan_limits=plan.plan_limits,
                usage={"brands": 3, "branches": len(branches), "users": 6, "devices": 4},
                limit_state="healthy",
                attention_codes=[],
                last_activity_at=now,
                onboarding_completed_steps=8,
                onboarding_total_steps=10,
                captured_by=operator.id,
            )
            await put(
                db,
                PlatformOperationsSnapshot,
                "platform-operations",
                "healthy",
                captured_at=now,
                overall_status="healthy",
                source="ui_showcase",
                component_checks={"api": "healthy", "postgres": "healthy", "redis": "healthy", "backup": "healthy"},
                projector_failed_events=0,
                projector_loop_errors=0,
                disk_usage_percent=Decimal("42.5"),
                backup_status="fresh",
                backup_age_hours=Decimal("1.2"),
                restore_status="passed",
                restore_drill_at=now - timedelta(hours=2),
                alert_delivery_status="healthy",
                alert_codes=[],
                evidence_sha256=digest("ui-showcase-operations-healthy"),
                captured_by=operator.id,
            )
            count(summary, "platform_snapshots", 2)
        await db.commit()
    return summary


async def mirror_platform_references_to_legacy(
    company: Company,
    references: dict[str, list[dict[str, Any]]],
) -> None:
    async with AsyncSessionLocal() as db:
        legacy_company = await db.get(Company, company.id)
        if legacy_company is None:
            db.add(
                Company(
                    id=company.id,
                    name=company.name,
                    business_slug=company.business_slug,
                    is_active=True,
                )
            )
            await db.flush()
        for row in references["branches"]:
            branch = await db.get(Branch, row["id"])
            values = {key: value for key, value in row.items() if key != "id"}
            if branch is None:
                db.add(Branch(id=row["id"], company_id=company.id, **values))
            else:
                for key, value in values.items():
                    setattr(branch, key, value)
        await db.flush()
        for row in references["brands"]:
            brand = await db.get(Brand, row["id"])
            values = {key: value for key, value in row.items() if key != "id"}
            if brand is None:
                db.add(Brand(id=row["id"], company_id=company.id, **values))
            else:
                for key, value in values.items():
                    setattr(brand, key, value)
        await db.flush()
        for row in references["links"]:
            link = await db.get(BrandBranch, row["id"])
            values = {key: value for key, value in row.items() if key != "id"}
            if link is None:
                db.add(BrandBranch(id=row["id"], company_id=company.id, **values))
            else:
                for key, value in values.items():
                    setattr(link, key, value)
        await db.commit()


async def ensure_location(
    db: AsyncSession,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    code: str,
    name: str,
) -> StockLocation:
    row = await db.scalar(
        select(StockLocation).where(
            StockLocation.company_id == company_id,
            StockLocation.branch_id == branch_id,
            StockLocation.code == code,
            StockLocation.deleted_at.is_(None),
        )
    )
    if row is None:
        row = StockLocation(
            id=fixture_id("stock-location", f"{branch_id}:{code}"),
            company_id=company_id,
            branch_id=branch_id,
            code=code,
            name=name,
            is_active=True,
        )
        db.add(row)
        await db.flush()
    return row


async def seed_legacy_catalog(company_id: uuid.UUID) -> dict[str, Any]:
    summary: dict[str, int] = {}
    async with AsyncSessionLocal() as db:
        restaurant_brand = await db.scalar(
            select(Brand).where(Brand.company_id == company_id, Brand.business_type == "restaurant")
        )
        main_branch = await db.scalar(
            select(Branch).where(Branch.company_id == company_id, Branch.code == "BKK-01")
        )
        showcase_branch = await db.scalar(
            select(Branch).where(Branch.company_id == company_id, Branch.code == "BKK-UI-02")
        )
        if restaurant_brand is None or main_branch is None or showcase_branch is None:
            raise RuntimeError("Restaurant showcase references are incomplete in Legacy")
    async with AsyncSessionLocal() as seed_db:
        await seed_fnb_demo_menu(seed_db, str(company_id), str(main_branch.id))
    # seed_fnb_demo_menu owns its transaction; use a fresh session for dependent fixtures.
    async with AsyncSessionLocal() as db:
        await seed_default_accounts(db, company_id)
        await seed_default_tiers(db, company_id)
        await seed_loyalty_settings(db, company_id)
        await seed_default_hr_components(db, company_id)
        await seed_default_leave_types(db, company_id)
        await seed_default_work_schedule(db, company_id, main_branch.id)
        await seed_public_holidays_2026(db, company_id)
        await seed_default_carriers(db, company_id)
        await seed_default_shipping_rates(db, company_id)
        main_location = await ensure_location(db, company_id, main_branch.id, "MAIN", "คลังหน้าร้าน สาขากรุงเทพ")
        showcase_location = await ensure_location(db, company_id, showcase_branch.id, "MAIN", "คลังหน้าร้าน สาขาสาธิต UI")
        raw_location = await ensure_location(db, company_id, main_branch.id, "CENTRAL-RAW", "คลังวัตถุดิบครัวกลาง")
        ready_location = await ensure_location(db, company_id, main_branch.id, "CENTRAL-READY", "คลังสินค้าพร้อมกระจาย")
        count(summary, "locations", 4)

        price_list = await db.scalar(
            select(PriceList).where(
                PriceList.company_id == company_id,
                PriceList.is_default.is_(True),
                PriceList.deleted_at.is_(None),
            )
        )
        if price_list is None:
            price_list, _ = await put(
                db,
                PriceList,
                "price-list",
                "ui-default",
                company_id=company_id,
                name="ราคาขาย UI Showcase",
                currency="THB",
                is_default=True,
                is_active=True,
            )
        products = (
            await db.scalars(
                select(Product).where(
                    Product.company_id == company_id,
                    Product.deleted_at.is_(None),
                    Product.is_active.is_(True),
                )
            )
        ).all()
        sale_products = [row for row in products if row.is_for_sale and row.selling_price > 0]
        for index, product in enumerate(products):
            if product.brand_id is None and product.product_type in {"menu_item", "raw_material"}:
                product.brand_id = restaurant_brand.id
            if product in sale_products:
                item = await db.scalar(
                    select(PriceListItem).where(
                        PriceListItem.price_list_id == price_list.id,
                        PriceListItem.product_id == product.id,
                        PriceListItem.variant_id.is_(None),
                    )
                )
                if item is None:
                    db.add(
                        PriceListItem(
                            id=fixture_id("price-item", str(product.id)),
                            company_id=company_id,
                            price_list_id=price_list.id,
                            product_id=product.id,
                            price=product.selling_price,
                            min_qty=Decimal("1"),
                        )
                    )
                else:
                    item.price = product.selling_price
                count(summary, "price_items")
            target_location = raw_location if product.product_type == "raw_material" else main_location
            balance = await db.scalar(
                select(StockBalance).where(
                    StockBalance.location_id == target_location.id,
                    StockBalance.product_id == product.id,
                    StockBalance.variant_id.is_(None),
                )
            )
            qty = Decimal(str((index % 5) * 8 + (3 if index % 4 == 0 else 18)))
            if balance is None:
                balance = StockBalance(
                    id=fixture_id("stock-balance", f"{target_location.id}:{product.id}"),
                    company_id=company_id,
                    branch_id=target_location.branch_id,
                    location_id=target_location.id,
                    product_id=product.id,
                    variant_id=None,
                    qty_on_hand=qty,
                    qty_reserved=Decimal(str(index % 3)),
                    cost_per_unit=product.cost_price,
                    last_movement_at=utc_now() - timedelta(hours=index),
                )
                db.add(balance)
            else:
                balance.qty_on_hand = max(balance.qty_on_hand, qty)
                balance.qty_reserved = min(balance.qty_on_hand, Decimal(str(index % 3)))
            count(summary, "stock_balances")
        await db.commit()
        return {
            "summary": summary,
            "restaurant_brand_id": restaurant_brand.id,
            "main_branch_id": main_branch.id,
            "showcase_branch_id": showcase_branch.id,
            "main_location_id": main_location.id,
            "showcase_location_id": showcase_location.id,
            "raw_location_id": raw_location.id,
            "ready_location_id": ready_location.id,
            "price_list_id": price_list.id,
        }


async def seed_restaurant_showcase(
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    context: dict[str, Any],
) -> dict[str, int]:
    summary: dict[str, int] = {}
    now = utc_now()
    async with AsyncSessionLocal() as db:
        branch_id = context["main_branch_id"]
        products = (
            await db.scalars(
                select(Product)
                .where(
                    Product.company_id == company_id,
                    Product.product_type == "menu_item",
                    Product.is_active.is_(True),
                    Product.deleted_at.is_(None),
                )
                .order_by(Product.sku)
                .limit(8)
            )
        ).all()
        tables = (
            await db.scalars(
                select(DiningTable)
                .where(DiningTable.company_id == company_id, DiningTable.branch_id == branch_id)
                .order_by(DiningTable.sort_order, DiningTable.name)
                .limit(4)
            )
        ).all()
        if len(products) < 4 or len(tables) < 4:
            raise RuntimeError("Restaurant menu or dining tables are incomplete for UI showcase")
        states = [
            ("pending", "pending", "รอยืนยันจากครัว", None),
            ("confirmed", "preparing", "กำลังปรุง ไม่เผ็ด", None),
            ("confirmed", "ready", "พร้อมเสิร์ฟ", now - timedelta(minutes=2)),
            ("served", "done", "เสิร์ฟแล้ว", now - timedelta(minutes=8)),
        ]
        for index, (order_status, item_status, note, done_at) in enumerate(states, start=1):
            table = tables[index - 1]
            session, _ = await put(
                db,
                DiningSession,
                "restaurant-session",
                str(index),
                company_id=company_id,
                branch_id=branch_id,
                table_id=table.id,
                qr_token=fixture_id("restaurant-qr", str(index)),
                opened_by=user_id,
                queue_number=100 + index,
                queue_date=date.today().isoformat(),
                status="open",
                guest_count=index + 1,
                customer_name=f"ลูกค้าตัวอย่างโต๊ะ {table.name}",
                customer_phone=f"09900000{index:02d}",
                note="[UI SHOWCASE] ทดสอบการแสดงสถานะโต๊ะและ KDS",
                opened_at=now - timedelta(minutes=index * 12),
                kitchen_sent_at=now - timedelta(minutes=index * 10),
            )
            table.status = "occupied"
            order, _ = await put(
                db,
                DiningOrder,
                "restaurant-dining-order",
                str(index),
                company_id=company_id,
                branch_id=branch_id,
                session_id=session.id,
                order_number=f"UI-DINE-{index:03d}",
                source="qr_self" if index % 2 else "staff",
                status=order_status,
                note=note,
                created_at=now - timedelta(minutes=index * 9),
            )
            product = products[index - 1]
            item, _ = await put(
                db,
                DiningOrderItem,
                "restaurant-dining-item",
                str(index),
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                qty=index,
                unit_price=product.selling_price,
                special_request="ไม่ใส่ผักชี" if index == 2 else None,
                station="ครัวร้อน" if index < 3 else "เครื่องดื่ม",
                status=item_status,
                created_at=now - timedelta(minutes=index * 8),
            )
            await put(
                db,
                KitchenTicket,
                "restaurant-kitchen-ticket",
                str(index),
                company_id=company_id,
                branch_id=branch_id,
                session_id=session.id,
                order_item_id=item.id,
                product_name=product.name,
                qty=index,
                special_request=item.special_request,
                station=item.station,
                queue_number=100 + index,
                table_name=table.name,
                status=item_status,
                done_at=done_at,
                created_at=now - timedelta(minutes=index * 8),
            )
            count(summary, "dining_sessions")
            count(summary, "kitchen_tickets")
        await db.commit()
    return summary


async def seed_sales_showcase(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    location_id: uuid.UUID,
    user_id: uuid.UUID,
    namespace: str,
    product_limit: int = 8,
) -> dict[str, int]:
    summary: dict[str, int] = {}
    now = utc_now()
    products = (
        await db.scalars(
            select(Product)
            .where(Product.company_id == company_id, Product.is_for_sale.is_(True), Product.is_active.is_(True))
            .order_by(Product.sku)
            .limit(product_limit)
        )
    ).all()
    if not products:
        raise RuntimeError(f"No sale products found for {namespace} UI showcase")
    sale_states = [
        ("completed", "cash", Decimal("0"), False),
        ("completed", "promptpay", Decimal("0"), False),
        ("completed", "card", Decimal("0"), True),
        ("refunded", "cash", Decimal("59"), False),
        ("voided", "cash", Decimal("0"), False),
        ("completed", "cash", Decimal("0"), False),
        ("completed", "promptpay", Decimal("0"), False),
    ]
    for index, (status_value, method, refund_amount, offline) in enumerate(sale_states, start=1):
        occurred_at = now - timedelta(days=7 - index, hours=index)
        shift, _ = await put(
            db,
            CashierShift,
            f"{namespace}-shift",
            str(index),
            company_id=company_id,
            branch_id=branch_id,
            location_id=location_id,
            user_id=user_id,
            shift_number=f"UI-{namespace.upper()}-S{index:03d}",
            status="closed",
            opened_at=occurred_at - timedelta(hours=8),
            closed_at=occurred_at,
            opening_cash=Decimal("1000"),
            closing_cash=Decimal("2450") + index,
            expected_cash=Decimal("2445") + index,
            cash_difference=Decimal("5"),
            total_sales=Decimal("350") + index * Decimal("75"),
            total_orders=index + 2,
            total_voids=1 if status_value == "voided" else 0,
            note="[UI SHOWCASE] กะขายตัวอย่าง",
            created_at=occurred_at - timedelta(hours=8),
        )
        product = products[(index - 1) % len(products)]
        total = Decimal(product.selling_price).quantize(Decimal("0.01"))
        vat = (total * Decimal("7") / Decimal("107")).quantize(Decimal("0.01"))
        sale, _ = await put(
            db,
            SaleOrder,
            f"{namespace}-sale",
            str(index),
            company_id=company_id,
            branch_id=branch_id,
            location_id=location_id,
            shift_id=shift.id,
            user_id=user_id,
            order_number=f"UI-{namespace.upper()}-SO-{index:04d}",
            status=status_value,
            customer_name=f"ลูกค้า {namespace.upper()} {index}",
            customer_phone=f"09910000{index:02d}",
            subtotal=total - vat,
            discount_amount=Decimal("10") if index == 6 else Decimal("0"),
            discount_type="amount",
            vat_amount=vat,
            vat_rate=Decimal("7"),
            total_amount=total,
            refund_amount=refund_amount,
            paid_amount=Decimal("0") if status_value == "voided" else total,
            change_amount=Decimal("0"),
            voided_at=occurred_at if status_value == "voided" else None,
            voided_by=user_id if status_value == "voided" else None,
            void_reason="ยกเลิกรายการตัวอย่าง" if status_value == "voided" else None,
            refunded_at=occurred_at if status_value == "refunded" else None,
            is_offline=offline,
            client_order_id=f"ui-{namespace}-client-{index}",
            synced_at=occurred_at + timedelta(minutes=3) if offline else None,
            note="[UI SHOWCASE] ข้อมูลจำลองสำหรับหน้ารายการขาย",
            created_at=occurred_at,
        )
        item, _ = await put(
            db,
            SaleOrderItem,
            f"{namespace}-sale-item",
            str(index),
            order_id=sale.id,
            company_id=company_id,
            product_id=product.id,
            variant_id=None,
            product_name=product.name,
            variant_name=None,
            sku=product.sku,
            unit_code="PCS",
            qty=Decimal("1"),
            unit_price=total,
            original_price=total,
            discount_amount=Decimal("0"),
            discount_type="amount",
            vat_type="included",
            vat_rate=Decimal("7"),
            vat_amount=vat,
            subtotal=total,
            refunded_qty=Decimal("1") if status_value == "refunded" else Decimal("0"),
            refunded_amount=refund_amount,
            created_at=occurred_at,
        )
        del item
        if status_value != "voided":
            await put(
                db,
                Payment,
                f"{namespace}-payment",
                str(index),
                order_id=sale.id,
                company_id=company_id,
                payment_method=method,
                amount=total,
                reference_no=f"UI-PAY-{namespace.upper()}-{index:03d}",
                paid_at=occurred_at,
                note="ข้อมูลการชำระเงินตัวอย่าง",
                created_at=occurred_at,
            )
        count(summary, "sales")
    return summary


async def seed_inventory_and_purchasing_showcase(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    context: dict[str, Any],
) -> dict[str, int]:
    summary: dict[str, int] = {}
    now = utc_now()
    products = (
        await db.scalars(
            select(Product)
            .where(Product.company_id == company_id, Product.is_active.is_(True))
            .order_by(Product.sku)
            .limit(8)
        )
    ).all()
    if len(products) < 4:
        raise RuntimeError("At least four Legacy products are required for purchasing fixtures")

    suppliers: list[Supplier] = []
    for index, name in enumerate(("ตลาดสดคุณภาพ", "โฮลเซลล์ฟู้ดเซอร์วิส", "บรรจุภัณฑ์รักษ์โลก"), start=1):
        supplier, _ = await put(
            db,
            Supplier,
            "supplier",
            str(index),
            company_id=company_id,
            code=f"UI-SUP-{index:02d}",
            name=name,
            tax_id=f"01055660{index:05d}",
            branch_code="00000",
            tax_entity_type="juristic",
            address="กรุงเทพมหานคร (ข้อมูลตัวอย่าง)",
            phone=f"0211100{index:03d}",
            email=f"supplier-{index}@example.invalid",
            contact_person=f"ผู้ติดต่อ {index}",
            payment_term_days=15 * index,
            wht_rate=Decimal("3"),
            credit_limit=Decimal("100000"),
            note="[UI SHOWCASE] ผู้จำหน่ายตัวอย่าง",
            is_active=index != 3,
        )
        suppliers.append(supplier)
        count(summary, "suppliers")

    po_states = ("draft", "approved", "partial", "received", "cancelled")
    for index, status_value in enumerate(po_states, start=1):
        subtotal = Decimal(4500 + index * 700)
        vat = (subtotal * Decimal("0.07")).quantize(Decimal("0.01"))
        po, _ = await put(
            db,
            PurchaseOrder,
            "purchase-order",
            status_value,
            company_id=company_id,
            branch_id=context["main_branch_id"],
            supplier_id=suppliers[(index - 1) % len(suppliers)].id,
            created_by=user_id,
            approved_by=user_id if status_value in {"approved", "partial", "received"} else None,
            po_number=f"UI-PO-2026-{index:03d}",
            status=status_value,
            order_date=date.today() - timedelta(days=8 - index),
            expected_date=date.today() + timedelta(days=index),
            approved_at=now - timedelta(days=6 - index) if status_value in {"approved", "partial", "received"} else None,
            cancelled_at=now - timedelta(days=1) if status_value == "cancelled" else None,
            cancel_reason="เปลี่ยนแผนการสั่งซื้อ (ตัวอย่าง)" if status_value == "cancelled" else None,
            subtotal=subtotal,
            discount_amount=Decimal("100") if index == 2 else Decimal("0"),
            vat_amount=vat,
            wht_amount=Decimal("0"),
            total_amount=subtotal + vat,
            paid_amount=subtotal + vat if status_value == "received" else Decimal("0"),
            remaining_amount=Decimal("0") if status_value == "received" else subtotal + vat,
            vat_type="excluded",
            vat_rate=Decimal("7"),
            wht_rate=Decimal("3"),
            note="[UI SHOWCASE] ใบสั่งซื้อตัวอย่าง",
        )
        product = products[index % len(products)]
        received_qty = Decimal("10") if status_value == "received" else Decimal("4") if status_value == "partial" else Decimal("0")
        po_item, _ = await put(
            db,
            PurchaseOrderItem,
            "purchase-item",
            status_value,
            po_id=po.id,
            company_id=company_id,
            product_id=product.id,
            variant_id=None,
            product_name=product.name,
            sku=product.sku,
            unit_code="PCS",
            qty_ordered=Decimal("10"),
            qty_received=received_qty,
            unit_cost=product.cost_price or Decimal("50"),
            discount_amount=Decimal("0"),
            vat_type="excluded",
            vat_rate=Decimal("7"),
            vat_amount=vat,
            subtotal=subtotal,
        )
        if status_value in {"partial", "received"}:
            receipt, _ = await put(
                db,
                GoodsReceipt,
                "goods-receipt",
                status_value,
                company_id=company_id,
                branch_id=context["main_branch_id"],
                po_id=po.id,
                location_id=context["main_location_id"],
                received_by=user_id,
                gr_number=f"UI-GR-2026-{index:03d}",
                received_date=date.today() - timedelta(days=1),
                note="[UI SHOWCASE] รับสินค้าตัวอย่าง",
            )
            await put(
                db,
                GoodsReceiptItem,
                "goods-receipt-item",
                status_value,
                gr_id=receipt.id,
                po_item_id=po_item.id,
                product_id=product.id,
                variant_id=None,
                qty_received=received_qty,
                unit_cost=product.cost_price or Decimal("50"),
                note="จำนวนตัวอย่างสำหรับจัด UI",
            )
            count(summary, "goods_receipts")
        count(summary, "purchase_orders")

    transfer_states = ("draft", "approved", "shipped", "completed", "cancelled")
    for index, status_value in enumerate(transfer_states, start=1):
        product = products[(index + 1) % len(products)]
        order, _ = await put(
            db,
            TransferOrder,
            "transfer-order",
            status_value,
            company_id=company_id,
            to_number=f"UI-TO-2026-{index:03d}",
            status=status_value,
            from_branch_id=context["main_branch_id"],
            to_branch_id=context["showcase_branch_id"],
            from_location_id=context["main_location_id"],
            to_location_id=context["showcase_location_id"],
            requested_by=user_id,
            approved_by=user_id if status_value in {"approved", "shipped", "completed"} else None,
            received_by=user_id if status_value == "completed" else None,
            request_date=date.today() - timedelta(days=index),
            expected_date=date.today() + timedelta(days=1),
            approved_at=now - timedelta(days=1) if status_value in {"approved", "shipped", "completed"} else None,
            shipped_at=now - timedelta(hours=8) if status_value in {"shipped", "completed"} else None,
            last_received_at=now - timedelta(hours=2) if status_value == "completed" else None,
            completed_at=now - timedelta(hours=2) if status_value == "completed" else None,
            cancelled_at=now - timedelta(hours=4) if status_value == "cancelled" else None,
            cancel_reason="สินค้าปลายทางเพียงพอแล้ว" if status_value == "cancelled" else None,
            has_discrepancy=status_value == "completed" and index % 2 == 0,
            discrepancy_note=None,
            destination_posted_at_ship=False,
            note="[UI SHOWCASE] โอนสินค้าระหว่างสาขา",
        )
        sent = Decimal("8") if status_value in {"shipped", "completed"} else None
        received = Decimal("8") if status_value == "completed" else None
        await put(
            db,
            TransferOrderItem,
            "transfer-item",
            status_value,
            to_id=order.id,
            company_id=company_id,
            product_id=product.id,
            variant_id=None,
            product_name=product.name,
            sku=product.sku,
            unit_code="PCS",
            qty_requested=Decimal("10"),
            qty_approved=Decimal("8") if status_value not in {"draft", "cancelled"} else None,
            qty_sent=sent,
            qty_received=received,
            unit_cost=product.cost_price,
            qty_discrepancy=Decimal("0"),
        )
        count(summary, "transfers")

    count_states = ("draft", "counting", "completed")
    for index, status_value in enumerate(count_states, start=1):
        session, _ = await put(
            db,
            StockCountSession,
            "stock-count",
            status_value,
            company_id=company_id,
            branch_id=context["main_branch_id"],
            location_id=context["main_location_id"],
            session_number=f"UI-SC-2026-{index:03d}",
            status=status_value,
            count_date=date.today() - timedelta(days=3 - index),
            started_at=now - timedelta(hours=4) if status_value != "draft" else None,
            completed_at=now - timedelta(hours=1) if status_value == "completed" else None,
            created_by=user_id,
            completed_by=user_id if status_value == "completed" else None,
            note="[UI SHOWCASE] รอบตรวจนับสต๊อก",
            total_items=3,
            items_matched=1 if status_value == "completed" else 0,
            items_over=1 if status_value == "completed" else 0,
            items_short=1 if status_value == "completed" else 0,
            total_variance_value=Decimal("-35") if status_value == "completed" else Decimal("0"),
        )
        for item_index, product in enumerate(products[:3], start=1):
            expected = Decimal(str(12 + item_index))
            variance = Decimal(str(item_index - 2)) if status_value == "completed" else None
            actual = expected + variance if variance is not None else None
            await put(
                db,
                StockCountItem,
                "stock-count-item",
                f"{status_value}:{item_index}",
                session_id=session.id,
                company_id=company_id,
                product_id=product.id,
                variant_id=None,
                product_name=product.name,
                sku=product.sku,
                unit_code="PCS",
                expected_qty=expected,
                actual_qty=actual,
                variance_qty=variance,
                cost_per_unit=product.cost_price,
                variance_value=variance * product.cost_price if variance is not None else None,
                counted_at=now - timedelta(hours=1) if actual is not None else None,
                counted_by=user_id if actual is not None else None,
                note="ตัวอย่างตรง/เกิน/ขาด" if status_value == "completed" else None,
                is_adjusted=status_value == "completed",
            )
        count(summary, "stock_counts")
    return summary


async def seed_crm_showcase(db: AsyncSession, *, company_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, int]:
    summary: dict[str, int] = {}
    now = utc_now()
    tiers = (await db.scalars(select(CustomerTier).where(CustomerTier.company_id == company_id).order_by(CustomerTier.sort_order))).all()
    if not tiers:
        raise RuntimeError("CRM tiers were not seeded")
    tags: list[CustomerTag] = []
    for key, label, color in (("vip", "ลูกค้า VIP", "#7c3aed"), ("delivery", "ชอบเดลิเวอรี", "#0891b2"), ("birthday", "วันเกิดเดือนนี้", "#db2777")):
        tag, _ = await put(db, CustomerTag, "customer-tag", key, company_id=company_id, name=label, color=color)
        tags.append(tag)
    for index in range(1, 9):
        points = index * 125
        customer, _ = await put(
            db,
            Customer,
            "customer",
            str(index),
            company_id=company_id,
            tier_id=tiers[(index - 1) % len(tiers)].id,
            customer_code=f"UI-CUS-{index:04d}",
            first_name=f"ลูกค้า{index}",
            last_name="ตัวอย่าง",
            display_name=f"สมาชิก UI {index}",
            phone=f"09870000{index:02d}",
            email=f"customer-{index}@example.invalid",
            date_of_birth=date(1990 + index, ((index - 1) % 12) + 1, min(index + 2, 28)),
            gender="female" if index % 2 else "male",
            address="กรุงเทพมหานคร (ข้อมูลตัวอย่าง)",
            note="[UI SHOWCASE] ลูกค้าสำหรับทดสอบรายการและโปรไฟล์",
            points_balance=points,
            lifetime_spend=Decimal(index * 3250),
            lifetime_points_earned=points + 50,
            lifetime_points_redeemed=50,
            total_orders=index * 3,
            last_purchase_at=now - timedelta(days=index),
            is_active=index != 8,
            is_blacklisted=index == 7,
            blacklist_reason="ข้อมูลตัวอย่างสถานะเฝ้าระวัง" if index == 7 else None,
        )
        await put(
            db,
            PointsTransaction,
            "points-transaction",
            str(index),
            company_id=company_id,
            customer_id=customer.id,
            transaction_type="earn" if index % 3 else "redeem",
            points=100 if index % 3 else -50,
            balance_after=points,
            reference_type="sale_order",
            reference_id=f"UI-SALE-{index}",
            spend_amount=Decimal("500"),
            redeem_amount=Decimal("5") if index % 3 == 0 else None,
            note="รายการคะแนนตัวอย่าง",
            expires_at=now + timedelta(days=365),
            created_by=user_id,
            created_at=now - timedelta(days=index),
        )
        assignment = await db.get(CustomerTagAssignment, {"customer_id": customer.id, "tag_id": tags[index % len(tags)].id})
        if assignment is None:
            db.add(CustomerTagAssignment(customer_id=customer.id, tag_id=tags[index % len(tags)].id))
        count(summary, "customers")
    summary["customer_tags"] = len(tags)
    return summary


async def seed_hr_showcase(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict[str, int]:
    summary: dict[str, int] = {}
    now = utc_now()
    departments: list[Department] = []
    positions: list[Position] = []
    department_rows = (
        ("STORE", "หน้าร้าน", "CASHIER", "พนักงานขาย"),
        ("OPS", "ปฏิบัติการร้าน", "MANAGER", "ผู้จัดการร้าน"),
        ("PUR", "จัดซื้อ", "BUYER", "เจ้าหน้าที่จัดซื้อ"),
        ("ACC", "บัญชีและการเงิน", "ACCOUNT", "เจ้าหน้าที่บัญชี"),
        ("KITCHEN", "ครัวกลาง", "CHEF", "พนักงานครัว"),
    )
    for level, (dept_code, dept_name, pos_code, pos_name) in enumerate(department_rows, start=1):
        department, _ = await put(
            db,
            Department,
            "department",
            dept_code,
            company_id=company_id,
            code=f"UI-{dept_code}",
            name=dept_name,
            name_en=dept_code.title(),
            parent_id=None,
            manager_id=None,
            is_active=True,
        )
        position, _ = await put(
            db,
            Position,
            "position",
            pos_code,
            company_id=company_id,
            department_id=department.id,
            code=f"UI-{pos_code}",
            name=pos_name,
            name_en=pos_code.title(),
            level=level,
            is_active=True,
        )
        departments.append(department)
        positions.append(position)
    schedule = await db.scalar(select(WorkSchedule).where(WorkSchedule.company_id == company_id, WorkSchedule.is_default.is_(True)))
    leave_type = await db.scalar(select(LeaveType).where(LeaveType.company_id == company_id, LeaveType.code == "ANNUAL"))
    base_component = await db.scalar(select(SalaryComponent).where(SalaryComponent.company_id == company_id, SalaryComponent.code == "BASE"))
    if schedule is None or leave_type is None or base_component is None:
        raise RuntimeError("Default HR references were not seeded")

    employees: list[Employee] = []
    names = (("สมชาย", "ขายดี"), ("สุดา", "บริหารร้าน"), ("นพดล", "จัดซื้อไว"), ("วราภรณ์", "บัญชีตรง"), ("กิตติ", "ครัวกลาง"), ("มาลี", "พาร์ตไทม์"))
    for index, (first_name, last_name) in enumerate(names, start=1):
        position = positions[(index - 1) % len(positions)]
        department = departments[(index - 1) % len(departments)]
        salary = Decimal(15000 + index * 2500)
        employee, _ = await put(
            db,
            Employee,
            "employee",
            str(index),
            company_id=company_id,
            branch_id=branch_id,
            user_id=None,
            employee_code=f"UI-EMP-{index:03d}",
            department_id=department.id,
            position_id=position.id,
            title="นาย" if index % 2 else "นางสาว",
            first_name=first_name,
            last_name=last_name,
            date_of_birth=date(1988 + index, index, min(10 + index, 28)),
            gender="male" if index % 2 else "female",
            national_id=f"199990000{index:03d}",
            phone=f"09750000{index:02d}",
            email=f"employee-{index}@example.invalid",
            address="กรุงเทพมหานคร (ข้อมูลตัวอย่าง)",
            hire_date=date.today() - timedelta(days=index * 120),
            probation_end_date=date.today() - timedelta(days=index * 30),
            employment_type="parttime" if index == 6 else "fulltime",
            base_salary=salary,
            salary_type="daily" if index == 6 else "monthly",
            bank_name="ธนาคารตัวอย่าง",
            bank_account=f"000000{index:04d}",
            bank_account_name=f"{first_name} {last_name}",
            tax_id=f"199990000{index:03d}",
            sso_registered=index != 6,
            is_active=index != 5,
        )
        employees.append(employee)
        await put(
            db,
            EmployeeSalary,
            "employee-salary",
            str(index),
            employee_id=employee.id,
            company_id=company_id,
            component_id=base_component.id,
            amount=salary,
            effective_from=date.today().replace(month=1, day=1),
            effective_to=None,
        )
        absence = index == 5
        late = index == 3
        await put(
            db,
            AttendanceRecord,
            "attendance",
            str(index),
            company_id=company_id,
            employee_id=employee.id,
            work_date=date.today() - timedelta(days=1),
            schedule_id=schedule.id,
            clock_in=None if absence else now.replace(hour=1, minute=10 if late else 0),
            clock_out=None if absence else now.replace(hour=10, minute=0),
            work_minutes=None if absence else 480,
            ot_minutes=60 if index == 1 else 0,
            ot_rate=Decimal("1.5"),
            ot_amount=Decimal("150") if index == 1 else Decimal("0"),
            is_absent=absence,
            is_late=late,
            late_minutes=10 if late else 0,
            is_holiday=False,
            note="ข้อมูลลงเวลาตัวอย่าง",
            entry_type="manual",
            created_by=user_id,
        )
        await put(
            db,
            LeaveBalance,
            "leave-balance",
            str(index),
            company_id=company_id,
            employee_id=employee.id,
            leave_type_id=leave_type.id,
            year=date.today().year,
            entitled_days=Decimal("6"),
            used_days=Decimal(str(index % 3)),
            remaining_days=Decimal(str(6 - index % 3)),
            carry_over_days=Decimal("0"),
        )
        count(summary, "employees")

    for index, status_value in enumerate(("pending", "approved", "rejected", "cancelled"), start=1):
        await put(
            db,
            LeaveRequest,
            "leave-request",
            status_value,
            company_id=company_id,
            employee_id=employees[index - 1].id,
            leave_type_id=leave_type.id,
            request_number=f"UI-LV-2026-{index:03d}",
            status=status_value,
            start_date=date.today() + timedelta(days=index * 2),
            end_date=date.today() + timedelta(days=index * 2),
            days_requested=Decimal("1"),
            reason="ธุระส่วนตัว (ข้อมูลตัวอย่าง)",
            reviewed_by=user_id if status_value in {"approved", "rejected"} else None,
            reviewed_at=now if status_value in {"approved", "rejected"} else None,
            review_note="อนุมัติ/ปฏิเสธเพื่อทดสอบ badge" if status_value in {"approved", "rejected"} else None,
            auto_attendance=True,
            created_by=user_id,
        )
        count(summary, "leave_requests")

    run, _ = await put(
        db,
        PayrollRun,
        "payroll-run",
        "current",
        company_id=company_id,
        branch_id=branch_id,
        run_number=f"UI-PAYROLL-{date.today().year}-{date.today().month:02d}",
        period_year=date.today().year,
        period_month=date.today().month,
        pay_date=date.today().replace(day=28),
        status="draft",
        total_employees=len(employees),
        total_gross=sum((employee.base_salary for employee in employees), Decimal("0")),
        total_deductions=Decimal("6000"),
        total_net=sum((employee.base_salary for employee in employees), Decimal("0")) - Decimal("6000"),
        total_sso_employee=Decimal("4500"),
        total_sso_employer=Decimal("4500"),
        total_pit=Decimal("1500"),
        created_by=user_id,
        note="[UI SHOWCASE] รอบเงินเดือนตัวอย่าง",
    )
    for index, employee in enumerate(employees, start=1):
        deductions = Decimal("1000")
        item, _ = await put(
            db,
            PayrollItem,
            "payroll-item",
            str(index),
            run_id=run.id,
            employee_id=employee.id,
            company_id=company_id,
            base_salary=employee.base_salary,
            earnings_total=employee.base_salary,
            sso_employee=Decimal("750"),
            sso_employer=Decimal("750"),
            pit_withheld=Decimal("250"),
            other_deductions=Decimal("0"),
            total_deductions=deductions,
            net_pay=employee.base_salary - deductions,
            ytd_gross=employee.base_salary * date.today().month,
            ytd_pit=Decimal("250") * date.today().month,
            employee_name=employee.full_name,
            employee_code=employee.employee_code,
            position_name=positions[(index - 1) % len(positions)].name,
            department_name=departments[(index - 1) % len(departments)].name,
            bank_account=employee.bank_account,
        )
        await put(
            db,
            PayrollItemLine,
            "payroll-line",
            str(index),
            payroll_item_id=item.id,
            component_id=base_component.id,
            component_name=base_component.name,
            component_type="earning",
            amount=employee.base_salary,
            note="เงินเดือนฐานตัวอย่าง",
            created_at=now,
        )
    summary["payroll_runs"] = 1
    return summary


async def seed_accounting_and_channels_showcase(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict[str, int]:
    summary: dict[str, int] = {}
    now = utc_now()
    accounts = {
        row.code: row
        for row in (await db.scalars(select(Account).where(Account.company_id == company_id))).all()
    }
    for index, (entry_type, description, debit_code, credit_code, amount) in enumerate(
        (
            ("sale", "ยอดขายหน้าร้าน", "1101", "4001", Decimal("5350")),
            ("purchase", "ซื้อวัตถุดิบ", "1105", "2101", Decimal("3200")),
            ("expense", "ค่าสาธารณูปโภค", "6003", "1102", Decimal("1450")),
        ),
        start=1,
    ):
        entry, _ = await put(
            db,
            JournalEntry,
            "journal-entry",
            str(index),
            company_id=company_id,
            branch_id=branch_id,
            entry_number=f"UI-JV-2026-{index:04d}",
            entry_date=date.today() - timedelta(days=3 - index),
            period_year=date.today().year,
            period_month=date.today().month,
            entry_type=entry_type,
            reference_type="ui_showcase",
            reference_id=f"UI-REF-{index}",
            description=description,
            is_posted=index != 3,
            is_reversed=False,
            reversed_by=None,
            created_by=user_id,
            posted_at=now if index != 3 else None,
        )
        for line_number, (code, debit, credit) in enumerate(
            ((debit_code, amount, Decimal("0")), (credit_code, Decimal("0"), amount)),
            start=1,
        ):
            if code not in accounts:
                raise RuntimeError(f"Account {code} is missing")
            await put(
                db,
                JournalLine,
                "journal-line",
                f"{index}:{line_number}",
                entry_id=entry.id,
                company_id=company_id,
                account_id=accounts[code].id,
                line_number=line_number,
                description=description,
                debit_amount=debit,
                credit_amount=credit,
                created_at=now,
            )
        count(summary, "journal_entries")

    keys = (
        ("active", True, None),
        ("expiring", True, now + timedelta(days=7)),
        ("revoked", False, now - timedelta(days=2)),
    )
    for index, (key, active, expires_at) in enumerate(keys, start=1):
        await put(
            db,
            APIKey,
            "api-key",
            key,
            company_id=company_id,
            name=f"UI API Key {key}",
            purpose="UI showcase",
            owner_contact="uat@foodchainservice.local",
            key_prefix=f"UI{index:06d}"[:8],
            key_hash=digest(f"non-secret-ui-key-{key}"),
            scopes=["orders:read", "products:read"] if active else [],
            is_active=active,
            last_used_at=now - timedelta(hours=index) if active else None,
            expires_at=expires_at,
            created_by=user_id,
            revoked_at=now - timedelta(days=1) if not active else None,
            revoked_by=user_id if not active else None,
        )
        count(summary, "api_keys")

    webhook, _ = await put(
        db,
        WebhookEndpoint,
        "webhook",
        "orders",
        company_id=company_id,
        name="UI Order Events",
        url="https://webhook.example.invalid/foodchainservice",
        events=["order.created", "order.completed", "stock.low"],
        secret_ciphertext=encrypt_integration_secret(digest("non-secret-ui-webhook")),
        secret_rotated_at=now,
        incoming_source="ui-showcase",
        is_active=True,
        last_triggered_at=now - timedelta(minutes=15),
        failure_count=1,
    )
    for index, status_code in enumerate((200, 500, None), start=1):
        await put(
            db,
            WebhookDelivery,
            "webhook-delivery",
            str(index),
            webhook_id=webhook.id,
            company_id=company_id,
            event_type=("order.created", "order.completed", "stock.low")[index - 1],
            payload={"demo": True, "sequence": index},
            response_status=status_code,
            response_body="OK" if status_code == 200 else "Demo failure" if status_code else None,
            status="delivered" if status_code == 200 else "retry_scheduled" if status_code == 500 else "pending",
            attempt_count=index,
            last_error_code="http_500" if status_code == 500 else None,
            delivered_at=now - timedelta(minutes=index) if status_code == 200 else None,
            failed_at=now - timedelta(minutes=index) if status_code == 500 else None,
            next_retry_at=now + timedelta(minutes=10) if status_code != 200 else None,
            created_at=now - timedelta(minutes=index * 5),
        )
        count(summary, "webhook_deliveries")

    for index, status_value in enumerate(("pending", "processing", "completed", "cancelled"), start=1):
        await put(
            db,
            ExternalOrder,
            "external-order",
            status_value,
            company_id=company_id,
            source=("line", "grab", "website", "lineman")[index - 1],
            external_order_id=f"UI-EXT-{index:04d}",
            status=status_value,
            customer_name=f"ลูกค้าช่องทางออนไลน์ {index}",
            customer_phone=f"09640000{index:02d}",
            customer_email=f"external-{index}@example.invalid",
            customer_address="กรุงเทพมหานคร (ข้อมูลตัวอย่าง)",
            items_json=[{"name": "เมนูตัวอย่าง", "qty": index, "price": 99}],
            total_amount=Decimal(99 * index),
            payment_method="online",
            payment_status="paid" if status_value == "completed" else "pending",
            sale_order_id=None,
            notes="[UI SHOWCASE] ออเดอร์จากช่องทางภายนอก",
            raw_payload={"demo": True},
            received_at=now - timedelta(hours=index),
            processed_at=now - timedelta(minutes=30) if status_value in {"completed", "cancelled"} else None,
        )
        count(summary, "external_orders")
    return summary


async def seed_logistics_showcase(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict[str, int]:
    summary: dict[str, int] = {}
    now = utc_now()
    carriers = (await db.scalars(select(Carrier).where(Carrier.company_id == company_id, Carrier.is_active.is_(True)))).all()
    products = (await db.scalars(select(Product).where(Product.company_id == company_id, Product.is_active.is_(True)).limit(5))).all()
    if not carriers or not products:
        raise RuntimeError("Logistics showcase references are incomplete")
    states = ("pending", "ready", "shipped", "delivered", "returned")
    for index, status_value in enumerate(states, start=1):
        carrier = carriers[(index - 1) % len(carriers)]
        shipment, _ = await put(
            db,
            Shipment,
            "shipment",
            status_value,
            company_id=company_id,
            branch_id=branch_id,
            carrier_id=carrier.id,
            shipment_number=f"UI-SHP-2026-{index:04d}",
            status=status_value,
            sale_order_id=None,
            external_order_id=None,
            sender_name="Foodchainservice สาขาหลัก",
            sender_phone="021111111",
            sender_address="กรุงเทพมหานคร",
            recipient_name=f"ลูกค้าจัดส่ง {index}",
            recipient_phone=f"09530000{index:02d}",
            recipient_address=f"ที่อยู่จัดส่งตัวอย่าง ลำดับ {index}",
            weight_grams=500 + index * 250,
            width_cm=20,
            height_cm=15,
            depth_cm=25,
            service_name="ส่งด่วน",
            is_cod=index == 2,
            cod_amount=Decimal("450") if index == 2 else Decimal("0"),
            shipping_cost=Decimal("45") + index,
            tracking_number=f"UITRACK{index:08d}" if status_value not in {"pending", "ready"} else None,
            picked_up_at=now - timedelta(days=2) if status_value in {"shipped", "delivered", "returned"} else None,
            delivered_at=now - timedelta(days=1) if status_value == "delivered" else None,
            returned_at=now - timedelta(hours=8) if status_value == "returned" else None,
            note="[UI SHOWCASE] งานจัดส่งตัวอย่าง",
            created_by=user_id,
        )
        product = products[(index - 1) % len(products)]
        await put(
            db,
            ShipmentItem,
            "shipment-item",
            status_value,
            shipment_id=shipment.id,
            product_id=product.id,
            product_name=product.name,
            sku=product.sku,
            qty=Decimal(str(index)),
            unit_price=product.selling_price,
        )
        event_states = ["pending"]
        if status_value in {"ready", "shipped", "delivered", "returned"}:
            event_states.append("ready")
        if status_value in {"shipped", "delivered", "returned"}:
            event_states.append("shipped")
        if status_value == "delivered":
            event_states.append("delivered")
        if status_value == "returned":
            event_states.append("returned")
        for event_index, event_status in enumerate(event_states, start=1):
            await put(
                db,
                ShipmentEvent,
                "shipment-event",
                f"{status_value}:{event_status}",
                shipment_id=shipment.id,
                status=event_status,
                location="ศูนย์กระจายสินค้าตัวอย่าง",
                note=f"เปลี่ยนสถานะเป็น {event_status}",
                event_at=now - timedelta(hours=len(event_states) - event_index),
                created_by=user_id,
            )
        count(summary, "shipments")
    return summary


async def seed_shared_kitchen_and_distribution_showcase(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    context: dict[str, Any],
) -> dict[str, int]:
    summary: dict[str, int] = {}
    now = utc_now()
    brands = (await db.scalars(select(Brand).where(Brand.company_id == company_id, Brand.is_active.is_(True)))).all()
    branches = (await db.scalars(select(Branch).where(Branch.company_id == company_id, Branch.is_active.is_(True)))).all()
    raw_products = (
        await db.scalars(
            select(Product)
            .where(Product.company_id == company_id, Product.is_active.is_(True))
            .order_by(Product.product_type.desc(), Product.sku)
            .limit(3)
        )
    ).all()
    if len(brands) < 3 or len(branches) < 3 or len(raw_products) < 3:
        raise RuntimeError("Shared kitchen showcase references are incomplete")
    kitchen, _ = await put(
        db,
        CompanyKitchen,
        "company-kitchen",
        "main",
        company_id=company_id,
        branch_id=context["main_branch_id"],
        raw_location_id=context["raw_location_id"],
        name="ครัวกลาง Foodchainservice",
        timezone="Asia/Bangkok",
        costing_method="fifo",
        allow_negative_stock=False,
        is_active=True,
        created_by=user_id,
    )
    ingredients: list[CompanyIngredient] = []
    for index, product in enumerate(raw_products, start=1):
        ingredient, _ = await put(
            db,
            CompanyIngredient,
            "company-ingredient",
            str(index),
            company_id=company_id,
            canonical_product_id=product.id,
            code=f"UI-ING-{index:03d}",
            name=("เนื้อหมูส่วนสะโพก", "น้ำมันพืช", "เครื่องปรุงรวม")[index - 1],
            base_unit_code="KG" if index < 3 else "PCS",
            unit_dimension="mass" if index < 3 else "count",
            is_active=True,
        )
        lot, _ = await put(
            db,
            CompanyIngredientLot,
            "ingredient-lot",
            str(index),
            company_id=company_id,
            kitchen_id=kitchen.id,
            ingredient_id=ingredient.id,
            lot_code=f"UI-LOT-{index:03d}",
            received_at=now - timedelta(days=index),
            expires_on=date.today() + timedelta(days=3 * index),
            qty_on_hand=Decimal(str(18 - index * 3)),
            unit_cost=Decimal(str(75 + index * 15)),
        )
        await put(
            db,
            CompanyKitchenMovement,
            "kitchen-movement",
            str(index),
            company_id=company_id,
            kitchen_id=kitchen.id,
            ingredient_id=ingredient.id,
            lot_id=lot.id,
            location_id=context["raw_location_id"],
            brand_id=brands[index % len(brands)].id,
            production_order_id=None,
            reversal_of_id=None,
            movement_type=("receipt", "adjustment", "waste")[index - 1],
            qty=Decimal("15") if index == 1 else Decimal("2") if index == 2 else Decimal("-1"),
            qty_before=Decimal("0") if index == 1 else Decimal("12"),
            qty_after=Decimal("15") if index == 1 else Decimal("14") if index == 2 else Decimal("11"),
            unit_cost=lot.unit_cost,
            idempotency_key=f"ui-showcase-kitchen-movement-{index}",
            reference_type="ui_showcase",
            reference_id=f"UI-KITCHEN-{index}",
            note="ข้อมูลเคลื่อนไหววัตถุดิบตัวอย่าง",
            actor_id=user_id,
            created_at=now - timedelta(hours=index),
        )
        ingredients.append(ingredient)
        count(summary, "ingredients")

    restaurant_brand = next((row for row in brands if row.business_type == "restaurant"), brands[0])
    production_states = ("planned", "in_progress", "completed")
    for index, status_value in enumerate(production_states, start=1):
        product = raw_products[(index - 1) % len(raw_products)]
        recipe, _ = await put(
            db,
            Recipe,
            "company-production-recipe",
            str(index),
            company_id=company_id,
            branch_id=None,
            brand_id=restaurant_brand.id,
            product_id=product.id,
            recipe_type="central_production",
            version_no=1,
            effective_from=date.today() - timedelta(days=30),
            effective_to=None,
            name=f"สูตรผลิตส่วนกลาง {product.name}",
            yield_qty=Decimal("10"),
            yield_unit="PCS",
            loss_percent=Decimal("3"),
            notes="[UI SHOWCASE] สูตรผลิตตัวอย่าง",
            is_active=True,
        )
        demand, _ = await put(
            db,
            CompanyProductionDemand,
            "company-production-demand",
            str(index),
            company_id=company_id,
            brand_id=restaurant_brand.id,
            branch_id=context["main_branch_id"],
            output_product_id=product.id,
            needed_on=date.today() + timedelta(days=index),
            requested_qty=Decimal(str(index * 10)),
            unit_code="PCS",
            status="converted" if status_value != "planned" else "submitted",
            source_type="ui_showcase",
            source_id=f"UI-PRODUCTION-DEMAND-{index}",
            idempotency_key=f"ui-showcase-production-demand-{index}",
            requested_by=user_id,
            note="ความต้องการผลิตตัวอย่าง",
        )
        order, _ = await put(
            db,
            CompanyProductionOrder,
            "company-production-order",
            str(index),
            company_id=company_id,
            kitchen_id=kitchen.id,
            brand_id=restaurant_brand.id,
            demand_id=demand.id,
            recipe_id=recipe.id,
            output_product_id=product.id,
            ready_location_id=context["ready_location_id"],
            order_number=f"UI-PROD-{index:03d}",
            planned_date=date.today(),
            status=status_value,
            planned_qty=Decimal(str(index * 10)),
            actual_output_qty=Decimal(str(index * 9)) if status_value == "completed" else None,
            waste_qty=Decimal("1") if status_value == "completed" else Decimal("0"),
            output_unit_code="PCS",
            total_input_cost=Decimal(str(index * 700)) if status_value == "completed" else Decimal("0"),
            output_cost_per_unit=Decimal("75") if status_value == "completed" else Decimal("0"),
            idempotency_key=f"ui-showcase-production-order-{index}",
            completion_key=f"ui-showcase-production-complete-{index}" if status_value == "completed" else None,
            reversal_key=None,
            planned_by=user_id,
            started_by=user_id if status_value != "planned" else None,
            completed_by=user_id if status_value == "completed" else None,
            reversed_by=None,
            started_at=now - timedelta(hours=2) if status_value != "planned" else None,
            completed_at=now - timedelta(minutes=15) if status_value == "completed" else None,
            reversed_at=None,
            note="[UI SHOWCASE] ใบผลิตครัวกลาง",
        )
        await put(
            db,
            CompanyProductionInput,
            "company-production-input",
            str(index),
            company_id=company_id,
            order_id=order.id,
            ingredient_id=ingredients[(index - 1) % len(ingredients)].id,
            planned_qty=Decimal(str(index * 5)),
            actual_qty=Decimal(str(index * 4)) if status_value == "completed" else None,
            base_unit_code=ingredients[(index - 1) % len(ingredients)].base_unit_code,
            actual_cost=Decimal(str(index * 700)) if status_value == "completed" else Decimal("0"),
        )
        count(summary, "production_orders")

    modules = ("restaurant_pos", "takeaway_pos", "retail_pos")
    statuses = ("submitted", "partially_allocated", "fulfilled")
    distribution_demands: list[CompanyDistributionDemand] = []
    for index, module in enumerate(modules, start=1):
        business_type = module.removesuffix("_pos")
        brand = next(
            (row for row in brands if row.business_type in {business_type, f"{business_type}_pos"}),
            brands[index - 1],
        )
        linked_branch = next((row for row in branches if row.id == brand.central_branch_id), branches[index - 1])
        product = raw_products[(index - 1) % len(raw_products)]
        distribution_demand, _ = await put(
            db,
            CompanyDistributionDemand,
            "distribution-demand",
            module,
            company_id=company_id,
            source_module=module,
            brand_id=brand.id,
            branch_id=linked_branch.id,
            product_id=product.id,
            needed_on=date.today() + timedelta(days=index),
            requested_qty=Decimal(str(index * 10)),
            unit_code="PCS",
            status=statuses[index - 1],
            source_type="ui_showcase",
            source_id=f"UI-DEMAND-{index}",
            idempotency_key=f"ui-showcase-distribution-{module}",
            payload_hash=digest(f"distribution:{module}"),
            requested_by=user_id,
            note="[UI SHOWCASE] ความต้องการสินค้าจากแต่ละระบบ POS",
        )
        distribution_demands.append(distribution_demand)
        count(summary, "distribution_demands")
    transfers = (
        await db.scalars(
            select(TransferOrder)
            .where(TransferOrder.company_id == company_id, TransferOrder.to_number.like("UI-TO-%"))
            .order_by(TransferOrder.to_number)
            .limit(3)
        )
    ).all()
    shipment_states = ("planned", "in_transit", "received")
    if len(transfers) == 3:
        for index, (module, status_value, demand, transfer) in enumerate(
            zip(modules, shipment_states, distribution_demands, transfers, strict=True), start=1
        ):
            shipped = Decimal("0") if status_value == "planned" else Decimal(str(index * 10))
            received = shipped if status_value == "received" else Decimal("0")
            shipment, _ = await put(
                db,
                CompanyDistributionShipment,
                "distribution-shipment",
                module,
                company_id=company_id,
                demand_id=demand.id,
                transfer_order_id=transfer.id,
                source_module=module,
                brand_id=demand.brand_id,
                branch_id=demand.branch_id,
                product_id=demand.product_id,
                from_location_id=context["ready_location_id"],
                to_location_id=context["showcase_location_id"],
                shipment_number=f"UI-DIST-{index:03d}",
                status=status_value,
                planned_qty=Decimal(str(index * 10)),
                shipped_qty=shipped,
                received_qty=received,
                rejected_qty=Decimal("0"),
                returned_qty=Decimal("0"),
                unit_code="PCS",
                unit_cost=Decimal("75"),
                idempotency_key=f"ui-showcase-distribution-shipment-{module}",
                payload_hash=digest(f"distribution-shipment:{module}"),
                planned_by=user_id,
                dispatched_at=now - timedelta(hours=2) if status_value != "planned" else None,
                settled_at=now - timedelta(minutes=30) if status_value == "received" else None,
                note="[UI SHOWCASE] งานกระจายสินค้าจากส่วนกลาง",
            )
            event_type = "received" if status_value == "received" else "dispatched" if status_value == "in_transit" else "planned"
            await put(
                db,
                CompanyDistributionEvent,
                "distribution-event",
                module,
                company_id=company_id,
                shipment_id=shipment.id,
                transfer_order_id=transfer.id,
                source_module=module,
                event_type=event_type,
                qty=received if event_type == "received" else shipped if event_type == "dispatched" else Decimal(str(index * 10)),
                unit_code="PCS",
                idempotency_key=f"ui-showcase-distribution-event-{module}",
                payload_hash=digest(f"distribution-event:{module}"),
                metadata_json={"ui_showcase": True},
                actor_id=user_id,
                note="สถานะกระจายสินค้าตัวอย่าง",
                created_at=now - timedelta(hours=index),
            )
            count(summary, "distribution_shipments")
    summary["company_kitchens"] = 1
    return summary


async def seed_legacy_showcase(
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    context: dict[str, Any],
) -> dict[str, int]:
    summary: dict[str, int] = {}
    async with AsyncSessionLocal() as db:
        parts = [
            await seed_sales_showcase(
                db,
                company_id=company_id,
                branch_id=context["main_branch_id"],
                location_id=context["main_location_id"],
                user_id=user_id,
                namespace="restaurant",
            ),
            await seed_inventory_and_purchasing_showcase(db, company_id=company_id, user_id=user_id, context=context),
            await seed_crm_showcase(db, company_id=company_id, user_id=user_id),
            await seed_hr_showcase(db, company_id=company_id, branch_id=context["main_branch_id"], user_id=user_id),
            await seed_accounting_and_channels_showcase(db, company_id=company_id, branch_id=context["main_branch_id"], user_id=user_id),
            await seed_logistics_showcase(db, company_id=company_id, branch_id=context["main_branch_id"], user_id=user_id),
            await seed_shared_kitchen_and_distribution_showcase(db, company_id=company_id, user_id=user_id, context=context),
        ]
        for part in parts:
            for key, value in part.items():
                count(summary, key, value)
        await db.commit()
    return summary


def reference_for_business(
    references: dict[str, list[dict[str, Any]]], business_type: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    accepted_types = {business_type, f"{business_type}_pos"}
    brand = next((row for row in references["brands"] if row["business_type"] in accepted_types), None)
    if brand is None:
        raise RuntimeError(f"{business_type} Brand was not found")
    link = next((row for row in references["links"] if row["brand_id"] == brand["id"] and row["is_active"]), None)
    if link is None:
        raise RuntimeError(f"{business_type} Brand has no active Branch")
    branch = next(row for row in references["branches"] if row["id"] == link["branch_id"])
    return brand, branch


async def seed_retail_showcase(
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    references: dict[str, list[dict[str, Any]]],
) -> dict[str, int]:
    summary: dict[str, int] = {}
    brand, branch = reference_for_business(references, "retail")
    async with RetailSessionLocal() as db:
        unit, _ = await put(
            db,
            Unit,
            "retail-unit",
            "pcs",
            company_id=company_id,
            code="UI-PCS",
            name="ชิ้น",
            name_en="Piece",
            decimal_places=0,
            is_active=True,
        )
        categories: list[Category] = []
        for index, (code, name) in enumerate(
            (("GROCERY", "สินค้าอุปโภคบริโภค"), ("BEAUTY", "สุขภาพและความงาม"), ("HOME", "ของใช้ในบ้าน"), ("SERVICE", "บริการและการจอง")),
            start=1,
        ):
            category, _ = await put(
                db,
                Category,
                "retail-category",
                code,
                company_id=company_id,
                parent_id=None,
                code=f"UI-RTL-{code}",
                name=name,
                name_en=code.title(),
                description="[UI SHOWCASE] หมวดสินค้าขายปลีก",
                sort_order=index,
                is_active=True,
            )
            categories.append(category)
        products: list[Product] = []
        names = (
            "น้ำดื่มแพ็ก", "ขนมขบเคี้ยว", "กาแฟพร้อมดื่ม", "บะหมี่กึ่งสำเร็จรูป",
            "แชมพูสมุนไพร", "สบู่เหลว", "หน้ากากอนามัย", "วิตามินรวม",
            "น้ำยาล้างจาน", "กระดาษทิชชู", "ถุงขยะ", "หลอดไฟ LED",
            "บริการซักรีด", "คูปองอาหารเช้า", "จองห้องประชุม", "แพ็กเกจสปา",
        )
        for index, name in enumerate(names, start=1):
            price = Decimal(25 + index * 12)
            product, _ = await put(
                db,
                Product,
                "retail-product",
                str(index),
                company_id=company_id,
                category_id=categories[(index - 1) // 4].id,
                brand_id=brand["id"],
                unit_id=unit.id,
                sku=f"UI-RTL-{index:03d}",
                barcode=f"88599990{index:05d}",
                name=name,
                name_en=f"Retail demo item {index}",
                description="ข้อมูลสินค้าตัวอย่างสำหรับจัดหน้า Retail POS",
                product_type="service" if index > 12 else "simple",
                inventory_role="not_stocked" if index > 12 else "store_local",
                cost_price=(price * Decimal("0.62")).quantize(Decimal("0.01")),
                selling_price=price,
                vat_type="included",
                vat_rate=Decimal("7"),
                weight_grams=None if index > 12 else 100 + index * 25,
                is_active=index != 16,
                is_for_sale=True,
                is_for_purchase=index <= 12,
                min_stock_qty=Decimal("5"),
            )
            products.append(product)
        location = await ensure_location(db, company_id, branch["id"], "UI-MAIN", "คลัง Retail Showcase")
        price_list, _ = await put(
            db,
            PriceList,
            "retail-price-list",
            "default",
            company_id=company_id,
            name="ราคาขายปลีกมาตรฐาน",
            currency="THB",
            is_default=True,
            is_active=True,
        )
        for index, product in enumerate(products, start=1):
            await put(
                db,
                PriceListItem,
                "retail-price-item",
                str(index),
                company_id=company_id,
                price_list_id=price_list.id,
                product_id=product.id,
                variant_id=None,
                price=product.selling_price,
                min_qty=Decimal("1"),
            )
            if product.product_type != "service":
                qty = Decimal("0") if index == 3 else Decimal("3") if index == 2 else Decimal(str(10 + index * 2))
                await put(
                    db,
                    StockBalance,
                    "retail-stock-balance",
                    str(index),
                    company_id=company_id,
                    branch_id=branch["id"],
                    location_id=location.id,
                    product_id=product.id,
                    variant_id=None,
                    qty_on_hand=qty,
                    qty_reserved=Decimal("2") if index == 4 else Decimal("0"),
                    cost_per_unit=product.cost_price,
                    last_movement_at=utc_now() - timedelta(hours=index),
                )
            count(summary, "products")
        sale_summary = await seed_sales_showcase(
            db,
            company_id=company_id,
            branch_id=branch["id"],
            location_id=location.id,
            user_id=user_id,
            namespace="retail",
        )
        for key, value in sale_summary.items():
            count(summary, key, value)
        summary["categories"] = len(categories)
        await db.commit()
    return summary


async def seed_takeaway_showcase(
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    references: dict[str, list[dict[str, Any]]],
) -> dict[str, int]:
    summary: dict[str, int] = {}
    now = utc_now()
    brand, branch = reference_for_business(references, "takeaway")
    async with TakeawaySessionLocal() as db:
        await put(
            db,
            TakeawayUnit,
            "takeaway-unit",
            "pcs",
            company_id=company_id,
            code="PCS",
            name="ชิ้น",
            name_en="Piece",
            decimal_places=0,
            is_active=True,
        )
        categories: list[TakeawayCategory] = []
        for index, (code, name) in enumerate((("FOOD", "อาหาร"), ("DRINK", "เครื่องดื่ม"), ("DESSERT", "ของหวาน"), ("SPECIAL", "เมนูพิเศษ")), start=1):
            category, _ = await put(
                db,
                TakeawayCategory,
                "takeaway-category",
                code,
                company_id=company_id,
                brand_id=brand["id"],
                code=f"UI-{code}",
                name=name,
                sort_order=index,
                is_active=True,
            )
            categories.append(category)
        items: list[TakeawayCatalogItem] = []
        names = (
            "หมูแดดเดียว", "หมูย่างสมุนไพร", "ข้าวเหนียว", "ไก่ทอดกรอบ",
            "ชาไทย", "กาแฟเย็น", "น้ำมะนาว", "น้ำดื่ม",
            "ข้าวเหนียวมะม่วง", "บัวลอยไข่หวาน", "เฉาก๊วยนมสด", "ไอศกรีมกะทิ",
            "ชุดอิ่มคุ้ม", "ชุดครอบครัว", "เมนูประจำวัน", "โปรพิเศษ UAT",
        )
        for index, name in enumerate(names, start=1):
            item, _ = await put(
                db,
                TakeawayCatalogItem,
                "takeaway-item",
                str(index),
                company_id=company_id,
                brand_id=brand["id"],
                category_id=categories[(index - 1) // 4].id,
                sku=f"UI-TW-{index:03d}",
                barcode=f"88588880{index:05d}",
                name=name,
                unit="ชิ้น",
                price=Decimal(25 + index * 8),
                tax_rate=Decimal("7"),
                kitchen_station="ครัวร้อน" if index <= 4 else "เครื่องดื่ม" if index <= 8 else "จัดชุด",
                track_stock=True,
                is_active=index != 16,
                source_metadata={"ui_showcase": True, "sort": index},
            )
            items.append(item)
            await put(
                db,
                TakeawayBranchCatalogItem,
                "takeaway-branch-item",
                str(index),
                company_id=company_id,
                brand_id=brand["id"],
                branch_id=branch["id"],
                catalog_item_id=item.id,
                price_override=Decimal(99) if index == 13 else None,
                is_available=index not in {3, 16},
            )
            count(summary, "catalog_items")
        store, _ = await put(
            db,
            TakeawayStockLocation,
            "takeaway-location",
            "store",
            company_id=company_id,
            branch_id=branch["id"],
            code="UI-TW-STORE",
            name="คลังหน้าร้าน Takeaway",
            location_type="store",
            is_active=True,
        )
        central, _ = await put(
            db,
            TakeawayStockLocation,
            "takeaway-location",
            "central",
            company_id=company_id,
            branch_id=branch["id"],
            code="UI-TW-CENTRAL",
            name="คลังพร้อมขายส่วนกลาง",
            location_type="central_ready",
            is_active=True,
        )
        for index, item in enumerate(items, start=1):
            qty = Decimal("0") if index == 2 else Decimal("3") if index == 3 else Decimal(str(index + 8))
            await put(
                db,
                TakeawayStockBalance,
                "takeaway-stock",
                str(index),
                company_id=company_id,
                location_id=store.id,
                item_id=item.id,
                lot_code="",
                on_hand_qty=qty,
                reserved_qty=Decimal("2") if index == 4 else Decimal("0"),
                average_cost=(item.price * Decimal("0.55")).quantize(Decimal("0.01")),
            )
        shift, _ = await put(
            db,
            TakeawayShift,
            "takeaway-shift",
            "open",
            company_id=company_id,
            brand_id=brand["id"],
            branch_id=branch["id"],
            business_date=date.today(),
            round_no=99,
            opened_by=user_id,
            opened_at=now - timedelta(hours=4),
            opening_cash=Decimal("1000"),
            status="open",
            closed_by=None,
            closed_at=None,
            expected_cash=None,
            counted_cash=None,
            close_note="[UI SHOWCASE] กะขายจำลอง",
        )
        order_states = (
            ("draft", "awaiting_payment", "counter"),
            ("paid", "queued", "counter"),
            ("paid", "preparing", "qr"),
            ("paid", "ready", "online"),
            ("paid", "picked_up", "counter"),
            ("cancelled", "cancelled", "online"),
            ("refunded", "picked_up", "counter"),
        )
        orders: list[TakeawayOrder] = []
        for index, (status_value, fulfillment, channel) in enumerate(order_states, start=1):
            item = items[(index - 1) % len(items)]
            total = item.price * index
            order, _ = await put(
                db,
                TakeawayOrder,
                "takeaway-order",
                str(index),
                company_id=company_id,
                brand_id=brand["id"],
                branch_id=branch["id"],
                shift_id=shift.id,
                order_number=f"UI-TW-ORD-{index:04d}",
                business_date=date.today(),
                queue_number=80 + index,
                channel=channel,
                status=status_value,
                fulfillment_status=fulfillment,
                subtotal=total,
                discount_amount=Decimal("10") if index == 4 else Decimal("0"),
                tax_amount=(total * Decimal("7") / Decimal("107")).quantize(Decimal("0.01")),
                total_amount=total,
                customer_name=f"ลูกค้า Takeaway {index}",
                customer_phone=f"09420000{index:02d}",
                note="[UI SHOWCASE] ออเดอร์รับกลับ",
                idempotency_key=f"ui-showcase-takeaway-order-{index}",
                paid_at=now - timedelta(minutes=index * 5) if status_value in {"paid", "refunded"} else None,
                picked_up_at=now - timedelta(minutes=2) if fulfillment == "picked_up" else None,
                source_metadata={"ui_showcase": True},
            )
            orders.append(order)
            order_item, _ = await put(
                db,
                TakeawayOrderItem,
                "takeaway-order-item",
                str(index),
                order_id=order.id,
                catalog_item_id=item.id,
                sku=item.sku,
                name=item.name,
                quantity=Decimal(str(index)),
                unit_price=item.price,
                discount_amount=Decimal("0"),
                tax_amount=(total * Decimal("7") / Decimal("107")).quantize(Decimal("0.01")),
                line_total=total,
                kitchen_station=item.kitchen_station,
                note="ไม่เผ็ด" if index == 3 else None,
            )
            if status_value in {"paid", "refunded"}:
                await put(
                    db,
                    TakeawayPayment,
                    "takeaway-payment",
                    str(index),
                    order_id=order.id,
                    method=("cash", "promptpay", "card")[index % 3],
                    amount=total,
                    status="refunded" if status_value == "refunded" else "captured",
                    reference=f"UI-TW-PAY-{index}",
                    idempotency_key=f"ui-showcase-takeaway-payment-{index}",
                    paid_at=now - timedelta(minutes=index * 5),
                )
                await put(
                    db,
                    TakeawayReceipt,
                    "takeaway-receipt",
                    str(index),
                    order_id=order.id,
                    company_id=company_id,
                    branch_id=branch["id"],
                    receipt_number=f"UI-TW-RCPT-{index:04d}",
                    payload={"demo": True, "total": str(total)},
                    issued_at=now - timedelta(minutes=index * 5),
                )
            if fulfillment in {"queued", "preparing", "ready", "picked_up"}:
                await put(
                    db,
                    TakeawayKitchenTicket,
                    "takeaway-kitchen-ticket",
                    str(index),
                    company_id=company_id,
                    brand_id=brand["id"],
                    branch_id=branch["id"],
                    order_id=order.id,
                    order_item_id=order_item.id,
                    queue_number=80 + index,
                    station=item.kitchen_station or "default",
                    item_name=item.name,
                    quantity=Decimal(str(index)),
                    status="done" if fulfillment == "picked_up" else fulfillment,
                    ready_at=now if fulfillment in {"ready", "picked_up"} else None,
                )
            await put(
                db,
                TakeawayPickupToken,
                "takeaway-pickup-token",
                str(index),
                order_id=order.id,
                token_hash=digest(f"ui-showcase-pickup-{index}"),
                expires_at=now + timedelta(hours=4),
                redeemed_at=now if fulfillment == "picked_up" else None,
            )
            count(summary, "orders")

        round_row, _ = await put(
            db,
            TakeawayCentralOrderRound,
            "takeaway-central-round",
            "today",
            company_id=company_id,
            brand_id=brand["id"],
            business_date=date.today(),
            round_no=99,
            cutoff_at=now + timedelta(hours=2),
            status="open",
        )
        for index, status_value in enumerate(("submitted", "approved", "fulfilled"), start=1):
            central_order, _ = await put(
                db,
                TakeawayCentralOrder,
                "takeaway-central-order",
                status_value,
                company_id=company_id,
                brand_id=brand["id"],
                branch_id=branch["id"],
                round_id=round_row.id,
                order_number=f"UI-TW-CENTRAL-{index:03d}",
                order_type="urgent" if index == 2 else "regular",
                status=status_value,
                requested_delivery_date=date.today() + timedelta(days=1),
                submitted_by=user_id,
                note="ใบสั่งจากส่วนกลางตัวอย่าง",
            )
            await put(
                db,
                TakeawayCentralOrderItem,
                "takeaway-central-item",
                str(index),
                central_order_id=central_order.id,
                catalog_item_id=items[index - 1].id,
                sku=items[index - 1].sku,
                item_name=items[index - 1].name,
                quantity=Decimal(str(index * 10)),
                unit="ชิ้น",
                source_kind="catalog",
                approval_status="approved" if index > 1 else "pending",
            )
            count(summary, "central_orders")

        for index, status_value in enumerate(("planned", "in_progress", "completed"), start=1):
            batch, _ = await put(
                db,
                TakeawayProductionBatch,
                "takeaway-production-batch",
                status_value,
                company_id=company_id,
                brand_id=brand["id"],
                location_id=central.id,
                batch_number=f"UI-TW-BATCH-{index:03d}",
                status=status_value,
                planned_at=now - timedelta(hours=index),
                started_at=now - timedelta(minutes=45) if status_value != "planned" else None,
                completed_at=now - timedelta(minutes=5) if status_value == "completed" else None,
                created_by=user_id,
            )
            await put(
                db,
                TakeawayProductionLine,
                "takeaway-production-line",
                str(index),
                batch_id=batch.id,
                item_id=items[index - 1].id,
                line_type="output",
                planned_qty=Decimal(str(index * 20)),
                actual_qty=Decimal(str(index * 19)) if status_value == "completed" else None,
                unit="ชิ้น",
            )
            count(summary, "production_batches")

        for index, status_value in enumerate(("draft", "shipped", "received"), start=1):
            transfer, _ = await put(
                db,
                TakeawayTransfer,
                "takeaway-transfer",
                status_value,
                company_id=company_id,
                brand_id=brand["id"],
                transfer_number=f"UI-TW-TR-{index:03d}",
                from_location_id=central.id,
                to_location_id=store.id,
                status=status_value,
                requested_by=user_id,
                shipped_at=now - timedelta(hours=2) if status_value in {"shipped", "received"} else None,
                received_at=now - timedelta(minutes=30) if status_value == "received" else None,
            )
            await put(
                db,
                TakeawayTransferItem,
                "takeaway-transfer-item",
                str(index),
                transfer_id=transfer.id,
                item_id=items[index - 1].id,
                requested_qty=Decimal("20"),
                shipped_qty=Decimal("18") if status_value != "draft" else None,
                received_qty=Decimal("18") if status_value == "received" else None,
                unit="ชิ้น",
            )
            count(summary, "transfers")

        account, _ = await put(
            db,
            TakeawayCreditAccount,
            "takeaway-credit-account",
            "main",
            company_id=company_id,
            brand_id=brand["id"],
            branch_id=branch["id"],
            credit_limit=Decimal("50000"),
            balance=Decimal("8500"),
            status="active",
        )
        for index, entry_type in enumerate(("charge", "payment"), start=1):
            await put(
                db,
                TakeawayCreditEntry,
                "takeaway-credit-entry",
                entry_type,
                account_id=account.id,
                entry_type=entry_type,
                amount=Decimal("10000") if entry_type == "charge" else Decimal("1500"),
                reference_type="central_order",
                reference_id=orders[index - 1].id,
                idempotency_key=f"ui-showcase-credit-{entry_type}",
                occurred_at=now - timedelta(days=2 - index),
            )
        summary["credit_accounts"] = 1
        summary["categories"] = len(categories)
        summary["stock_locations"] = 2
        await db.commit()
    return summary


async def run(args: argparse.Namespace) -> dict[str, Any]:
    require_uat(args)
    company, user = await require_platform_context(args.company_id, args.username)
    await provision_restaurant_showcase_branch(company.id, user.id)
    projections = await project_references(company.id)
    references = await platform_reference_snapshot(company.id)
    await mirror_platform_references_to_legacy(company, references)
    platform = await seed_platform_showcase(company.id, user.id)
    catalog = await seed_legacy_catalog(company.id)
    restaurant = await seed_restaurant_showcase(company.id, user.id, catalog)
    legacy = await seed_legacy_showcase(company.id, user.id, catalog)
    retail = await seed_retail_showcase(company.id, user.id, references)
    takeaway = await seed_takeaway_showcase(company.id, user.id, references)
    return {
        "status": "ok",
        "dataset": "ui_showcase",
        "environment": settings.environment,
        "public_base_url": settings.saas_public_base_url,
        "company_id": str(company.id),
        "company_name": company.name,
        "production_activated": False,
        "idempotent": True,
        "projections": projections,
        "platform": platform,
        "restaurant": restaurant,
        "legacy_erp": legacy,
        "retail": retail,
        "takeaway": takeaway,
    }


def main() -> None:
    args = build_parser().parse_args()
    result = asyncio.run(run(args))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
