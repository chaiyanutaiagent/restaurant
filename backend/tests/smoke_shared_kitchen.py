from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
import os
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.branch import Branch
from app.models.company import Company
from app.models.product import Product, Unit
from app.models.restaurant import Brand, BrandBranch, Recipe, RecipeIngredient
from app.models.shared_kitchen import CompanyIngredientLot, CompanyKitchenMovement
from app.models.stock import StockBalance, StockLocation
from app.models.user import User
from app.schemas.shared_kitchen import (
    CompanyIngredientAliasCreateRequest,
    CompanyIngredientCreateRequest,
    CompanyIngredientReceiptRequest,
    CompanyKitchenConfigureRequest,
    CompanyProductionCompleteRequest,
    CompanyProductionDemandCreateRequest,
    CompanyProductionOrderCreateRequest,
)
from app.services.shared_kitchen_service import SharedKitchenService, q4


DATABASE_PREFIX = "restaurant_wp5_kitchen_"


async def seed_fixture(db):
    marker = uuid.uuid4().hex[:8]
    company = Company(name="WP5 Kitchen Company", business_slug=f"wp5-kitchen-{marker}", is_active=True)
    foreign = Company(name="WP5 Foreign Company", business_slug=f"wp5-foreign-{marker}", is_active=True)
    db.add_all([company, foreign])
    await db.flush()
    actor = User(company_id=company.id, username=f"wp5-{marker}", hashed_password="not-used", is_active=True, is_superuser=True)
    central = Branch(company_id=company.id, code=f"CK-{marker[:5]}", name="WP5 Central Kitchen", is_warehouse=True, is_active=True)
    store_a = Branch(company_id=company.id, code=f"A-{marker[:6]}", name="Brand A Store", is_active=True)
    store_b = Branch(company_id=company.id, code=f"B-{marker[:6]}", name="Brand B Store", is_active=True)
    gram = Unit(company_id=company.id, code="g", name="กรัม WP5", decimal_places=4, is_active=True)
    piece = Unit(company_id=company.id, code="ea", name="ชิ้น WP5", decimal_places=4, is_active=True)
    db.add_all([actor, central, store_a, store_b, gram, piece])
    await db.flush()
    shared_raw = StockLocation(company_id=company.id, branch_id=central.id, code="WP5-RAW", name="Shared RAW", is_active=True)
    ready_a = StockLocation(company_id=company.id, branch_id=central.id, code="WP5-A-RDY", name="Brand A READY", is_active=True)
    ready_b = StockLocation(company_id=company.id, branch_id=central.id, code="WP5-B-RDY", name="Brand B READY", is_active=True)
    store_location_a = StockLocation(company_id=company.id, branch_id=store_a.id, code="WP5-A-ST", name="Brand A Store Stock", is_active=True)
    store_location_b = StockLocation(company_id=company.id, branch_id=store_b.id, code="WP5-B-ST", name="Brand B Store Stock", is_active=True)
    db.add_all([shared_raw, ready_a, ready_b, store_location_a, store_location_b])
    await db.flush()
    brand_a = Brand(company_id=company.id, central_branch_id=central.id, central_location_id=shared_raw.id, central_ready_location_id=ready_a.id, slug=f"pork-a-{marker}", name="หมูแดดเดียว", business_type="restaurant", is_active=True)
    brand_b = Brand(company_id=company.id, central_branch_id=central.id, central_location_id=shared_raw.id, central_ready_location_id=ready_b.id, slug=f"pork-b-{marker}", name="หมูหนักย่าง", business_type="restaurant", is_active=True)
    db.add_all([brand_a, brand_b])
    await db.flush()
    db.add_all([
        BrandBranch(company_id=company.id, brand_id=brand_a.id, branch_id=store_a.id, store_location_id=store_location_a.id, is_active=True),
        BrandBranch(company_id=company.id, brand_id=brand_b.id, branch_id=store_b.id, store_location_id=store_location_b.id, is_active=True),
    ])
    canonical_pork = Product(company_id=company.id, unit_id=gram.id, sku=f"PORK-{marker}", name="หมูกลาง", product_type="raw_material", inventory_role="central_raw", brand_id=None, is_active=True, is_for_sale=False, is_for_purchase=True)
    pork_a = Product(company_id=company.id, unit_id=gram.id, sku=f"PORK-A-{marker}", name="หมูสูตร A", product_type="raw_material", inventory_role="central_raw", brand_id=brand_a.id, is_active=True, is_for_sale=False, is_for_purchase=True)
    pork_b = Product(company_id=company.id, unit_id=gram.id, sku=f"PORK-B-{marker}", name="หมูสูตร B", product_type="raw_material", inventory_role="central_raw", brand_id=brand_b.id, is_active=True, is_for_sale=False, is_for_purchase=True)
    output_a = Product(company_id=company.id, unit_id=piece.id, sku=f"OUT-A-{marker}", name="หมูแดดเดียวพร้อมขาย", product_type="manufactured", inventory_role="central_ready", brand_id=brand_a.id, is_active=True, is_for_sale=True, is_for_purchase=False)
    output_b = Product(company_id=company.id, unit_id=piece.id, sku=f"OUT-B-{marker}", name="หมูหนักย่างพร้อมขาย", product_type="manufactured", inventory_role="central_ready", brand_id=brand_b.id, is_active=True, is_for_sale=True, is_for_purchase=False)
    db.add_all([canonical_pork, pork_a, pork_b, output_a, output_b])
    await db.flush()
    recipe_a = Recipe(company_id=company.id, brand_id=brand_a.id, product_id=output_a.id, recipe_type="production_recipe", version_no=1, name="สูตร A", yield_qty=Decimal("10"), yield_unit=piece.code, is_active=True)
    recipe_b = Recipe(company_id=company.id, brand_id=brand_b.id, product_id=output_b.id, recipe_type="production_recipe", version_no=1, name="สูตร B", yield_qty=Decimal("10"), yield_unit=piece.code, is_active=True)
    db.add_all([recipe_a, recipe_b])
    await db.flush()
    db.add_all([
        RecipeIngredient(recipe_id=recipe_a.id, ingredient_id=pork_a.id, quantity=Decimal("1000"), unit=gram.code),
        RecipeIngredient(recipe_id=recipe_b.id, ingredient_id=pork_b.id, quantity=Decimal("1000"), unit=gram.code),
    ])
    await db.commit()
    return {
        "company": company, "foreign": foreign, "actor": actor, "central": central,
        "store_a": store_a, "store_b": store_b, "shared_raw": shared_raw,
        "brand_a": brand_a, "brand_b": brand_b, "canonical": canonical_pork,
        "pork_a": pork_a, "pork_b": pork_b, "output_a": output_a, "output_b": output_b,
        "gram": gram,
    }


async def complete(service, company_id, actor_id, order_id, completion_key):
    await service.start_order(company_id, actor_id, order_id)
    return await service.complete_order(
        company_id, actor_id, order_id,
        CompanyProductionCompleteRequest(completion_key=completion_key, actual_output_qty=Decimal("10")),
    )


async def main_async() -> None:
    configured = os.environ.get("WP5_KITCHEN_DATABASE_NAME", "")
    if not configured.startswith(DATABASE_PREFIX):
        raise RuntimeError("WP5 kitchen smoke refuses to write a non-isolated database")
    async with AsyncSessionLocal() as db:
        actual_database = await db.scalar(func.current_database())
        if actual_database != configured:
            raise RuntimeError(f"WP5 database mismatch: {actual_database} != {configured}")
        fixture = await seed_fixture(db)
        service = SharedKitchenService(db)
        company_id, actor_id = fixture["company"].id, fixture["actor"].id
        kitchen = await service.configure(company_id, actor_id, CompanyKitchenConfigureRequest(branch_id=fixture["central"].id, raw_location_id=fixture["shared_raw"].id, name="ครัวกลาง WP5"))
        ingredient = await service.create_ingredient(company_id, actor_id, CompanyIngredientCreateRequest(canonical_product_id=fixture["canonical"].id, code="PORK", name="หมู", base_unit_code=fixture["gram"].code, unit_dimension="mass"))
        for brand_key, source_key in [("brand_a", "pork_a"), ("brand_b", "pork_b")]:
            await service.create_alias(company_id, actor_id, CompanyIngredientAliasCreateRequest(ingredient_id=ingredient["id"], brand_id=fixture[brand_key].id, source_product_id=fixture[source_key].id, source_unit_code=fixture["gram"].code, conversion_factor=Decimal("1")))
        receipt = CompanyIngredientReceiptRequest(ingredient_id=ingredient["id"], lot_code="PORK-LOT-01", qty=Decimal("2500"), unit_cost=Decimal("0.10"), idempotency_key="wp5-receipt-0001", reference_id="GR-WP5-01")
        first_receipt = await service.receive(company_id, actor_id, receipt)
        replay_receipt = await service.receive(company_id, actor_id, receipt)
        assert first_receipt["replayed"] is False and replay_receipt["replayed"] is True
        try:
            await service.receive(company_id, actor_id, receipt.model_copy(update={"qty": Decimal("1")}))
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("conflicting receipt replay was not rejected")

        demands = []
        for suffix, brand_key, branch_key, output_key in [("a", "brand_a", "store_a", "output_a"), ("b", "brand_b", "store_b", "output_b")]:
            demands.append(await service.create_demand(company_id, actor_id, CompanyProductionDemandCreateRequest(brand_id=fixture[brand_key].id, branch_id=fixture[branch_key].id, output_product_id=fixture[output_key].id, needed_on=date(2026, 9, 15), requested_qty=Decimal("10"), unit_code="ea", source_type="smoke", source_id=f"demand-{suffix}", idempotency_key=f"wp5-demand-000{suffix}")))
        orders = []
        for suffix, demand_row, brand_key, output_key in [("a", demands[0], "brand_a", "output_a"), ("b", demands[1], "brand_b", "output_b")]:
            orders.append(await service.create_order(company_id, actor_id, CompanyProductionOrderCreateRequest(brand_id=fixture[brand_key].id, output_product_id=fixture[output_key].id, planned_date=date(2026, 9, 15), planned_qty=Decimal("10"), idempotency_key=f"wp5-order-000{suffix}", demand_id=demand_row["id"])))
        completed_a = await complete(service, company_id, actor_id, orders[0]["id"], "wp5-complete-000a")
        completed_b = await complete(service, company_id, actor_id, orders[1]["id"], "wp5-complete-000b")
        assert completed_a["brand_id"] != completed_b["brand_id"]
        replay = await service.complete_order(company_id, actor_id, orders[0]["id"], CompanyProductionCompleteRequest(completion_key="wp5-complete-000a", actual_output_qty=Decimal("10")))
        assert replay["replayed"] is True
        try:
            await service.complete_order(company_id, actor_id, orders[0]["id"], CompanyProductionCompleteRequest(completion_key="wp5-complete-000a", actual_output_qty=Decimal("9")))
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("conflicting completion replay was not rejected")
        lot_total = q4(await db.scalar(select(func.sum(CompanyIngredientLot.qty_on_hand)).where(CompanyIngredientLot.company_id == company_id)))
        assert lot_total == Decimal("500.0000"), lot_total
        output_balances = list((await db.scalars(select(StockBalance).where(StockBalance.company_id == company_id, StockBalance.product_id.in_([fixture["output_a"].id, fixture["output_b"].id])))).all())
        assert {row.product_id: q4(row.qty_on_hand) for row in output_balances} == {fixture["output_a"].id: Decimal("10.0000"), fixture["output_b"].id: Decimal("10.0000")}
        report = await service.report(company_id, date(2026, 9, 14), date(2026, 9, 16))
        assert {row["brand_id"] for row in report["production_by_brand"]} == {fixture["brand_a"].id, fixture["brand_b"].id}
        reversed_a = await service.reverse_order(company_id, actor_id, orders[0]["id"], "wp5-reverse-000a", "smoke rollback")
        assert reversed_a["status"] == "reversed"
        replay_reverse = await service.reverse_order(company_id, actor_id, orders[0]["id"], "wp5-reverse-000a", "smoke rollback")
        assert replay_reverse["replayed"] is True
        lot_total = q4(await db.scalar(select(func.sum(CompanyIngredientLot.qty_on_hand)).where(CompanyIngredientLot.company_id == company_id)))
        assert lot_total == Decimal("1500.0000"), lot_total
        foreign_dashboard = await service.dashboard(fixture["foreign"].id)
        assert foreign_dashboard["ingredients"] == [] and foreign_dashboard["orders"] == []

        # Two Brand A orders compete for 1,500 g. Row locks allow exactly one 1,000 g issue.
        concurrent_orders = []
        for suffix in ["c1", "c2"]:
            concurrent_orders.append(await service.create_order(company_id, actor_id, CompanyProductionOrderCreateRequest(brand_id=fixture["brand_a"].id, output_product_id=fixture["output_a"].id, planned_date=date(2026, 9, 16), planned_qty=Decimal("10"), idempotency_key=f"wp5-order-{suffix}")))
            await service.start_order(company_id, actor_id, concurrent_orders[-1]["id"])

    async def compete(order_id: uuid.UUID, suffix: str):
        async with AsyncSessionLocal() as session:
            try:
                await SharedKitchenService(session).complete_order(company_id, actor_id, order_id, CompanyProductionCompleteRequest(completion_key=f"wp5-complete-{suffix}", actual_output_qty=Decimal("10")))
                return "completed"
            except HTTPException as exc:
                return f"blocked:{exc.status_code}"

    outcomes = await asyncio.gather(compete(concurrent_orders[0]["id"], "c1"), compete(concurrent_orders[1]["id"], "c2"))
    assert sorted(outcomes) == ["blocked:409", "completed"], outcomes
    async with AsyncSessionLocal() as db:
        final_total = q4(await db.scalar(select(func.sum(CompanyIngredientLot.qty_on_hand)).where(CompanyIngredientLot.company_id == company_id)))
        movement_count = int(await db.scalar(select(func.count(CompanyKitchenMovement.id)).where(CompanyKitchenMovement.company_id == company_id)) or 0)
        assert final_total == Decimal("500.0000"), final_total
        assert movement_count == 5, movement_count  # receipt + A/B issues + A reversal + one concurrent issue
    print("WP5 shared kitchen smoke passed: shared raw pool, Brand isolation, replay, reversal, concurrency")


if __name__ == "__main__":
    asyncio.run(main_async())
