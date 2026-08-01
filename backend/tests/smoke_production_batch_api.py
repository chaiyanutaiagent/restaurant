from __future__ import annotations

import asyncio
from datetime import date
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
from app.models.hr import Employee
from app.models.product import Product
from app.models.restaurant import (
    Brand,
    BrandBranch,
    ProductionBatch,
    ProductionBatchLine,
    Recipe,
    RecipeIngredient,
)
from app.models.role import Permission, Role
from app.models.staff_assignment import StaffRoleAssignment
from app.models.stock import StockBalance, StockLocation, StockMovement
from app.models.user import User
from app.utils.create_superuser import DEFAULT_COMPANY_ID, ensure_default_company_seed_in_session
from app.utils.seed_test_beverage import seed_test_beverage
from app.utils.seed_permissions import seed_default_permissions
from app.utils.security import hash_password


PASSWORD = "ProductionSmoke123!"


def expect(response, expected: int):
    if response.status_code != expected:
        raise RuntimeError(
            f"Expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    return response.json().get("data")


async def prepare() -> dict[str, str]:
    marker = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        await seed_default_permissions(db)
        await ensure_default_company_seed_in_session(db)
        await seed_test_beverage(db, str(DEFAULT_COMPANY_ID))

        branch = await db.scalar(
            select(Branch).where(
                Branch.company_id == DEFAULT_COMPANY_ID,
                Branch.code == "BKK-01",
            )
        )
        brand = await db.scalar(
            select(Brand).where(
                Brand.company_id == DEFAULT_COMPANY_ID,
                Brand.slug == "test-beverage",
            )
        )
        if branch is None or brand is None or brand.central_location_id is None:
            raise RuntimeError("Default Restaurant central configuration is missing")

        production_branch = Branch(
            company_id=DEFAULT_COMPANY_ID,
            code=f"PB-{marker}"[:20],
            name="Production Batch Branch",
            is_active=True,
        )
        db.add(production_branch)
        await db.flush()
        db.add(
            BrandBranch(
                company_id=DEFAULT_COMPANY_ID,
                brand_id=brand.id,
                branch_id=production_branch.id,
                branch_type="company_owned",
                is_active=True,
            )
        )
        raw_location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=production_branch.id,
            code=f"PB-RAW-{marker}",
            name="Production Batch Raw",
            is_active=True,
        )
        ready_location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=production_branch.id,
            code=f"PB-RDY-{marker}",
            name="Production Batch Ready",
            is_active=True,
        )
        db.add_all([raw_location, ready_location])
        await db.flush()
        brand.central_branch_id = production_branch.id
        brand.central_location_id = raw_location.id
        brand.central_ready_location_id = ready_location.id

        raw_product = Product(
            company_id=DEFAULT_COMPANY_ID,
            brand_id=brand.id,
            sku=f"PB-RAW-{marker}",
            name="Production Batch Raw",
            product_type="raw_material",
            inventory_role="central_raw",
            cost_price=Decimal("2"),
            selling_price=Decimal("0"),
            is_active=True,
            is_for_sale=False,
            is_for_purchase=True,
        )
        output_product = Product(
            company_id=DEFAULT_COMPANY_ID,
            brand_id=brand.id,
            sku=f"PB-READY-{marker}",
            name="Production Batch Output",
            product_type="raw_material",
            inventory_role="central_ready",
            cost_price=Decimal("0"),
            selling_price=Decimal("0"),
            is_active=True,
            is_for_sale=False,
            is_for_purchase=False,
        )
        db.add_all([raw_product, output_product])
        await db.flush()
        recipe = Recipe(
            company_id=DEFAULT_COMPANY_ID,
            brand_id=brand.id,
            branch_id=None,
            product_id=output_product.id,
            recipe_type="production_recipe",
            version_no=1,
            name="Production Batch Recipe",
            yield_qty=Decimal("2"),
            yield_unit="tray",
            loss_percent=Decimal("0"),
            is_active=True,
        )
        db.add(recipe)
        await db.flush()
        db.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=raw_product.id,
                quantity=Decimal("3"),
                unit="kg",
                sort_order=0,
            )
        )
        db.add_all(
            [
                StockBalance(
                    company_id=DEFAULT_COMPANY_ID,
                    branch_id=production_branch.id,
                    location_id=raw_location.id,
                    product_id=raw_product.id,
                    variant_id=None,
                    qty_on_hand=Decimal("10"),
                    qty_reserved=Decimal("0"),
                    cost_per_unit=Decimal("2"),
                ),
                StockBalance(
                    company_id=DEFAULT_COMPANY_ID,
                    branch_id=branch.id,
                    location_id=ready_location.id,
                    product_id=output_product.id,
                    variant_id=None,
                    qty_on_hand=Decimal("1"),
                    qty_reserved=Decimal("0"),
                    cost_per_unit=Decimal("5"),
                ),
            ]
        )

        permission = await db.scalar(
            select(Permission).where(Permission.code == "brand.central.production.manage")
        )
        if permission is None:
            raise RuntimeError("Production permission was not seeded")
        role = Role(
            company_id=DEFAULT_COMPANY_ID,
            name=f"production_smoke_{marker}",
            is_branch_assignable=True,
        )
        role.permissions = [permission]
        db.add(role)
        await db.flush()
        username = f"production-smoke-{marker}"
        user = User(
            company_id=DEFAULT_COMPANY_ID,
            username=username,
            hashed_password=hash_password(PASSWORD),
            is_active=True,
        )
        db.add(user)
        await db.flush()
        db.add_all(
            [
                Employee(
                    company_id=DEFAULT_COMPANY_ID,
                    branch_id=production_branch.id,
                    user_id=user.id,
                    employee_code=f"PB-{marker}"[:20],
                    first_name="Production",
                    last_name="Smoke",
                    hire_date=date.today(),
                    is_active=True,
                ),
                StaffRoleAssignment(
                    company_id=DEFAULT_COMPANY_ID,
                    user_id=user.id,
                    role_id=role.id,
                    scope_type="branch",
                    scope_key=str(production_branch.id),
                    brand_id=brand.id,
                    branch_id=production_branch.id,
                    station_key=None,
                    assignment_reason="Phase 4 production smoke",
                    assigned_by=user.id,
                ),
            ]
        )
        await db.commit()
        context = {
            "username": username,
            "branch_id": str(production_branch.id),
            "brand_id": str(brand.id),
            "raw_location_id": str(brand.central_location_id),
            "ready_location_id": str(ready_location.id),
            "raw_product_id": str(raw_product.id),
            "output_product_id": str(output_product.id),
        }
    await engine.dispose()
    return context


def login(client: TestClient, username: str, branch_id: str) -> dict[str, str]:
    data = expect(
        client.post(
            "/api/v1/auth/login",
            json={
                "company_id": str(DEFAULT_COMPANY_ID),
                "username": username,
                "password": PASSWORD,
                "branch_id": branch_id,
            },
        ),
        200,
    )
    return {"Authorization": f"Bearer {data['access_token']}"}


async def verify_database(context: dict[str, str], batch_id: str, cancelled_id: str) -> None:
    verify_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(verify_engine, expire_on_commit=False)
    async with session_factory() as db:
        batch = await db.get(ProductionBatch, uuid.UUID(batch_id))
        cancelled = await db.get(ProductionBatch, uuid.UUID(cancelled_id))
        if batch is None or batch.status != "completed":
            raise RuntimeError("Production batch was not completed")
        if cancelled is None or cancelled.status != "cancelled":
            raise RuntimeError("Production batch was not cancelled")

        lines = list(
            (
                await db.scalars(
                    select(ProductionBatchLine).where(
                        ProductionBatchLine.batch_id == batch.id
                    )
                )
            ).all()
        )
        input_line = next(line for line in lines if line.line_type == "input")
        output_line = next(line for line in lines if line.line_type == "output")
        if input_line.planned_qty != Decimal("6") or input_line.actual_qty != Decimal("6"):
            raise RuntimeError(f"Unexpected input quantities: {input_line.planned_qty}")
        if output_line.actual_qty != Decimal("4") or output_line.cost_per_unit != Decimal("3"):
            raise RuntimeError(f"Unexpected output quantities/cost: {output_line.cost_per_unit}")

        raw_balance = await db.scalar(
            select(StockBalance).where(
                StockBalance.location_id == uuid.UUID(context["raw_location_id"]),
                StockBalance.product_id == uuid.UUID(context["raw_product_id"]),
                StockBalance.variant_id.is_(None),
            )
        )
        ready_balance = await db.scalar(
            select(StockBalance).where(
                StockBalance.location_id == uuid.UUID(context["ready_location_id"]),
                StockBalance.product_id == uuid.UUID(context["output_product_id"]),
                StockBalance.variant_id.is_(None),
            )
        )
        if raw_balance is None or raw_balance.qty_on_hand != Decimal("4"):
            raise RuntimeError(f"RAW was not issued correctly: {raw_balance}")
        if ready_balance is None or ready_balance.qty_on_hand != Decimal("5"):
            raise RuntimeError(f"READY was not received correctly: {ready_balance}")

        movements = list(
            (
                await db.scalars(
                    select(StockMovement).where(
                        StockMovement.reference_type == "central_production_batch",
                        StockMovement.reference_id == batch_id,
                    )
                )
            ).all()
        )
        if len(movements) != 2 or {movement.movement_type for movement in movements} != {
            "issue",
            "receive",
        }:
            raise RuntimeError(f"Unexpected production movements: {movements}")
        audit_count = await db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.resource == "ProductionBatch",
                AuditLog.resource_id.in_([batch_id, cancelled_id]),
            )
        )
        if not audit_count or audit_count < 5:
            raise RuntimeError("Production batch audit trail is incomplete")
    await verify_engine.dispose()


def run() -> None:
    if not settings.default_admin_password:
        raise RuntimeError("DEFAULT_ADMIN_PASSWORD is required for production batch smoke")
    context = asyncio.run(prepare())
    with TestClient(app) as client:
        headers = login(client, context["username"], context["branch_id"])
        expect(
            client.get(
                "/api/v1/restaurant/central/test-beverage/production-batches",
                headers=headers,
            ),
            403,
        )
        admin_data = expect(
            client.post(
                "/api/v1/auth/login",
                json={
                    "company_id": str(DEFAULT_COMPANY_ID),
                    "username": "admin",
                    "password": settings.default_admin_password,
                },
            ),
            200,
        )
        admin_headers = {"Authorization": f"Bearer {admin_data['access_token']}"}
        entitlement = expect(
            client.put(
                f"/api/v1/system/brands/{context['brand_id']}/modules/central-production",
                headers=admin_headers,
                json={"is_enabled": True, "config": {}},
            ),
            200,
        )
        if not entitlement["is_enabled"]:
            raise RuntimeError("Central production entitlement was not enabled")
        batch = expect(
            client.post(
                "/api/v1/restaurant/central/test-beverage/production-batches",
                headers=headers,
                json={
                    "planned_date": "2026-07-22",
                    "outputs": [
                        {
                            "product_id": context["output_product_id"],
                            "planned_qty": 4,
                            "unit_code": "tray",
                        }
                    ],
                    "note": "Production batch smoke",
                },
            ),
            201,
        )
        inputs = [line for line in batch["lines"] if line["line_type"] == "input"]
        if len(inputs) != 1 or Decimal(str(inputs[0]["planned_qty"])) != Decimal("6"):
            raise RuntimeError(f"Recipe inputs were not derived: {inputs}")

        started = expect(
            client.post(
                f"/api/v1/restaurant/central/test-beverage/production-batches/{batch['id']}/start",
                headers=headers,
            ),
            200,
        )
        if started["status"] != "in_progress":
            raise RuntimeError("Production batch did not start")

        input_line = next(line for line in started["lines"] if line["line_type"] == "input")
        output_line = next(line for line in started["lines"] if line["line_type"] == "output")
        expect(
            client.post(
                f"/api/v1/restaurant/central/test-beverage/production-batches/{batch['id']}/complete",
                headers=headers,
                json={
                    "lines": [
                        {"line_id": input_line["id"], "actual_qty": 11},
                        {"line_id": output_line["id"], "actual_qty": 4},
                    ]
                },
            ),
            400,
        )
        completed = expect(
            client.post(
                f"/api/v1/restaurant/central/test-beverage/production-batches/{batch['id']}/complete",
                headers=headers,
                json={"lines": []},
            ),
            200,
        )
        if completed["status"] != "completed":
            raise RuntimeError("Production batch did not complete")
        expect(
            client.post(
                f"/api/v1/restaurant/central/test-beverage/production-batches/{batch['id']}/complete",
                headers=headers,
                json={"lines": []},
            ),
            409,
        )

        cancelled = expect(
            client.post(
                "/api/v1/restaurant/central/test-beverage/production-batches",
                headers=headers,
                json={
                    "planned_date": "2026-07-22",
                    "outputs": [
                        {
                            "product_id": context["output_product_id"],
                            "planned_qty": 2,
                            "unit_code": "tray",
                        }
                    ],
                },
            ),
            201,
        )
        cancelled = expect(
            client.post(
                f"/api/v1/restaurant/central/test-beverage/production-batches/{cancelled['id']}/cancel",
                headers=headers,
                json={"reason": "Smoke cancellation"},
            ),
            200,
        )
        expect(
            client.get(
                "/api/v1/restaurant/central/test-food/production-batches",
                headers=headers,
            ),
            404,
        )
        expect(
            client.post(
                "/api/v1/restaurant/central/test-beverage/production-complete",
                headers=headers,
                json={
                    "location_id": context["raw_location_id"],
                    "inputs": [],
                    "outputs": [
                        {"product_id": context["output_product_id"], "qty": 1}
                    ],
                },
            ),
            409,
        )

    asyncio.run(verify_database(context, batch["id"], cancelled["id"]))
    print(
        "production_batch_api_smoke=ok "
        f"batch={batch['id']} raw={context['raw_location_id']} "
        f"ready={context['ready_location_id']}"
    )


if __name__ == "__main__":
    run()
