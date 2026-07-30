from __future__ import annotations

import asyncio
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.main import app
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.product import Product, Unit
from app.models.restaurant import (
    Brand,
    BrandBranch,
    Recipe,
    RecipeIngredient,
    StockCutoverItem,
    StockCutoverRun,
)
from app.models.role import Permission, Role
from app.models.stock import StockBalance, StockLocation, StockMovement
from app.models.transfer import TransferOrder, TransferOrderItem
from app.models.user import User, UserBranch
from app.utils.create_superuser import DEFAULT_COMPANY_ID, ensure_default_company_seed_in_session
from app.utils.security import hash_password
from app.utils.seed_permissions import seed_default_permissions


PASSWORD = "StockCutoverSmoke123!"


def expect(response, expected: int):
    if response.status_code != expected:
        raise RuntimeError(f"Expected HTTP {expected}, got {response.status_code}: {response.text}")
    return response.json().get("data")


async def prepare() -> dict[str, str]:
    marker = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        await seed_default_permissions(db)
        await ensure_default_company_seed_in_session(db)
        central_branch = Branch(
            company_id=DEFAULT_COMPANY_ID,
            code=f"CUT-C-{marker}",
            name=f"Cutover Central {marker}",
            is_warehouse=True,
            is_active=True,
        )
        store_branch = Branch(
            company_id=DEFAULT_COMPANY_ID,
            code=f"CUT-S-{marker}",
            name=f"Cutover Store {marker}",
            is_active=True,
        )
        db.add_all([central_branch, store_branch])
        await db.flush()
        raw_location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=central_branch.id,
            code=f"CUT-RAW-{marker}",
            name="Cutover CENTRAL-RAW",
            is_active=True,
        )
        ready_location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=central_branch.id,
            code=f"CUT-RDY-{marker}",
            name="Cutover CENTRAL-READY",
            is_active=True,
        )
        store_location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=store_branch.id,
            code=f"CUT-STORE-{marker}",
            name="Cutover STORE-STOCK",
            is_active=True,
        )
        db.add_all([raw_location, ready_location, store_location])
        await db.flush()
        brand = Brand(
            company_id=DEFAULT_COMPANY_ID,
            slug=f"cutover-{marker}",
            name=f"Cutover Brand {marker}",
            central_branch_id=central_branch.id,
            central_location_id=raw_location.id,
            central_ready_location_id=ready_location.id,
            is_active=True,
        )
        db.add(brand)
        await db.flush()
        db.add(
            BrandBranch(
                company_id=DEFAULT_COMPANY_ID,
                brand_id=brand.id,
                branch_id=store_branch.id,
                store_location_id=store_location.id,
                branch_type="company_owned",
                is_active=True,
            )
        )
        unit = await db.scalar(
            select(Unit).where(Unit.company_id == DEFAULT_COMPANY_ID, Unit.code == "kg")
        )
        if unit is None:
            unit = Unit(
                company_id=DEFAULT_COMPANY_ID,
                code="kg",
                name="กิโลกรัม",
                decimal_places=4,
                is_active=True,
            )
            db.add(unit)
            await db.flush()
        raw_product = Product(
            company_id=DEFAULT_COMPANY_ID,
            brand_id=brand.id,
            unit_id=unit.id,
            sku=f"CUT-RAW-P-{marker}",
            name="Cutover Raw Product",
            product_type="raw_material",
            inventory_role="central_raw",
            cost_price=Decimal("2"),
            selling_price=Decimal("0"),
            is_active=True,
            is_for_sale=False,
            is_for_purchase=True,
        )
        ready_product = Product(
            company_id=DEFAULT_COMPANY_ID,
            brand_id=brand.id,
            unit_id=unit.id,
            sku=f"CUT-RDY-P-{marker}",
            name="Cutover Ready Product",
            product_type="raw_material",
            inventory_role="central_ready",
            cost_price=Decimal("4"),
            selling_price=Decimal("0"),
            is_active=True,
            is_for_sale=False,
            is_for_purchase=False,
        )
        menu_product = Product(
            company_id=DEFAULT_COMPANY_ID,
            brand_id=brand.id,
            unit_id=unit.id,
            sku=f"CUT-MENU-{marker}",
            name="Cutover Menu",
            product_type="menu_item",
            inventory_role="not_stocked",
            cost_price=Decimal("0"),
            selling_price=Decimal("100"),
            is_active=True,
            is_for_sale=True,
            is_for_purchase=False,
        )
        db.add_all([raw_product, ready_product, menu_product])
        await db.flush()
        production_recipe = Recipe(
            company_id=DEFAULT_COMPANY_ID,
            brand_id=brand.id,
            product_id=ready_product.id,
            recipe_type="production_recipe",
            name="Cutover Production Recipe",
            yield_qty=Decimal("1"),
            yield_unit="kg",
            loss_percent=Decimal("0"),
            is_active=True,
        )
        menu_recipe = Recipe(
            company_id=DEFAULT_COMPANY_ID,
            brand_id=brand.id,
            product_id=menu_product.id,
            recipe_type="menu_recipe",
            name="Cutover Menu Recipe",
            yield_qty=Decimal("1"),
            yield_unit="จาน",
            loss_percent=Decimal("0"),
            is_active=True,
        )
        db.add_all([production_recipe, menu_recipe])
        await db.flush()
        db.add_all(
            [
                RecipeIngredient(
                    recipe_id=production_recipe.id,
                    ingredient_id=raw_product.id,
                    quantity=Decimal("1"),
                    unit="kg",
                ),
                RecipeIngredient(
                    recipe_id=menu_recipe.id,
                    ingredient_id=ready_product.id,
                    quantity=Decimal("1"),
                    unit="kg",
                ),
                StockBalance(
                    company_id=DEFAULT_COMPANY_ID,
                    branch_id=central_branch.id,
                    location_id=raw_location.id,
                    product_id=raw_product.id,
                    qty_on_hand=Decimal("5"),
                    qty_reserved=Decimal("0"),
                    cost_per_unit=Decimal("2"),
                ),
                StockBalance(
                    company_id=DEFAULT_COMPANY_ID,
                    branch_id=central_branch.id,
                    location_id=raw_location.id,
                    product_id=ready_product.id,
                    qty_on_hand=Decimal("10"),
                    qty_reserved=Decimal("0"),
                    cost_per_unit=Decimal("4"),
                ),
                StockBalance(
                    company_id=DEFAULT_COMPANY_ID,
                    branch_id=central_branch.id,
                    location_id=ready_location.id,
                    product_id=ready_product.id,
                    qty_on_hand=Decimal("2"),
                    qty_reserved=Decimal("0"),
                    cost_per_unit=Decimal("5"),
                ),
            ]
        )
        permission = await db.scalar(
            select(Permission).where(Permission.code == "fb.kitchen.manage")
        )
        store_permission = await db.scalar(
            select(Permission).where(Permission.code == "brand.store.stock.view")
        )
        if permission is None or store_permission is None:
            raise RuntimeError("Stock permissions were not seeded")
        role = Role(
            company_id=DEFAULT_COMPANY_ID,
            name=f"stock_cutover_smoke_{marker}",
            is_branch_assignable=True,
        )
        role.permissions = [permission]
        db.add(role)
        await db.flush()
        user = User(
            company_id=DEFAULT_COMPANY_ID,
            username=f"stock-cutover-{marker}",
            hashed_password=hash_password(PASSWORD),
            is_active=True,
        )
        db.add(user)
        await db.flush()
        db.add(
            UserBranch(
                user_id=user.id,
                branch_id=central_branch.id,
                brand_id=brand.id,
                role_id=role.id,
                is_default=True,
            )
        )
        store_role = Role(
            company_id=DEFAULT_COMPANY_ID,
            name=f"stock_cutover_store_smoke_{marker}",
            is_branch_assignable=True,
        )
        store_role.permissions = [store_permission]
        db.add(store_role)
        await db.flush()
        store_user = User(
            company_id=DEFAULT_COMPANY_ID,
            username=f"stock-cutover-store-{marker}",
            hashed_password=hash_password(PASSWORD),
            is_active=True,
        )
        db.add(store_user)
        await db.flush()
        db.add(
            UserBranch(
                user_id=store_user.id,
                branch_id=store_branch.id,
                brand_id=brand.id,
                role_id=store_role.id,
                is_default=True,
            )
        )
        await db.commit()
        result = {
            "username": user.username,
            "store_username": store_user.username,
            "user_id": str(user.id),
            "brand_slug": brand.slug,
            "brand_id": str(brand.id),
            "central_branch_id": str(central_branch.id),
            "store_branch_id": str(store_branch.id),
            "raw_location_id": str(raw_location.id),
            "ready_location_id": str(ready_location.id),
            "store_location_id": str(store_location.id),
            "raw_product_id": str(raw_product.id),
            "ready_product_id": str(ready_product.id),
            "marker": marker,
        }
    await engine.dispose()
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


async def balances(context: dict[str, str]) -> tuple[Decimal, Decimal, Decimal]:
    verify_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(verify_engine, expire_on_commit=False)
    async with factory() as db:
        rows = list(
            (
                await db.scalars(
                    select(StockBalance).where(
                        StockBalance.product_id == uuid.UUID(context["ready_product_id"]),
                        StockBalance.location_id.in_(
                            [
                                uuid.UUID(context["raw_location_id"]),
                                uuid.UUID(context["ready_location_id"]),
                            ]
                        ),
                    )
                )
            ).all()
        )
        by_location = {str(row.location_id): row for row in rows}
        raw = by_location[context["raw_location_id"]]
        ready = by_location[context["ready_location_id"]]
        result = (Decimal(raw.qty_on_hand), Decimal(ready.qty_on_hand), Decimal(ready.cost_per_unit))
    await verify_engine.dispose()
    return result


async def add_in_transit_transfer(context: dict[str, str]) -> None:
    verify_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(verify_engine, expire_on_commit=False)
    async with factory() as db:
        transfer = TransferOrder(
            company_id=DEFAULT_COMPANY_ID,
            to_number=f"CUT-TO-{context['marker']}",
            status="in_transit",
            from_branch_id=uuid.UUID(context["central_branch_id"]),
            to_branch_id=uuid.UUID(context["store_branch_id"]),
            from_location_id=uuid.UUID(context["ready_location_id"]),
            to_location_id=uuid.UUID(context["store_location_id"]),
            requested_by=uuid.UUID(context["user_id"]),
            approved_by=uuid.UUID(context["user_id"]),
        )
        db.add(transfer)
        await db.flush()
        db.add(
            TransferOrderItem(
                to_id=transfer.id,
                company_id=DEFAULT_COMPANY_ID,
                product_id=uuid.UUID(context["ready_product_id"]),
                product_name="Cutover Ready Product",
                sku=f"CUT-RDY-P-{context['marker']}",
                unit_code="kg",
                qty_requested=Decimal("4"),
                qty_approved=Decimal("4"),
                qty_sent=Decimal("4"),
                qty_received=Decimal("1"),
                unit_cost=Decimal("4"),
            )
        )
        await db.commit()
    await verify_engine.dispose()


async def verify_audit(context: dict[str, str], run_id: str) -> None:
    verify_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(verify_engine, expire_on_commit=False)
    async with factory() as db:
        run = await db.get(StockCutoverRun, uuid.UUID(run_id))
        item_count = await db.scalar(
            select(func.count(StockCutoverItem.id)).where(StockCutoverItem.run_id == uuid.UUID(run_id))
        )
        movements = list(
            (
                await db.scalars(
                    select(StockMovement).where(
                        StockMovement.reference_type == "stock_separation_cutover",
                        StockMovement.reference_id == run_id,
                    )
                )
            ).all()
        )
        audit_count = await db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.resource == "StockCutoverRun",
                AuditLog.resource_id == run_id,
            )
        )
        if run is None or run.status != "completed" or run.item_count != 1:
            raise RuntimeError("Cutover run was not completed correctly")
        if item_count != 1:
            raise RuntimeError("Cutover item audit is missing")
        if len(movements) != 2 or {item.movement_type for item in movements} != {"transfer_out", "transfer_in"}:
            raise RuntimeError(f"Unexpected cutover movements: {movements}")
        if audit_count != 1:
            raise RuntimeError("Cutover AuditLog is missing")
    await verify_engine.dispose()


def run() -> None:
    context = asyncio.run(prepare())
    path = f"/api/v1/restaurant/central/{context['brand_slug']}"
    with TestClient(app) as client:
        store_headers = login(client, context["store_username"])
        expect(client.get(f"{path}/cutover/preview", headers=store_headers), 403)
        expect(client.get(f"{path}/stock-dashboard", headers=store_headers), 403)
        headers = login(client, context["username"])
        before = asyncio.run(balances(context))
        preview = expect(client.get(f"{path}/cutover/preview", headers=headers), 200)
        after_preview = asyncio.run(balances(context))
        if before != after_preview:
            raise RuntimeError("Read-only preview changed stock balances")
        if not preview["is_ready"] or preview["candidate_count"] != 1:
            raise RuntimeError(f"Cutover preview was not ready: {preview['blockers']}")
        if Decimal(str(preview["candidate_total_qty"])) != Decimal("10"):
            raise RuntimeError("Cutover preview quantity is incorrect")

        expect(
            client.post(
                f"{path}/cutover/execute",
                headers=headers,
                json={
                    "preview_token": "0" * 64,
                    "confirmation_text": preview["required_confirmation"],
                },
            ),
            409,
        )
        if asyncio.run(balances(context)) != before:
            raise RuntimeError("Rejected cutover changed stock balances")

        completed = expect(
            client.post(
                f"{path}/cutover/execute",
                headers=headers,
                json={
                    "preview_token": preview["preview_token"],
                    "confirmation_text": preview["required_confirmation"],
                    "note": "Stock cutover smoke",
                },
            ),
            200,
        )
        raw_qty, ready_qty, ready_cost = asyncio.run(balances(context))
        if raw_qty != Decimal("0") or ready_qty != Decimal("12") or ready_cost != Decimal("4.1667"):
            raise RuntimeError(f"Unexpected post-cutover balances: {(raw_qty, ready_qty, ready_cost)}")
        asyncio.run(verify_audit(context, completed["id"]))

        repeated_preview = expect(client.get(f"{path}/cutover/preview", headers=headers), 200)
        if repeated_preview["is_ready"] or not any(
            item["code"] == "cutover_already_completed" for item in repeated_preview["blockers"]
        ):
            raise RuntimeError("Completed cutover was not protected from duplicate execution")
        expect(
            client.post(
                f"{path}/cutover/execute",
                headers=headers,
                json={
                    "preview_token": repeated_preview["preview_token"],
                    "confirmation_text": repeated_preview["required_confirmation"],
                },
            ),
            409,
        )
        runs = expect(client.get(f"{path}/cutover/runs", headers=headers), 200)
        if len(runs) != 1 or runs[0]["id"] != completed["id"] or len(runs[0]["items"]) != 1:
            raise RuntimeError("Cutover history is incomplete")

        asyncio.run(add_in_transit_transfer(context))
        dashboard = expect(client.get(f"{path}/stock-dashboard", headers=headers), 200)
        if (
            Decimal(str(dashboard["central"]["raw"]["total_qty"])) != Decimal("5")
            or Decimal(str(dashboard["central"]["ready"]["total_qty"])) != Decimal("12")
            or Decimal(str(dashboard["in_transit"]["total_qty"])) != Decimal("3")
            or dashboard["in_transit"]["order_count"] != 1
        ):
            raise RuntimeError(f"Stock dashboard totals are incorrect: {dashboard}")

    print(
        "stock_cutover_api_smoke=ok "
        f"run={completed['id']} raw={context['raw_location_id']} ready={context['ready_location_id']}"
    )


if __name__ == "__main__":
    run()
