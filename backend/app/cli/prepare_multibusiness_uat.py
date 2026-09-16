from __future__ import annotations

import argparse
import asyncio
from datetime import date
from decimal import Decimal
import json
from typing import Sequence
import uuid
from urllib.parse import urlsplit

from sqlalchemy import select

from app.config import settings
from app.database import (
    AsyncSessionLocal,
    PlatformSessionLocal,
    RetailSessionLocal,
    TakeawaySessionLocal,
)
from app.dependencies import TokenData
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.company import Company
from app.models.platform import PlatformTenantProfile
from app.models.product import Category, PriceList, PriceListItem, Product, Unit
from app.models.restaurant import Brand, BrandBranch
from app.models.saas_billing import SaasPlan
from app.models.settings import BranchSettings
from app.models.stock import StockBalance, StockLocation
from app.models.takeaway import (
    TakeawayCatalogItem,
    TakeawayCategory,
    TakeawayStockMovement,
    TakeawayStockLocation,
)
from app.models.user import User
from app.schemas.company_workspace import CompanyWorkspaceProvisionRequest
from app.schemas.takeaway import TakeawayStockMovementCreate
from app.services.company_workspace_service import CompanyWorkspaceService
from app.services.platform_reference_projection import (
    process_projection_batch,
    seed_snapshot_events,
    verify_projection_parity,
)
from app.services.retail_migration_service import (
    migrate_retail_operational_data,
    reconcile_retail_operational_data,
)
from app.services.retail_reference_projector import (
    project_retail_reference_snapshot,
    verify_retail_reference_parity,
)
from app.services.takeaway_reference_projector import (
    project_takeaway_reference_snapshot,
    verify_takeaway_reference_parity,
)
from app.services.takeaway_service import TakeawayService


UAT_PLAN_CODE = "uat-multibusiness"
UAT_FLAGS = {
    "restaurant": True,
    "restaurant_pos": True,
    "takeaway": True,
    "takeaway_pos": True,
    "retail_pos": True,
    "erp": True,
    "central_kitchen": True,
    "hotel_pms": False,
}
UAT_LIMITS = {"brands": 0, "branches": 0, "users": 0, "devices": 0}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Idempotently prepare controlled Takeaway and Retail workspaces in UAT.",
    )
    parser.add_argument("--company-id", type=uuid.UUID, required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--yes", action="store_true")
    return parser


def require_uat(args: argparse.Namespace) -> None:
    hostname = urlsplit(settings.saas_public_base_url).hostname or ""
    if not args.yes:
        raise RuntimeError("Pass --yes to prepare persistent UAT data")
    if settings.environment != "development" or not hostname.startswith("uat-"):
        raise RuntimeError("This command is restricted to the HTTPS uat-* development environment")
    if settings.identity_database != "platform_core" or not settings.reference_projector_enabled:
        raise RuntimeError("UAT preparation requires Platform identity and reference projection")
    if not settings.takeaway_feature_enabled or settings.takeaway_service_database != "takeaway":
        raise RuntimeError("UAT preparation requires the Takeaway dark-launch runtime")
    if TakeawaySessionLocal is None or RetailSessionLocal is None:
        raise RuntimeError("Takeaway and Retail database URLs are required")


async def enable_uat_plan(
    company_id: uuid.UUID,
    username: str,
) -> tuple[User, Company]:
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

        plan = await db.scalar(select(SaasPlan).where(SaasPlan.code == UAT_PLAN_CODE))
        if plan is None:
            plan = SaasPlan(
                code=UAT_PLAN_CODE,
                name="UAT Multi-business",
                description="Internal non-production plan for controlled module activation",
                currency="THB",
                billing_interval="month",
                unit_amount_satang=0,
                feature_flags=UAT_FLAGS.copy(),
                plan_limits=UAT_LIMITS.copy(),
                is_public=False,
                is_active=True,
            )
            db.add(plan)
        else:
            plan.feature_flags = UAT_FLAGS.copy()
            plan.plan_limits = UAT_LIMITS.copy()
            plan.is_public = False
            plan.is_active = True

        profile = await db.scalar(
            select(PlatformTenantProfile).where(
                PlatformTenantProfile.company_id == company_id
            )
        )
        if profile is None:
            profile = PlatformTenantProfile(
                company_id=company_id,
                plan_code=UAT_PLAN_CODE,
                feature_flags=UAT_FLAGS.copy(),
                plan_limits=UAT_LIMITS.copy(),
            )
            db.add(profile)
        else:
            profile.plan_code = UAT_PLAN_CODE
            profile.feature_flags = UAT_FLAGS.copy()
            profile.plan_limits = UAT_LIMITS.copy()
        db.add(
            AuditLog(
                company_id=company_id,
                user_id=user.id,
                action="uat.multibusiness.prepare",
                resource="PlatformTenantProfile",
                resource_id=str(company_id),
                new_value={"plan_code": UAT_PLAN_CODE, "modules": ["takeaway_pos", "retail_pos"]},
            )
        )
        await db.commit()
        await db.refresh(user)
        await db.refresh(company)
        return user, company


async def provision_workspaces(
    company_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[object, object]:
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
        service = CompanyWorkspaceService(db)
        takeaway = await service.provision(
            current,
            CompanyWorkspaceProvisionRequest(
                idempotency_key="wp10-takeaway-uat-v1",
                module_key="takeaway_pos",
                brand_slug="foodchain-takeaway-uat",
                brand_name="Foodchainservice Takeaway UAT",
                branch_code="TW-01",
                branch_name="สาขาทดสอบ Takeaway",
                branch_type="company_owned",
                storefront_mode="food_stall",
            ),
            ip_address=None,
            user_agent="prepare-multibusiness-uat",
        )
        retail = await service.provision(
            current,
            CompanyWorkspaceProvisionRequest(
                idempotency_key="wp13-retail-uat-v1",
                module_key="retail_pos",
                brand_slug="foodchain-retail-uat",
                brand_name="Foodchainservice Retail UAT",
                branch_code="RTL-01",
                branch_name="สาขาทดสอบ Retail",
                branch_type="company_owned",
                storefront_mode="food_stall",
            ),
            ip_address=None,
            user_agent="prepare-multibusiness-uat",
        )
        for workspace in (takeaway.workspace, retail.workspace):
            brand = await db.get(Brand, workspace.brand_id)
            if brand is not None and brand.central_branch_id is None:
                brand.central_branch_id = workspace.branch_id
        await db.commit()
        return takeaway.workspace, retail.workspace


async def project_platform_references() -> dict[str, object]:
    async with PlatformSessionLocal() as db:
        seeded = await seed_snapshot_events(db)
        await db.commit()
    claimed = applied = replayed = failed = 0
    while True:
        batch = await process_projection_batch(limit=100)
        claimed += batch.claimed
        applied += batch.applied
        replayed += batch.replayed
        failed += batch.failed
        if batch.claimed == 0 or batch.failed:
            break
    parity = await verify_projection_parity()
    if failed or any(not row.matches for row in parity):
        raise RuntimeError("Platform to Restaurant reference projection failed")
    return {
        "seeded": seeded,
        "claimed": claimed,
        "applied": applied,
        "replayed": replayed,
        "failed": failed,
    }


async def ensure_legacy_retail_source(
    *,
    platform_company: Company,
    retail_workspace,
) -> dict[str, str]:
    company_id = platform_company.id
    async with AsyncSessionLocal() as db:
        company = await db.get(Company, company_id)
        if company is None:
            company = Company(
                id=company_id,
                name=platform_company.name,
                business_slug=platform_company.business_slug,
                is_active=True,
            )
            db.add(company)
            await db.flush()

        branch = await db.get(Branch, retail_workspace.branch_id)
        if branch is None:
            branch = Branch(
                id=retail_workspace.branch_id,
                company_id=company_id,
                code=retail_workspace.branch_code,
                name=retail_workspace.branch_name,
                is_active=True,
            )
            db.add(branch)
            await db.flush()
        brand = await db.get(Brand, retail_workspace.brand_id)
        if brand is None:
            brand = Brand(
                id=retail_workspace.brand_id,
                company_id=company_id,
                central_branch_id=branch.id,
                slug=retail_workspace.brand_slug,
                name=retail_workspace.brand_name,
                business_type="retail_pos",
                storefront_mode="food_stall",
                theme_config={"uat": True},
                is_active=True,
            )
            db.add(brand)
            await db.flush()
        link = await db.get(BrandBranch, retail_workspace.workspace_id)
        if link is None:
            link = BrandBranch(
                id=retail_workspace.workspace_id,
                company_id=company_id,
                brand_id=brand.id,
                branch_id=branch.id,
                branch_type="company_owned",
                is_active=True,
            )
            db.add(link)

        unit = await db.scalar(
            select(Unit).where(Unit.company_id == company_id, Unit.code == "UAT-PCS")
        )
        if unit is None:
            unit = Unit(company_id=company_id, code="UAT-PCS", name="ชิ้น", decimal_places=0)
            db.add(unit)
            await db.flush()
        category = await db.scalar(
            select(Category).where(Category.company_id == company_id, Category.code == "UAT-RETAIL")
        )
        if category is None:
            category = Category(company_id=company_id, code="UAT-RETAIL", name="สินค้าทดสอบ Retail")
            db.add(category)
            await db.flush()
        price_list = await db.scalar(
            select(PriceList).where(
                PriceList.company_id == company_id,
                PriceList.name == "ราคาทดสอบ Retail UAT",
            )
        )
        if price_list is None:
            price_list = PriceList(
                company_id=company_id,
                name="ราคาทดสอบ Retail UAT",
                valid_from=date(2026, 1, 1),
                is_default=True,
                is_active=True,
            )
            db.add(price_list)
            await db.flush()
        location = await db.scalar(
            select(StockLocation).where(
                StockLocation.branch_id == branch.id,
                StockLocation.code == "STORE",
            )
        )
        if location is None:
            location = StockLocation(
                company_id=company_id,
                branch_id=branch.id,
                code="STORE",
                name="คลังหน้าร้าน Retail UAT",
                is_active=True,
            )
            db.add(location)
            await db.flush()
        product = await db.scalar(
            select(Product).where(
                Product.company_id == company_id,
                Product.sku == "UAT-RETAIL-001",
            )
        )
        if product is None:
            product = Product(
                company_id=company_id,
                brand_id=brand.id,
                category_id=category.id,
                unit_id=unit.id,
                sku="UAT-RETAIL-001",
                barcode="8850000000001",
                name="สินค้าทดสอบ Retail",
                product_type="simple",
                inventory_role="store_local",
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
        price_item = await db.scalar(
            select(PriceListItem).where(
                PriceListItem.price_list_id == price_list.id,
                PriceListItem.product_id == product.id,
                PriceListItem.variant_id.is_(None),
            )
        )
        if price_item is None:
            db.add(
                PriceListItem(
                    company_id=company_id,
                    price_list_id=price_list.id,
                    product_id=product.id,
                    price=Decimal("107"),
                    min_qty=Decimal("1"),
                )
            )
        balance = await db.scalar(
            select(StockBalance).where(
                StockBalance.location_id == location.id,
                StockBalance.product_id == product.id,
                StockBalance.variant_id.is_(None),
            )
        )
        if balance is None:
            db.add(
                StockBalance(
                    company_id=company_id,
                    branch_id=branch.id,
                    location_id=location.id,
                    product_id=product.id,
                    qty_on_hand=Decimal("20"),
                    qty_reserved=Decimal("0"),
                    cost_per_unit=Decimal("40"),
                )
            )
        branch_settings = await db.scalar(
            select(BranchSettings).where(BranchSettings.branch_id == branch.id)
        )
        if branch_settings is None:
            db.add(
                BranchSettings(
                    company_id=company_id,
                    branch_id=branch.id,
                    pos_default_price_list_id=price_list.id,
                    pos_receipt_header="Foodchainservice Retail UAT",
                    pos_receipt_footer="ข้อมูลทดสอบเท่านั้น",
                )
            )
        else:
            branch_settings.pos_default_price_list_id = price_list.id
        brand.central_branch_id = branch.id
        brand.central_location_id = location.id
        brand.central_ready_location_id = location.id
        link.store_location_id = location.id
        await db.commit()
        return {
            "brand_id": str(brand.id),
            "branch_id": str(branch.id),
            "product_id": str(product.id),
            "location_id": str(location.id),
        }


async def prepare_retail(company_id: uuid.UUID) -> dict[str, object]:
    projection = await project_retail_reference_snapshot(company_id=company_id)
    migration = await migrate_retail_operational_data(company_id=company_id)
    _, parity = await reconcile_retail_operational_data(company_id=company_id)
    reference_parity = await verify_retail_reference_parity(company_id=company_id)
    if any(not row.matches for row in parity):
        raise RuntimeError("Retail operational migration parity failed")
    if any(row[0] != row[1] or row[2] for row in reference_parity.values()):
        raise RuntimeError("Retail reference parity failed")
    return {
        "projection": {
            "scanned": projection.scanned,
            "applied": projection.applied,
            "unchanged": projection.unchanged,
        },
        "migration_run_id": str(migration.run_id),
        "tables": {
            row.table_name: {
                "source_count": row.source_count,
                "target_count": row.target_count,
                "matches": row.matches,
            }
            for row in parity
        },
    }


async def prepare_takeaway(
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    takeaway_workspace,
) -> dict[str, object]:
    projection = await project_takeaway_reference_snapshot()
    parity = await verify_takeaway_reference_parity()
    if any(row[0] != row[1] or row[2] for row in parity.values()):
        raise RuntimeError("Takeaway reference parity failed")
    assert TakeawaySessionLocal is not None
    current = TokenData(
        user_id=user_id,
        company_id=company_id,
        branch_id=takeaway_workspace.branch_id,
        brand_id=takeaway_workspace.brand_id,
        business_type="takeaway",
        target_database="takeaway",
        permissions=["*"],
        scope_types=["company"],
    )
    menu = (
        ("food", "อาหาร", "UAT-TW-FOOD-001", "ข้าวกะเพราหมูสับ", "69"),
        ("drink", "เครื่องดื่ม", "UAT-TW-DRINK-001", "ชาไทยเย็น", "45"),
        ("dessert", "ของหวาน", "UAT-TW-DESSERT-001", "เฉาก๊วยนมสด", "45"),
        ("special", "เมนูพิเศษ", "UAT-TW-SPECIAL-001", "เมนูประจำวัน", "99"),
    )
    async with TakeawaySessionLocal() as db:
        location = await db.scalar(
            select(TakeawayStockLocation).where(
                TakeawayStockLocation.company_id == company_id,
                TakeawayStockLocation.code == "TW-STORE",
            )
        )
        if location is None:
            location = TakeawayStockLocation(
                company_id=company_id,
                branch_id=takeaway_workspace.branch_id,
                code="TW-STORE",
                name="คลังหน้าร้าน Takeaway UAT",
                location_type="store",
            )
            db.add(location)
            await db.flush()
        service = TakeawayService(db, current)
        item_ids: list[str] = []
        for category_code, category_name, sku, item_name, price in menu:
            category = await db.scalar(
                select(TakeawayCategory).where(
                    TakeawayCategory.company_id == company_id,
                    TakeawayCategory.brand_id == takeaway_workspace.brand_id,
                    TakeawayCategory.code == category_code,
                )
            )
            if category is None:
                category = TakeawayCategory(
                    company_id=company_id,
                    brand_id=takeaway_workspace.brand_id,
                    code=category_code,
                    name=category_name,
                    is_active=True,
                )
                db.add(category)
                await db.flush()
            item = await db.scalar(
                select(TakeawayCatalogItem).where(
                    TakeawayCatalogItem.company_id == company_id,
                    TakeawayCatalogItem.brand_id == takeaway_workspace.brand_id,
                    TakeawayCatalogItem.sku == sku,
                )
            )
            if item is None:
                item = TakeawayCatalogItem(
                    company_id=company_id,
                    brand_id=takeaway_workspace.brand_id,
                    category_id=category.id,
                    sku=sku,
                    name=item_name,
                    unit="จาน",
                    price=Decimal(price),
                    tax_rate=Decimal("7"),
                    kitchen_station="main",
                    track_stock=True,
                    is_active=True,
                    source_metadata={"source": "wp10-uat-seed"},
                )
                db.add(item)
                await db.flush()
            movement_key = f"wp10-opening-{sku.lower()}"
            existing_movement = await db.scalar(
                select(TakeawayStockMovement).where(
                    TakeawayStockMovement.idempotency_key == movement_key
                )
            )
            if existing_movement is None:
                await service.create_stock_movement(
                    TakeawayStockMovementCreate(
                        location_id=location.id,
                        item_id=item.id,
                        quantity_delta=Decimal("50"),
                        unit_cost=Decimal("20"),
                        movement_type="receive",
                        brand_id=takeaway_workspace.brand_id,
                        branch_id=takeaway_workspace.branch_id,
                        idempotency_key=movement_key,
                    )
                )
            item_ids.append(str(item.id))
        await db.commit()
    return {
        "projection": {
            "scanned": projection.scanned,
            "applied": projection.applied,
            "unchanged": projection.unchanged,
        },
        "brand_id": str(takeaway_workspace.brand_id),
        "branch_id": str(takeaway_workspace.branch_id),
        "menu_item_ids": item_ids,
    }


async def run(args: argparse.Namespace) -> int:
    require_uat(args)
    user, company = await enable_uat_plan(args.company_id, args.username)
    takeaway_workspace, retail_workspace = await provision_workspaces(company.id, user.id)
    platform_projection = await project_platform_references()
    takeaway = await prepare_takeaway(company.id, user.id, takeaway_workspace)
    retail_source = await ensure_legacy_retail_source(
        platform_company=company,
        retail_workspace=retail_workspace,
    )
    retail = await prepare_retail(company.id)
    print(
        json.dumps(
            {
                "status": "ready_for_controlled_uat",
                "company_id": str(company.id),
                "plan_code": UAT_PLAN_CODE,
                "platform_projection": platform_projection,
                "takeaway": takeaway,
                "retail_source": retail_source,
                "retail": retail,
                "physical_uat": "deferred_by_owner",
                "production_activated": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
