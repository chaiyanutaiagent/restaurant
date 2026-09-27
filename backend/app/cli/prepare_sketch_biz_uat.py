from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
import json
from typing import Any, Sequence
import uuid
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import AsyncSessionLocal, PlatformSessionLocal, RetailSessionLocal, TakeawaySessionLocal
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.company import Company
from app.models.product import Category, PriceList, PriceListItem, Product, Unit
from app.models.restaurant import Brand, BrandBranch, DiningTable
from app.models.role import Permission, Role
from app.models.settings import BranchSettings
from app.models.tax_settings import BranchTaxProfile, CompanyTaxProfile, TaxRateRule
from app.models.user import User, UserBranch
from app.services.role_preset_service import ROLE_PRESET_POLICIES, missing_role_preset_permissions
from app.cli.prepare_multibusiness_uat import enable_uat_plan
from app.cli.seed_ui_showcase import (
    mirror_platform_references_to_legacy,
    platform_reference_snapshot,
    project_references,
)


SKETCH_BIZ_COMPANY_ID = uuid.UUID("1b8a1818-44d6-4d5f-9d22-e5e17b23c081")
LEGAL_NAME_TH = "บริษัท สเก็ตช์ บีซ จำกัด"
LEGAL_NAME_EN = "SKETCH BIZ CO., LTD."
REGISTRATION_ID = "0125568025206"
REGISTERED_ADDRESS = (
    "63/5 หมู่ที่ 7 ถนนบางกรวย-ไทรน้อย ตำบลไทรน้อย "
    "อำเภอไทรน้อย จังหวัดนนทบุรี 11150"
)
UAT_VAT_RATE = Decimal("7.00")
UAT_VAT_EFFECTIVE_FROM = date(2026, 1, 1)
RESTAURANT_MENU_INVENTORY_ROLE = "not_stocked"


@dataclass(frozen=True)
class WorkspaceSpec:
    key: str
    business_type: str
    brand_slug: str
    brand_name: str
    branch_code: str
    branch_name: str
    source_brand_slug: str | None = None
    source_branch_code: str | None = None
    storefront_mode: str = "food_stall"


WORKSPACES = (
    WorkspaceSpec(
        key="krua-pa-pla-khuen",
        business_type="restaurant",
        brand_slug="krua-pa-pla-khuen",
        brand_name="ครัวป่าปลาเขื่อน",
        branch_code="KPP-01",
        branch_name="ครัวป่าปลาเขื่อน สาขาไทรน้อย",
        source_brand_slug="foodchainservice-restaurant-uat",
        source_branch_code="BKK-01",
        storefront_mode="full_service",
    ),
    WorkspaceSpec(
        key="the-loft-kitchen",
        business_type="restaurant",
        brand_slug="the-loft-kitchen",
        brand_name="The Loft Kitchen",
        branch_code="TLK-01",
        branch_name="The Loft Kitchen สาขาไทรน้อย",
        source_branch_code="BKK-UI-02",
        storefront_mode="full_service",
    ),
    WorkspaceSpec(
        key="the-loft-mini-mart",
        business_type="retail_pos",
        brand_slug="the-loft-mini-mart",
        brand_name="The Loft Mini Mart",
        branch_code="TLM-01",
        branch_name="The Loft Mini Mart สาขาไทรน้อย",
        source_brand_slug="foodchain-retail-uat",
        source_branch_code="RTL-01",
        storefront_mode="retail_store",
    ),
    WorkspaceSpec(
        key="chambo",
        business_type="takeaway",
        brand_slug="chambo",
        brand_name="Chambo",
        branch_code="CHB-01",
        branch_name="Chambo สาขาโอโซนวัน",
        source_brand_slug="foodchain-takeaway-uat",
        source_branch_code="TW-01",
        storefront_mode="food_stall",
    ),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare the idempotent Sketch Biz multi-business UAT tenant.",
    )
    parser.add_argument("--company-id", type=uuid.UUID, required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--yes", action="store_true")
    return parser


def require_uat(args: argparse.Namespace) -> None:
    hostname = urlsplit(settings.saas_public_base_url).hostname or ""
    if not args.yes:
        raise RuntimeError("Pass --yes to prepare persistent Sketch Biz UAT data")
    if args.company_id != SKETCH_BIZ_COMPANY_ID:
        raise RuntimeError("The command is pinned to the approved Sketch Biz UAT Company ID")
    if settings.environment != "development" or not hostname.startswith("uat-"):
        raise RuntimeError("This command is restricted to the HTTPS uat-* development environment")
    if settings.identity_database != "platform_core" or not settings.reference_projector_enabled:
        raise RuntimeError("Sketch Biz UAT preparation requires Platform identity and reference projection")
    if settings.restaurant_service_database != "legacy":
        raise RuntimeError("Sketch Biz UAT preparation currently requires the Legacy Restaurant runtime")
    if settings.retail_service_database != "retail" or RetailSessionLocal is None:
        raise RuntimeError("Sketch Biz UAT preparation requires the dedicated Retail database")
    if not settings.takeaway_feature_enabled or settings.takeaway_service_database != "takeaway":
        raise RuntimeError("Sketch Biz UAT preparation requires the Takeaway dark-launch runtime")
    if TakeawaySessionLocal is None:
        raise RuntimeError("Sketch Biz UAT preparation requires the dedicated Takeaway database")


def validate_registration_id(value: str) -> None:
    if len(value) != 13 or not value.isdigit():
        raise RuntimeError("Thai company registration/tax ID must contain exactly 13 digits")


def workspace_keys() -> tuple[str, ...]:
    return tuple(spec.key for spec in WORKSPACES)


async def _find_brand(db, company_id: uuid.UUID, spec: WorkspaceSpec) -> Brand | None:
    slugs = [spec.brand_slug]
    if spec.source_brand_slug:
        slugs.append(spec.source_brand_slug)
    brand = await db.scalar(
        select(Brand).where(Brand.company_id == company_id, Brand.slug.in_(slugs)).order_by(
            (Brand.slug == spec.brand_slug).desc()
        )
    )
    return brand


async def _find_branch(db, company_id: uuid.UUID, spec: WorkspaceSpec) -> Branch | None:
    codes = [spec.branch_code]
    if spec.source_branch_code:
        codes.append(spec.source_branch_code)
    return await db.scalar(
        select(Branch).where(Branch.company_id == company_id, Branch.code.in_(codes)).order_by(
            (Branch.code == spec.branch_code).desc()
        )
    )


async def _ensure_workspace(
    db,
    company_id: uuid.UUID,
    spec: WorkspaceSpec,
) -> tuple[Brand, Branch, BrandBranch, bool]:
    brand = await _find_brand(db, company_id, spec)
    created = brand is None
    if brand is None:
        brand = Brand(company_id=company_id, slug=spec.brand_slug, name=spec.brand_name)
        db.add(brand)
        await db.flush()
    brand.slug = spec.brand_slug
    brand.name = spec.brand_name
    brand.business_type = spec.business_type
    brand.storefront_mode = spec.storefront_mode
    brand.theme_config = {
        **(brand.theme_config or {}),
        "tenant": "sketch-biz",
        "uat": True,
        "production_transactions_enabled": False if spec.business_type == "takeaway" else None,
    }
    brand.is_active = True

    branch = await _find_branch(db, company_id, spec)
    if branch is None:
        branch = Branch(company_id=company_id, code=spec.branch_code, name=spec.branch_name)
        db.add(branch)
        await db.flush()
        created = True
    branch.code = spec.branch_code
    branch.name = spec.branch_name
    branch.name_en = spec.branch_name if spec.brand_name.startswith("The Loft") else None
    branch.address = REGISTERED_ADDRESS
    branch.is_warehouse = False
    branch.is_active = True
    branch.deleted_at = None

    conflicting_links = (
        await db.scalars(
            select(BrandBranch).where(
                BrandBranch.company_id == company_id,
                BrandBranch.branch_id == branch.id,
                BrandBranch.brand_id != brand.id,
                BrandBranch.is_active.is_(True),
            )
        )
    ).all()
    for conflict in conflicting_links:
        conflict.is_active = False

    link = await db.scalar(
        select(BrandBranch).where(
            BrandBranch.company_id == company_id,
            BrandBranch.brand_id == brand.id,
            BrandBranch.branch_id == branch.id,
        )
    )
    if link is None:
        link = BrandBranch(
            company_id=company_id,
            brand_id=brand.id,
            branch_id=branch.id,
            branch_type="company_owned",
            is_active=True,
        )
        db.add(link)
        await db.flush()
        created = True
    else:
        link.branch_type = "company_owned"
        link.is_active = True

    brand.central_branch_id = branch.id
    return brand, branch, link, created


async def _ensure_roles(db, company_id: uuid.UUID) -> tuple[dict[str, Role], int]:
    permissions = (await db.scalars(select(Permission).order_by(Permission.code))).all()
    permission_by_code = {row.code: row for row in permissions}
    missing = missing_role_preset_permissions(permission_by_code)
    if missing:
        details = "; ".join(f"{key}: {', '.join(codes)}" for key, codes in sorted(missing.items()))
        raise RuntimeError(f"Permission catalog is incomplete: {details}")

    roles: dict[str, Role] = {}
    created = 0
    for policy in ROLE_PRESET_POLICIES:
        role = await db.scalar(
            select(Role)
            .where(Role.company_id == company_id, Role.name == policy.name)
            .options(selectinload(Role.permissions))
        )
        resolved = [permission_by_code[code] for code in policy.permission_codes]
        if role is None:
            role = Role(
                company_id=company_id,
                name=policy.name,
                description=policy.description,
                is_system=True,
                is_branch_assignable=policy.is_branch_assignable,
                allowed_scope_types=list(policy.allowed_scopes),
                permissions=resolved,
            )
            db.add(role)
            await db.flush()
            created += 1
        else:
            role.deleted_at = None
            role.description = policy.description
            role.is_system = True
            role.is_branch_assignable = policy.is_branch_assignable
            role.allowed_scope_types = list(policy.allowed_scopes)
            role.permissions = resolved
        roles[policy.key] = role
    return roles, created


async def _ensure_admin_branch_access(
    db,
    admin: User,
    workspaces: list[tuple[WorkspaceSpec, Brand, Branch, BrandBranch]],
    branch_manager_role: Role,
) -> int:
    created = 0
    all_assignments = (
        await db.scalars(
            select(UserBranch).where(UserBranch.user_id == admin.id, UserBranch.deleted_at.is_(None))
        )
    ).all()
    by_branch = {row.branch_id: row for row in all_assignments}
    for row in all_assignments:
        row.is_default = False

    for index, (spec, brand, branch, _) in enumerate(workspaces):
        assignment = by_branch.get(branch.id)
        if assignment is None:
            assignment = UserBranch(
                user_id=admin.id,
                branch_id=branch.id,
                role_id=branch_manager_role.id,
            )
            db.add(assignment)
            created += 1
        assignment.brand_id = brand.id
        assignment.business_type = spec.business_type
        assignment.target_database = spec.business_type
        assignment.is_default = index == 0
        assignment.deleted_at = None

        moved_assignments = (
            await db.scalars(
                select(UserBranch).where(
                    UserBranch.branch_id == branch.id,
                    UserBranch.deleted_at.is_(None),
                )
            )
        ).all()
        for moved in moved_assignments:
            moved.brand_id = brand.id
            moved.business_type = spec.business_type
            moved.target_database = spec.business_type
    return created


async def _ensure_tax_configuration(
    db,
    company_id: uuid.UUID,
    workspaces: list[tuple[WorkspaceSpec, Brand, Branch, BrandBranch]],
) -> dict[str, Any]:
    profile = await db.scalar(select(CompanyTaxProfile).where(CompanyTaxProfile.company_id == company_id))
    if profile is None:
        profile = CompanyTaxProfile(company_id=company_id)
        db.add(profile)
    profile.legal_name = LEGAL_NAME_TH
    profile.tax_id = REGISTRATION_ID
    profile.vat_registered = True
    profile.vat_registration_date = None
    profile.registered_address = REGISTERED_ADDRESS
    profile.default_price_vat_type = "included"
    profile.default_vat_rate = UAT_VAT_RATE
    profile.vat_filing_mode = "separate"
    profile.consolidated_filing_approved = False

    rules = (
        ("VAT7-UAT", "ภาษีมูลค่าเพิ่ม 7% (UAT)", "standard", UAT_VAT_RATE, "included", True),
        ("VAT0-UAT", "ภาษีมูลค่าเพิ่ม 0% (UAT)", "zero", Decimal("0"), "included", False),
        ("VAT-EXEMPT-UAT", "ยกเว้นภาษีมูลค่าเพิ่ม (UAT)", "exempt", Decimal("0"), "exempt", False),
    )
    for code, name, category, rate, vat_type, is_default in rules:
        row = await db.scalar(
            select(TaxRateRule).where(
                TaxRateRule.company_id == company_id,
                TaxRateRule.code == code,
                TaxRateRule.effective_from == UAT_VAT_EFFECTIVE_FROM,
            )
        )
        if row is None:
            row = TaxRateRule(
                company_id=company_id,
                code=code,
                effective_from=UAT_VAT_EFFECTIVE_FROM,
            )
            db.add(row)
        row.name = name
        row.tax_category = category
        row.rate = rate
        row.price_vat_type = vat_type
        row.effective_to = None
        row.is_default = is_default
        row.is_active = True

    existing_profiles = (
        await db.scalars(select(BranchTaxProfile).where(BranchTaxProfile.company_id == company_id))
    ).all()
    by_branch = {row.branch_id: row for row in existing_profiles}
    used_codes = {row.tax_branch_code for row in existing_profiles}
    for row in existing_profiles:
        row.is_head_office = False

    allocated: list[str] = []
    next_code = 1
    for index, (_, _, branch, _) in enumerate(workspaces):
        row = by_branch.get(branch.id)
        if row is None:
            while f"{next_code:05d}" in used_codes:
                next_code += 1
            code = f"{next_code:05d}"
            used_codes.add(code)
            next_code += 1
            row = BranchTaxProfile(
                company_id=company_id,
                branch_id=branch.id,
                tax_branch_code=code,
                effective_from=UAT_VAT_EFFECTIVE_FROM,
            )
            db.add(row)
        row.is_head_office = index == 0
        row.legal_name = LEGAL_NAME_TH
        row.registered_address = REGISTERED_ADDRESS
        row.vat_registration_date = None
        row.filing_enabled = True
        row.effective_to = None
        allocated.append(row.tax_branch_code)
    return {
        "uat_vat_rate": str(UAT_VAT_RATE),
        "branch_tax_codes": allocated,
        "production_vat_registration_confirmation_required": True,
        "production_branch_registration_confirmation_required": True,
    }


async def configure_legacy_tax(
    company_id: uuid.UUID,
    platform_summary: dict[str, Any],
) -> dict[str, Any]:
    configured: list[tuple[WorkspaceSpec, Brand, Branch, BrandBranch]] = []
    specs_by_key = {spec.key: spec for spec in WORKSPACES}
    async with AsyncSessionLocal() as db:
        for row in platform_summary["workspaces"]:
            spec = specs_by_key[row["key"]]
            brand = await db.get(Brand, uuid.UUID(row["brand_id"]))
            branch = await db.get(Branch, uuid.UUID(row["branch_id"]))
            link = await db.scalar(
                select(BrandBranch).where(
                    BrandBranch.company_id == company_id,
                    BrandBranch.brand_id == uuid.UUID(row["brand_id"]),
                    BrandBranch.branch_id == uuid.UUID(row["branch_id"]),
                )
            )
            if brand is None or branch is None or link is None:
                raise RuntimeError(f"Projected Legacy references are incomplete for {spec.key}")
            configured.append((spec, brand, branch, link))
        tax = await _ensure_tax_configuration(db, company_id, configured)
        await db.commit()
        return tax


async def configure_platform(company_id: uuid.UUID, username: str) -> dict[str, Any]:
    validate_registration_id(REGISTRATION_ID)
    async with PlatformSessionLocal() as db:
        company = await db.get(Company, company_id)
        admin = await db.scalar(
            select(User).where(
                User.company_id == company_id,
                User.username == username,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        if company is None or not company.is_active:
            raise RuntimeError("Active UAT Company was not found")
        if admin is None or not admin.is_superuser:
            raise RuntimeError("Active UAT superuser was not found")

        company.name = LEGAL_NAME_TH
        company.name_en = LEGAL_NAME_EN
        company.business_slug = "sketch-biz"
        company.tax_id = REGISTRATION_ID
        company.vat_registered = True
        company.address = REGISTERED_ADDRESS
        company.address_en = None
        company.phone = None
        company.email = None
        company.website = "https://uat-app.foodchainservice.com"
        company.currency = "THB"
        company.timezone = "Asia/Bangkok"
        company.fiscal_year_start = 1
        company.is_active = True

        configured: list[tuple[WorkspaceSpec, Brand, Branch, BrandBranch]] = []
        created_workspaces = 0
        for spec in WORKSPACES:
            brand, branch, link, created = await _ensure_workspace(db, company_id, spec)
            configured.append((spec, brand, branch, link))
            created_workspaces += int(created)

        roles, created_roles = await _ensure_roles(db, company_id)
        created_access = await _ensure_admin_branch_access(
            db,
            admin,
            configured,
            roles["branch-manager"],
        )
        db.add(
            AuditLog(
                company_id=company_id,
                user_id=admin.id,
                action="uat.sketch_biz.prepare",
                resource="Company",
                resource_id=str(company_id),
                new_value={
                    "legal_name": LEGAL_NAME_TH,
                    "registration_id": REGISTRATION_ID,
                    "workspace_keys": list(workspace_keys()),
                    "tax_configuration": "uat_test_only",
                    "takeaway_transactions": "hold",
                    "production_activated": False,
                },
            )
        )
        await db.commit()
        return {
            "company_id": str(company_id),
            "admin_user_id": str(admin.id),
            "created_workspaces": created_workspaces,
            "created_roles": created_roles,
            "created_admin_branch_access": created_access,
            "workspaces": [
                {
                    **asdict(spec),
                    "brand_id": str(brand.id),
                    "branch_id": str(branch.id),
                    "workspace_id": str(link.id),
                }
                for spec, brand, branch, link in configured
            ],
        }


async def seed_restaurant_examples(
    company_id: uuid.UUID,
    platform_summary: dict[str, Any],
) -> dict[str, int]:
    restaurant_rows = [row for row in platform_summary["workspaces"] if row["business_type"] == "restaurant"]
    summary = {"brands": 0, "tables": 0, "categories": 0, "products": 0, "price_lists": 0}
    async with AsyncSessionLocal() as db:
        unit = await db.scalar(select(Unit).where(Unit.company_id == company_id, Unit.code == "MENU-PORTION"))
        if unit is None:
            unit = Unit(company_id=company_id, code="MENU-PORTION", name="ที่", decimal_places=0)
            db.add(unit)
            await db.flush()

        menu = (
            ("FOOD", "อาหาร", "เมนูแนะนำ", Decimal("89")),
            ("DRINK", "เครื่องดื่ม", "เครื่องดื่มประจำร้าน", Decimal("45")),
            ("DESSERT", "ของหวาน", "ของหวานประจำร้าน", Decimal("55")),
            ("SPECIAL", "เมนูพิเศษ", "เมนูพิเศษประจำวัน", Decimal("129")),
        )
        zones = ("โซนหน้าร้าน", "โซนในร้าน", "โซนครอบครัว", "โซนสวน")
        for row in restaurant_rows:
            brand_id = uuid.UUID(row["brand_id"])
            branch_id = uuid.UUID(row["branch_id"])
            key = row["key"].upper().replace("-", "_")
            price_list = await db.scalar(
                select(PriceList).where(PriceList.company_id == company_id, PriceList.name == f"{row['brand_name']} UAT Menu")
            )
            if price_list is None:
                price_list = PriceList(
                    company_id=company_id,
                    name=f"{row['brand_name']} UAT Menu",
                    valid_from=UAT_VAT_EFFECTIVE_FROM,
                    is_default=False,
                    is_active=True,
                )
                db.add(price_list)
                await db.flush()
            summary["price_lists"] += 1

            branch_settings = await db.scalar(select(BranchSettings).where(BranchSettings.branch_id == branch_id))
            if branch_settings is None:
                branch_settings = BranchSettings(company_id=company_id, branch_id=branch_id)
                db.add(branch_settings)
            branch_settings.pos_default_price_list_id = price_list.id
            branch_settings.pos_receipt_header = row["brand_name"]
            branch_settings.pos_receipt_footer = "ข้อมูลสำหรับทดสอบ UAT เท่านั้น"

            for category_suffix, category_name, product_name, price in menu:
                category_code = f"{key[:12]}-{category_suffix}"
                category = await db.scalar(
                    select(Category).where(Category.company_id == company_id, Category.code == category_code)
                )
                if category is None:
                    category = Category(company_id=company_id, code=category_code, name=category_name)
                    db.add(category)
                    await db.flush()
                summary["categories"] += 1
                sku = f"{key[:12]}-{category_suffix}-001"
                product = await db.scalar(select(Product).where(Product.company_id == company_id, Product.sku == sku))
                if product is None:
                    product = Product(
                        company_id=company_id,
                        brand_id=brand_id,
                        category_id=category.id,
                        unit_id=unit.id,
                        sku=sku,
                        name=f"{product_name} · {row['brand_name']}",
                        product_type="menu_item",
                        inventory_role=RESTAURANT_MENU_INVENTORY_ROLE,
                        cost_price=(price * Decimal("0.40")).quantize(Decimal("0.01")),
                        selling_price=price,
                        vat_type="included",
                        vat_rate=UAT_VAT_RATE,
                        is_active=True,
                        is_for_sale=True,
                        is_for_purchase=False,
                    )
                    db.add(product)
                    await db.flush()
                else:
                    product.brand_id = brand_id
                    product.category_id = category.id
                    product.name = f"{product_name} · {row['brand_name']}"
                    product.inventory_role = RESTAURANT_MENU_INVENTORY_ROLE
                    product.selling_price = price
                    product.vat_type = "included"
                    product.vat_rate = UAT_VAT_RATE
                    product.is_active = True
                    product.is_for_sale = True
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
                            price=price,
                            min_qty=Decimal("1"),
                        )
                    )
                else:
                    price_item.price = price
                summary["products"] += 1

            for zone_index, zone in enumerate(zones, start=1):
                for table_index in range(1, 5):
                    table_name = f"{zone_index}-{table_index:02d}"
                    table = await db.scalar(
                        select(DiningTable).where(
                            DiningTable.company_id == company_id,
                            DiningTable.branch_id == branch_id,
                            DiningTable.name == table_name,
                        )
                    )
                    if table is None:
                        table = DiningTable(
                            company_id=company_id,
                            branch_id=branch_id,
                            name=table_name,
                            zone=zone,
                        )
                        db.add(table)
                    table.capacity = 4 if zone_index != 3 else 6
                    table.table_type = "dine_in"
                    table.status = "available"
                    table.sort_order = zone_index * 100 + table_index
                    table.is_active = True
                    summary["tables"] += 1
            summary["brands"] += 1
        await db.commit()
    return summary


async def run(args: argparse.Namespace) -> dict[str, Any]:
    require_uat(args)
    await enable_uat_plan(args.company_id, args.username)
    platform = await configure_platform(args.company_id, args.username)
    projections = await project_references(args.company_id)
    references = await platform_reference_snapshot(args.company_id)
    async with PlatformSessionLocal() as db:
        company = await db.get(Company, args.company_id)
        if company is None:
            raise RuntimeError("Sketch Biz UAT Company disappeared during projection")
        await mirror_platform_references_to_legacy(company, references)
    tax = await configure_legacy_tax(args.company_id, platform)
    restaurant_examples = await seed_restaurant_examples(args.company_id, platform)
    return {
        "status": "ready_for_controlled_uat",
        "dataset": "sketch_biz_uat",
        "environment": settings.environment,
        "company": platform,
        "tax": tax,
        "projections": projections,
        "restaurant_examples": restaurant_examples,
        "android_business_code": "sketch-biz",
        "takeaway_brand": "chambo",
        "takeaway_source_import": "not_started",
        "takeaway_transactions": "hold",
        "physical_uat": "deferred_by_owner",
        "production_activated": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = asyncio.run(run(args))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
