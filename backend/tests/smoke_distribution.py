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
from app.models.distribution import CompanyDistributionEvent, CompanyDistributionShipment
from app.models.product import Product, Unit
from app.models.restaurant import Brand, BrandBranch
from app.models.stock import StockBalance, StockLocation, StockMovement
from app.models.user import User
from app.schemas.distribution import (
    DistributionActionRequest,
    DistributionDemandCreateRequest,
    DistributionReceiveRequest,
    DistributionRejectRequest,
    DistributionReturnRequest,
    DistributionShipmentPlanRequest,
)
from app.services.distribution_service import DistributionService, q4


DATABASE_PREFIX = "restaurant_wp6_distribution_"


async def seed_fixture(db):
    marker = uuid.uuid4().hex[:8]
    company = Company(name="WP6 Distribution Company", business_slug=f"wp6-distribution-{marker}", is_active=True)
    foreign = Company(name="WP6 Foreign Company", business_slug=f"wp6-foreign-{marker}", is_active=True)
    db.add_all([company, foreign])
    await db.flush()
    actor = User(company_id=company.id, username=f"wp6-{marker}", hashed_password="not-used", is_active=True, is_superuser=True)
    central = Branch(company_id=company.id, code=f"CK{marker[:5]}", name="WP6 Central", is_warehouse=True, is_active=True)
    stores = {
        module: Branch(company_id=company.id, code=f"{prefix}{marker[:5]}", name=f"{module} Store", is_active=True)
        for module, prefix in (("restaurant_pos", "RS"), ("takeaway_pos", "TK"), ("retail_pos", "RT"))
    }
    unit = Unit(company_id=company.id, code="ea", name="ชิ้น WP6", decimal_places=4, is_active=True)
    db.add_all([actor, central, unit, *stores.values()])
    await db.flush()
    fixture = {"company": company, "foreign": foreign, "actor": actor, "central": central, "unit": unit, "modules": {}}
    for module, business_type in (("restaurant_pos", "restaurant"), ("takeaway_pos", "takeaway"), ("retail_pos", "retail_pos")):
        suffix = module.split("_")[0][:3].upper()
        ready = StockLocation(company_id=company.id, branch_id=central.id, code=f"{suffix}RDY", name=f"{module} READY", is_active=True)
        store_location = StockLocation(company_id=company.id, branch_id=stores[module].id, code=f"{suffix}STR", name=f"{module} Store Stock", is_active=True)
        db.add_all([ready, store_location])
        await db.flush()
        brand = Brand(company_id=company.id, central_branch_id=central.id, central_ready_location_id=ready.id, slug=f"{module}-{marker}", name=f"{module} Brand", business_type=business_type, is_active=True)
        db.add(brand)
        await db.flush()
        db.add(BrandBranch(company_id=company.id, brand_id=brand.id, branch_id=stores[module].id, store_location_id=store_location.id, is_active=True))
        product = Product(company_id=company.id, brand_id=brand.id, unit_id=unit.id, sku=f"{suffix}-{marker}", name=f"{module} Finished Good", product_type="manufactured", inventory_role="central_ready", is_active=True, is_for_sale=True, is_for_purchase=False)
        db.add(product)
        await db.flush()
        db.add(StockBalance(company_id=company.id, branch_id=central.id, location_id=ready.id, product_id=product.id, qty_on_hand=Decimal("10"), qty_reserved=Decimal("0"), cost_per_unit=Decimal("20")))
        fixture["modules"][module] = {"brand": brand, "branch": stores[module], "ready": ready, "store": store_location, "product": product}
    await db.commit()
    return fixture


async def demand_and_plan(service, fixture, module: str, suffix: str, qty: Decimal = Decimal("5")):
    row = fixture["modules"][module]
    demand = await service.create_demand(
        fixture["company"].id,
        fixture["actor"].id,
        DistributionDemandCreateRequest(
            source_module=module,
            brand_id=row["brand"].id,
            branch_id=row["branch"].id,
            product_id=row["product"].id,
            needed_on=date(2026, 9, 15),
            requested_qty=qty,
            unit_code="ea",
            source_type=f"{module}_replenishment",
            source_id=f"REQ-{suffix}",
            idempotency_key=f"wp6-demand-{suffix}",
        ),
    )
    shipment = await service.plan_shipment(
        fixture["company"].id,
        fixture["actor"].id,
        DistributionShipmentPlanRequest(demand_id=demand["id"], planned_qty=qty, idempotency_key=f"wp6-plan-{suffix}"),
    )
    return demand, shipment


async def main_async() -> None:
    configured = os.environ.get("WP6_DISTRIBUTION_DATABASE_NAME", "")
    if not configured.startswith(DATABASE_PREFIX):
        raise RuntimeError("WP6 distribution smoke refuses to write a non-isolated database")
    async with AsyncSessionLocal() as db:
        actual = await db.scalar(func.current_database())
        if actual != configured:
            raise RuntimeError(f"WP6 database mismatch: {actual} != {configured}")
        fixture = await seed_fixture(db)
        service = DistributionService(db)
        company_id, actor_id = fixture["company"].id, fixture["actor"].id

        restaurant_demand, restaurant = await demand_and_plan(service, fixture, "restaurant_pos", "restaurant")
        plan_replay = await service.plan_shipment(company_id, actor_id, DistributionShipmentPlanRequest(
            demand_id=restaurant_demand["id"], planned_qty=Decimal("5"), idempotency_key="wp6-plan-restaurant"
        ))
        assert plan_replay["replayed"] is True and plan_replay["id"] == restaurant["id"]
        replay = await service.create_demand(company_id, actor_id, DistributionDemandCreateRequest(
            source_module="restaurant_pos", brand_id=fixture["modules"]["restaurant_pos"]["brand"].id,
            branch_id=fixture["modules"]["restaurant_pos"]["branch"].id, product_id=fixture["modules"]["restaurant_pos"]["product"].id,
            needed_on=date(2026, 9, 15), requested_qty=Decimal("5"), unit_code="ea", source_type="restaurant_pos_replenishment",
            source_id="REQ-restaurant", idempotency_key="wp6-demand-restaurant",
        ))
        assert replay["replayed"] is True
        try:
            await service.create_demand(company_id, actor_id, DistributionDemandCreateRequest(
                source_module="restaurant_pos", brand_id=fixture["modules"]["restaurant_pos"]["brand"].id,
                branch_id=fixture["modules"]["restaurant_pos"]["branch"].id, product_id=fixture["modules"]["restaurant_pos"]["product"].id,
                needed_on=date(2026, 9, 15), requested_qty=Decimal("4"), unit_code="ea", source_type="restaurant_pos_replenishment",
                source_id="REQ-restaurant", idempotency_key="wp6-demand-restaurant",
            ))
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("conflicting demand replay was not blocked")
        dispatch_request = DistributionActionRequest(idempotency_key="wp6-dispatch-restaurant")
        restaurant = await service.dispatch(company_id, actor_id, restaurant["id"], dispatch_request)
        dispatch_replay = await service.dispatch(company_id, actor_id, restaurant["id"], dispatch_request)
        assert dispatch_replay["replayed"] is True
        receive_request = DistributionReceiveRequest(idempotency_key="wp6-receive-restaurant", cumulative_received_qty=Decimal("5"), finalize=True)
        restaurant = await service.receive(company_id, actor_id, restaurant["id"], receive_request)
        receive_replay = await service.receive(company_id, actor_id, restaurant["id"], receive_request)
        assert receive_replay["replayed"] is True
        assert restaurant["status"] == "received"

        _, takeaway = await demand_and_plan(service, fixture, "takeaway_pos", "takeaway")
        takeaway = await service.dispatch(company_id, actor_id, takeaway["id"], DistributionActionRequest(idempotency_key="wp6-dispatch-takeaway"))
        takeaway = await service.reject(company_id, actor_id, takeaway["id"], DistributionRejectRequest(idempotency_key="wp6-reject-takeaway", reason="กล่องเสียหาย"))
        assert takeaway["status"] == "rejected" and q4(takeaway["rejected_qty"]) == Decimal("5.0000")

        _, retail = await demand_and_plan(service, fixture, "retail_pos", "retail")
        retail = await service.dispatch(company_id, actor_id, retail["id"], DistributionActionRequest(idempotency_key="wp6-dispatch-retail"))
        retail = await service.receive(company_id, actor_id, retail["id"], DistributionReceiveRequest(idempotency_key="wp6-receive-retail", cumulative_received_qty=Decimal("5"), finalize=True))
        return_request = DistributionReturnRequest(idempotency_key="wp6-return-retail", qty=Decimal("2"), reason="สินค้าคงเหลือ")
        retail = await service.return_goods(company_id, actor_id, retail["id"], return_request)
        return_replay = await service.return_goods(company_id, actor_id, retail["id"], return_request)
        assert return_replay["replayed"] is True
        assert retail["status"] == "partially_returned" and q4(retail["net_received_qty"]) == Decimal("3.0000")

        wrong = fixture["modules"]["restaurant_pos"]
        try:
            await service.create_demand(company_id, actor_id, DistributionDemandCreateRequest(
                source_module="retail_pos", brand_id=wrong["brand"].id, branch_id=wrong["branch"].id,
                product_id=wrong["product"].id, needed_on=date(2026, 9, 16), requested_qty=Decimal("1"), unit_code="ea",
                source_type="bad", source_id="bad", idempotency_key="wp6-demand-wrong-module",
            ))
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("cross-module demand was not blocked")

        foreign_dashboard = await service.dashboard(fixture["foreign"].id)
        assert foreign_dashboard["demands"] == [] and foreign_dashboard["shipments"] == []
        report = await service.report(company_id, date(2026, 9, 14), date(2026, 9, 16))
        assert {row["source_module"] for row in report["by_workspace"]} == {"restaurant_pos", "takeaway_pos", "retail_pos"}
        assert q4(report["totals"]["net_received_qty"]) == Decimal("8.0000")

        # Reservation locking: only five READY units remain, so the second four-unit plan is rejected.
        _, first_competitor = await demand_and_plan(service, fixture, "restaurant_pos", "compete-a", Decimal("4"))
        assert first_competitor["status"] == "planned"
        row = fixture["modules"]["restaurant_pos"]
        second = await service.create_demand(company_id, actor_id, DistributionDemandCreateRequest(
            source_module="restaurant_pos", brand_id=row["brand"].id, branch_id=row["branch"].id, product_id=row["product"].id,
            needed_on=date(2026, 9, 16), requested_qty=Decimal("4"), unit_code="ea", source_type="competition",
            source_id="REQ-compete-b", idempotency_key="wp6-demand-compete-b",
        ))
        try:
            await service.plan_shipment(company_id, actor_id, DistributionShipmentPlanRequest(
                demand_id=second["id"], planned_qty=Decimal("4"), idempotency_key="wp6-plan-compete-b"
            ))
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError("competing reservation exceeded READY stock")

        events = int(await db.scalar(select(func.count(CompanyDistributionEvent.id)).where(CompanyDistributionEvent.company_id == company_id)) or 0)
        shipments = int(await db.scalar(select(func.count(CompanyDistributionShipment.id)).where(CompanyDistributionShipment.company_id == company_id)) or 0)
        movements = int(await db.scalar(select(func.count(StockMovement.id)).where(StockMovement.company_id == company_id)) or 0)
        assert shipments == 4 and events == 11 and movements == 7, (shipments, events, movements)
    print("WP6 distribution smoke passed: three POS demands, transfer reuse, receive/reject/return, replay, tenant and reservation isolation")


if __name__ == "__main__":
    asyncio.run(main_async())
