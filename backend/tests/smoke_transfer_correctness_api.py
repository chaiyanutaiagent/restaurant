from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.main import app
from app.models.branch import Branch
from app.models.product import Product
from app.models.restaurant import Brand, BrandBranch, CentralOrder, CentralOrderItem, WapShiftClosure
from app.models.role import Permission, Role
from app.models.stock import StockBalance, StockLocation, StockMovement
from app.models.transfer import TransferOrder
from app.models.user import User, UserBranch
from app.schemas.transfer import ShipTORequest
from app.services.transfer_service import TransferService
from app.services.stock_service import StockService
from app.utils.create_superuser import DEFAULT_COMPANY_ID, ensure_default_company_seed_in_session
from app.utils.seed_permissions import seed_default_permissions
from app.utils.seed_test_beverage import seed_test_beverage
from app.utils.security import hash_password


PASSWORD = "TransferSmoke123!"


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
        central_branch = await db.scalar(
            select(Branch).where(
                Branch.company_id == DEFAULT_COMPANY_ID,
                Branch.code == "BKK-01",
            )
        )
        if central_branch is None:
            raise RuntimeError("Default central branch is missing")
        store_branch = Branch(
            company_id=DEFAULT_COMPANY_ID,
            code=f"TS-{marker}",
            name=f"Transfer Smoke Store {marker}",
            is_active=True,
        )
        db.add(store_branch)
        await db.flush()
        ready_location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=central_branch.id,
            code=f"TS-R-{marker}",
            name=f"Transfer Smoke READY {marker}",
            is_active=True,
        )
        store_location = StockLocation(
            company_id=DEFAULT_COMPANY_ID,
            branch_id=store_branch.id,
            code=f"TS-S-{marker}",
            name=f"Transfer Smoke STORE {marker}",
            is_active=True,
        )
        product = Product(
            company_id=DEFAULT_COMPANY_ID,
            sku=f"TS-P-{marker}",
            name=f"Transfer Smoke Product {marker}",
            product_type="raw_material",
            inventory_role="central_ready",
            cost_price=Decimal("7.5"),
            selling_price=Decimal("0"),
            is_active=True,
            is_for_sale=False,
            is_for_purchase=False,
        )
        db.add_all([ready_location, store_location, product])
        await db.flush()
        db.add(
            StockBalance(
                company_id=DEFAULT_COMPANY_ID,
                branch_id=central_branch.id,
                location_id=ready_location.id,
                product_id=product.id,
                variant_id=None,
                qty_on_hand=Decimal("30"),
                qty_reserved=Decimal("0"),
                cost_per_unit=Decimal("7.5"),
            )
        )

        permissions = list(
            (
                await db.scalars(
                    select(Permission).where(
                        Permission.code.in_(
                            [
                                "inventory.transfer.view",
                                "inventory.transfer.create",
                                "inventory.transfer.approve",
                            ]
                        )
                    )
                )
            ).all()
        )
        if len(permissions) != 3:
            raise RuntimeError("Transfer permissions were not seeded")
        role = Role(
            company_id=DEFAULT_COMPANY_ID,
            name=f"transfer_smoke_{marker}",
            is_branch_assignable=True,
        )
        role.permissions = permissions
        db.add(role)
        await db.flush()
        username = f"transfer-smoke-{marker}"
        user = User(
            company_id=DEFAULT_COMPANY_ID,
            username=username,
            hashed_password=hash_password(PASSWORD),
            is_active=True,
        )
        db.add(user)
        await db.flush()
        db.add(
            UserBranch(
                user_id=user.id,
                branch_id=central_branch.id,
                role_id=role.id,
                is_default=True,
            )
        )
        await db.commit()
        context = {
            "username": username,
            "user_id": str(user.id),
            "central_branch_id": str(central_branch.id),
            "store_branch_id": str(store_branch.id),
            "ready_location_id": str(ready_location.id),
            "store_location_id": str(store_location.id),
            "product_id": str(product.id),
        }
    await engine.dispose()
    return context


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


def create_approved_transfer(
    client: TestClient,
    headers: dict[str, str],
    context: dict[str, str],
    qty: int,
) -> dict:
    transfer = expect(
        client.post(
            "/api/v1/transfer/orders",
            headers=headers,
            json={
                "from_branch_id": context["central_branch_id"],
                "to_branch_id": context["store_branch_id"],
                "from_location_id": context["ready_location_id"],
                "to_location_id": context["store_location_id"],
                "items": [
                    {
                        "product_id": context["product_id"],
                        "qty_requested": qty,
                    }
                ],
            },
        ),
        201,
    )
    transfer = expect(
        client.post(
            f"/api/v1/transfer/orders/{transfer['id']}/submit",
            headers=headers,
        ),
        200,
    )
    return expect(
        client.post(
            f"/api/v1/transfer/orders/{transfer['id']}/approve",
            headers=headers,
            json={
                "items": [
                    {
                        "item_id": transfer["items"][0]["id"],
                        "qty_approved": qty,
                    }
                ]
            },
        ),
        200,
    )


async def verify_after_ship(context: dict[str, str], transfer_id: str) -> None:
    verify_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(verify_engine, expire_on_commit=False)
    async with factory() as db:
        source = await db.scalar(
            select(StockBalance).where(
                StockBalance.location_id == uuid.UUID(context["ready_location_id"]),
                StockBalance.product_id == uuid.UUID(context["product_id"]),
            )
        )
        destination = await db.scalar(
            select(StockBalance).where(
                StockBalance.location_id == uuid.UUID(context["store_location_id"]),
                StockBalance.product_id == uuid.UUID(context["product_id"]),
            )
        )
        if source is None or source.qty_on_hand != Decimal("25") or source.qty_reserved != Decimal("0"):
            raise RuntimeError(f"READY was not shipped correctly: {source}")
        if destination is not None and destination.qty_on_hand != Decimal("0"):
            raise RuntimeError("STORE stock increased before Receive")
        movements = list(
            (
                await db.scalars(
                    select(StockMovement).where(
                        StockMovement.reference_type == "transfer_order",
                        StockMovement.reference_id == transfer_id,
                    )
                )
            ).all()
        )
        if len(movements) != 1 or movements[0].movement_type != "transfer_out":
            raise RuntimeError(f"Unexpected Ship movements: {movements}")
    await verify_engine.dispose()


async def verify_completed(context: dict[str, str], transfer_id: str) -> None:
    verify_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(verify_engine, expire_on_commit=False)
    async with factory() as db:
        destination = await db.scalar(
            select(StockBalance).where(
                StockBalance.location_id == uuid.UUID(context["store_location_id"]),
                StockBalance.product_id == uuid.UUID(context["product_id"]),
            )
        )
        if destination is None or destination.qty_on_hand != Decimal("4"):
            raise RuntimeError(f"STORE received incorrect stock: {destination}")
        movements = list(
            (
                await db.scalars(
                    select(StockMovement).where(
                        StockMovement.reference_type == "transfer_order",
                        StockMovement.reference_id == transfer_id,
                    )
                )
            ).all()
        )
        if [movement.movement_type for movement in movements].count("transfer_out") != 1:
            raise RuntimeError("Ship was recorded more than once")
        incoming = [movement.qty for movement in movements if movement.movement_type == "transfer_in"]
        if sorted(incoming) != [Decimal("1"), Decimal("3")]:
            raise RuntimeError(f"Unexpected Receive movements: {incoming}")
    await verify_engine.dispose()


async def concurrent_ship(context: dict[str, str], transfer_id: str) -> None:
    concurrent_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(concurrent_engine, expire_on_commit=False)

    async def ship_once() -> int:
        async with factory() as db:
            try:
                await TransferService(db).ship_to(
                    uuid.UUID(transfer_id),
                    DEFAULT_COMPANY_ID,
                    uuid.UUID(context["user_id"]),
                    ShipTORequest(note="concurrency smoke"),
                )
                return 200
            except HTTPException as exc:
                return exc.status_code

    statuses = await asyncio.gather(ship_once(), ship_once())
    if sorted(statuses) != [200, 409]:
        raise RuntimeError(f"Concurrent Ship was not idempotent: {statuses}")
    async with factory() as db:
        source = await db.scalar(
            select(StockBalance).where(
                StockBalance.location_id == uuid.UUID(context["ready_location_id"]),
                StockBalance.product_id == uuid.UUID(context["product_id"]),
            )
        )
        if source is None or source.qty_on_hand != Decimal("23"):
            raise RuntimeError("Concurrent Ship deducted READY more than once")
    await concurrent_engine.dispose()


async def prepare_central_flow(context: dict[str, str]) -> dict[str, str]:
    marker = uuid.uuid4().hex[:8]
    central_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(central_engine, expire_on_commit=False)
    async with factory() as db:
        await seed_test_beverage(db, str(DEFAULT_COMPANY_ID))
        brand = await db.scalar(
            select(Brand).where(
                Brand.company_id == DEFAULT_COMPANY_ID,
                Brand.slug == "test-beverage",
            )
        )
        if brand is None:
            raise RuntimeError("Restaurant brand was not seeded")
        brand.central_branch_id = uuid.UUID(context["central_branch_id"])
        brand.central_ready_location_id = uuid.UUID(context["ready_location_id"])
        raw_location = await db.scalar(
            select(StockLocation).where(
                StockLocation.company_id == DEFAULT_COMPANY_ID,
                StockLocation.branch_id == uuid.UUID(context["central_branch_id"]),
                StockLocation.id != uuid.UUID(context["ready_location_id"]),
                StockLocation.deleted_at.is_(None),
                StockLocation.is_active.is_(True),
            )
        )
        if raw_location is None:
            raw_location = StockLocation(
                company_id=DEFAULT_COMPANY_ID,
                branch_id=uuid.UUID(context["central_branch_id"]),
                code=f"TS-RAW-{marker}",
                name=f"Transfer Smoke RAW {marker}",
                is_active=True,
            )
            db.add(raw_location)
            await db.flush()
        brand.central_location_id = raw_location.id
        brand_branch = await db.scalar(
            select(BrandBranch).where(
                BrandBranch.brand_id == brand.id,
                BrandBranch.branch_id == uuid.UUID(context["store_branch_id"]),
            )
        )
        if brand_branch is None:
            raise RuntimeError("Restaurant store branch was not seeded")
        brand_branch.store_location_id = uuid.UUID(context["store_location_id"])
        product = await db.get(Product, uuid.UUID(context["product_id"]))
        if product is None:
            raise RuntimeError("Transfer smoke product is missing")
        product.brand_id = brand.id

        central_user = await db.get(User, uuid.UUID(context["user_id"]))
        central_assignment = await db.scalar(
            select(UserBranch)
            .where(
                UserBranch.user_id == central_user.id,
                UserBranch.is_default.is_(True),
            )
            .options(selectinload(UserBranch.role).selectinload(Role.permissions))
        )
        central_permission = await db.scalar(
            select(Permission).where(Permission.code == "fb.kitchen.manage")
        )
        store_permission = await db.scalar(
            select(Permission).where(Permission.code == "brand.store.delivery.receive")
        )
        if central_assignment is None or central_permission is None or store_permission is None:
            raise RuntimeError("Central/store permissions are missing")
        if central_permission not in central_assignment.role.permissions:
            central_assignment.role.permissions.append(central_permission)

        store_role = Role(
            company_id=DEFAULT_COMPANY_ID,
            name=f"transfer_store_smoke_{marker}",
            is_branch_assignable=True,
        )
        store_role.permissions = [store_permission]
        db.add(store_role)
        await db.flush()
        store_username = f"transfer-store-smoke-{marker}"
        store_user = User(
            company_id=DEFAULT_COMPANY_ID,
            username=store_username,
            hashed_password=hash_password(PASSWORD),
            is_active=True,
        )
        db.add(store_user)
        await db.flush()
        db.add(
            UserBranch(
                user_id=store_user.id,
                branch_id=uuid.UUID(context["store_branch_id"]),
                role_id=store_role.id,
                brand_id=brand.id,
                business_type="restaurant",
                target_database="restaurant",
                is_default=True,
            )
        )
        closure = WapShiftClosure(
            company_id=DEFAULT_COMPANY_ID,
            brand_id=brand.id,
            branch_id=uuid.UUID(context["store_branch_id"]),
            closed_by=central_user.id,
            business_date="2026-07-22",
            round_no=1,
            total_orders=1,
            total_amount=Decimal("45"),
        )
        db.add(closure)
        await db.flush()
        order = CentralOrder(
            company_id=DEFAULT_COMPANY_ID,
            brand_id=brand.id,
            branch_id=uuid.UUID(context["store_branch_id"]),
            shift_closure_id=closure.id,
            order_number=f"TS-CO-{marker}",
            status="packed",
            business_date="2026-07-22",
            submitted_by=central_user.id,
            approved_by=central_user.id,
            packed_by=central_user.id,
        )
        db.add(order)
        await db.flush()
        item = CentralOrderItem(
            order_id=order.id,
            company_id=DEFAULT_COMPANY_ID,
            branch_id=uuid.UUID(context["store_branch_id"]),
            product_id=product.id,
            sku=product.sku,
            product_name=product.name,
            unit="ชิ้น",
            unit_cost=Decimal("7.5"),
            system_qty=Decimal("6"),
            requested_qty=Decimal("6"),
            approved_qty=Decimal("6"),
            shipped_qty=Decimal("6"),
            requested_amount=Decimal("45"),
            approved_amount=Decimal("45"),
            shipped_amount=Decimal("45"),
        )
        db.add(item)
        await db.commit()
        result = {
            "order_id": str(order.id),
            "item_id": str(item.id),
            "store_username": store_username,
        }
    await central_engine.dispose()
    return result


async def verify_central_ship(context: dict[str, str], order_id: str) -> None:
    verify_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(verify_engine, expire_on_commit=False)
    async with factory() as db:
        source = await db.scalar(
            select(StockBalance).where(
                StockBalance.location_id == uuid.UUID(context["ready_location_id"]),
                StockBalance.product_id == uuid.UUID(context["product_id"]),
            )
        )
        destination = await db.scalar(
            select(StockBalance).where(
                StockBalance.location_id == uuid.UUID(context["store_location_id"]),
                StockBalance.product_id == uuid.UUID(context["product_id"]),
            )
        )
        order = await db.get(CentralOrder, uuid.UUID(order_id))
        if source is None or source.qty_on_hand != Decimal("17"):
            raise RuntimeError("Central Ship did not deduct READY exactly once")
        if destination is None or destination.qty_on_hand != Decimal("4"):
            raise RuntimeError("Central Ship increased STORE before Receive")
        if order is None or order.transfer_order_id is None:
            raise RuntimeError("Central Ship did not create a linked Transfer")
    await verify_engine.dispose()


async def verify_central_received(context: dict[str, str], order_id: str) -> None:
    verify_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(verify_engine, expire_on_commit=False)
    async with factory() as db:
        destination = await db.scalar(
            select(StockBalance).where(
                StockBalance.location_id == uuid.UUID(context["store_location_id"]),
                StockBalance.product_id == uuid.UUID(context["product_id"]),
            )
        )
        order = await db.scalar(
            select(CentralOrder)
            .where(CentralOrder.id == uuid.UUID(order_id))
            .options(selectinload(CentralOrder.transfer_order).selectinload(TransferOrder.items))
        )
        if destination is None or destination.qty_on_hand != Decimal("9"):
            raise RuntimeError("Central Receive did not add only actual STORE quantity")
        if order is None or order.status != "received" or order.transfer_order is None:
            raise RuntimeError("Central order was not completed through its Transfer")
        transfer_item = order.transfer_order.items[0]
        if transfer_item.qty_received != Decimal("5") or transfer_item.qty_discrepancy != Decimal("1"):
            raise RuntimeError("Central discrepancy was not persisted")
    await verify_engine.dispose()


async def post_legacy_destination_at_ship(
    context: dict[str, str],
    transfer_id: str,
) -> str:
    legacy_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(legacy_engine, expire_on_commit=False)
    async with factory() as db:
        transfer = await db.scalar(
            select(TransferOrder)
            .where(TransferOrder.id == uuid.UUID(transfer_id))
            .options(selectinload(TransferOrder.items))
            .with_for_update()
        )
        if transfer is None:
            raise RuntimeError("Legacy transfer fixture is missing")
        item = transfer.items[0]
        qty = Decimal(item.qty_approved or 0)
        stock_service = StockService(db)
        source = await stock_service._get_or_create_balance(
            DEFAULT_COMPANY_ID,
            transfer.from_branch_id,
            transfer.from_location_id,
            item.product_id,
            item.variant_id,
        )
        destination = await stock_service._get_or_create_balance(
            DEFAULT_COMPANY_ID,
            transfer.to_branch_id,
            transfer.to_location_id,
            item.product_id,
            item.variant_id,
        )
        unit_cost = Decimal(source.cost_per_unit or 0)
        await stock_service._record_movement(
            source,
            "transfer_out",
            -qty,
            uuid.UUID(context["user_id"]),
            cost_per_unit=unit_cost,
            note="legacy ship fixture",
        )
        source.qty_reserved = Decimal(source.qty_reserved or 0) - qty
        await stock_service._record_movement(
            destination,
            "transfer_in",
            qty,
            uuid.UUID(context["user_id"]),
            cost_per_unit=unit_cost,
            note="legacy ship fixture",
        )
        item.qty_sent = qty
        item.qty_received = Decimal("0")
        transfer.status = "in_transit"
        transfer.shipped_at = datetime.now(timezone.utc)
        transfer.destination_posted_at_ship = True
        await db.commit()
        item_id = str(item.id)
    await legacy_engine.dispose()
    return item_id


async def verify_legacy_receive(context: dict[str, str], transfer_id: str) -> None:
    verify_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(verify_engine, expire_on_commit=False)
    async with factory() as db:
        destination = await db.scalar(
            select(StockBalance).where(
                StockBalance.location_id == uuid.UUID(context["store_location_id"]),
                StockBalance.product_id == uuid.UUID(context["product_id"]),
            )
        )
        transfer = await db.get(TransferOrder, uuid.UUID(transfer_id))
        linked_movements = list(
            (
                await db.scalars(
                    select(StockMovement).where(
                        StockMovement.reference_id == transfer_id,
                    )
                )
            ).all()
        )
        if destination is None or destination.qty_on_hand != Decimal("10"):
            raise RuntimeError("Legacy full Receive duplicated STORE stock")
        if transfer is None or transfer.status != "completed" or transfer.destination_posted_at_ship:
            raise RuntimeError("Legacy transfer was not normalized on Receive")
        if linked_movements:
            raise RuntimeError("Legacy full Receive should not create another incoming movement")
    await verify_engine.dispose()


def run() -> None:
    context = asyncio.run(prepare())
    with TestClient(app) as client:
        headers = login(client, context["username"])
        transfer = create_approved_transfer(client, headers, context, 5)
        transfer = expect(
            client.post(
                f"/api/v1/transfer/orders/{transfer['id']}/ship",
                headers=headers,
                json={"note": "ship correctness smoke"},
            ),
            200,
        )
        if transfer["status"] != "in_transit" or Decimal(str(transfer["items"][0]["qty_in_transit"])) != Decimal("5"):
            raise RuntimeError("Transfer did not enter in-transit state")
        asyncio.run(verify_after_ship(context, transfer["id"]))
        expect(
            client.post(
                f"/api/v1/transfer/orders/{transfer['id']}/ship",
                headers=headers,
                json={},
            ),
            409,
        )

        item_id = transfer["items"][0]["id"]
        partial = expect(
            client.post(
                f"/api/v1/transfer/orders/{transfer['id']}/receive",
                headers=headers,
                json={
                    "items": [{"item_id": item_id, "qty_received": 3}],
                    "finalize": False,
                },
            ),
            200,
        )
        if partial["status"] != "partially_received" or Decimal(str(partial["items"][0]["qty_in_transit"])) != Decimal("2"):
            raise RuntimeError("Partial Receive did not preserve in-transit quantity")
        expect(
            client.post(
                f"/api/v1/transfer/orders/{transfer['id']}/receive",
                headers=headers,
                json={
                    "items": [{"item_id": item_id, "qty_received": 3}],
                    "finalize": False,
                },
            ),
            409,
        )
        completed = expect(
            client.post(
                f"/api/v1/transfer/orders/{transfer['id']}/receive",
                headers=headers,
                json={
                    "items": [{"item_id": item_id, "qty_received": 4}],
                    "finalize": True,
                    "note": "short by one in smoke",
                },
            ),
            200,
        )
        line = completed["items"][0]
        if (
            completed["status"] != "completed"
            or not completed["has_discrepancy"]
            or Decimal(str(line["qty_discrepancy"])) != Decimal("1")
            or Decimal(str(line["qty_in_transit"])) != Decimal("0")
        ):
            raise RuntimeError(f"Final discrepancy was not recorded: {completed}")
        expect(
            client.post(
                f"/api/v1/transfer/orders/{transfer['id']}/receive",
                headers=headers,
                json={
                    "items": [{"item_id": item_id, "qty_received": 4}],
                    "finalize": True,
                    "note": "duplicate",
                },
            ),
            409,
        )
        asyncio.run(verify_completed(context, transfer["id"]))

        concurrent_transfer = create_approved_transfer(client, headers, context, 2)
        asyncio.run(concurrent_ship(context, concurrent_transfer["id"]))
        central_context = asyncio.run(prepare_central_flow(context))
        central_headers = login(client, context["username"])
        shipped_order = expect(
            client.post(
                f"/api/v1/restaurant/central/orders/{central_context['order_id']}/ship",
                headers=central_headers,
            ),
            200,
        )
        if shipped_order["status"] != "shipped" or shipped_order["transfer_order_status"] != "in_transit":
            raise RuntimeError("Central order did not create and Ship its Transfer")
        asyncio.run(verify_central_ship(context, central_context["order_id"]))

        store_headers = login(client, central_context["store_username"])
        partially_received = expect(
            client.post(
                f"/api/v1/restaurant/store/test-beverage/central-orders/{central_context['order_id']}/receive",
                headers=store_headers,
                json={
                    "items": [
                        {
                            "item_id": central_context["item_id"],
                            "qty_received": 4,
                        }
                    ],
                    "finalize": False,
                },
            ),
            200,
        )
        if (
            partially_received["status"] != "partially_received"
            or Decimal(str(partially_received["items"][0]["in_transit_qty"])) != Decimal("2")
        ):
            raise RuntimeError("Store partial Receive did not preserve central order in-transit quantity")
        completed_order = expect(
            client.post(
                f"/api/v1/restaurant/store/test-beverage/central-orders/{central_context['order_id']}/receive",
                headers=store_headers,
                json={
                    "items": [
                        {
                            "item_id": central_context["item_id"],
                            "qty_received": 5,
                        }
                    ],
                    "finalize": True,
                    "note": "central smoke short by one",
                },
            ),
            200,
        )
        if (
            completed_order["status"] != "received"
            or not completed_order["transfer_has_discrepancy"]
            or Decimal(str(completed_order["items"][0]["discrepancy_qty"])) != Decimal("1")
        ):
            raise RuntimeError("Store final Receive did not expose its discrepancy")
        expect(
            client.post(
                f"/api/v1/restaurant/store/test-beverage/central-orders/{central_context['order_id']}/receive",
                headers=store_headers,
                json={
                    "items": [
                        {
                            "item_id": central_context["item_id"],
                            "qty_received": 5,
                        }
                    ],
                    "finalize": True,
                    "note": "duplicate",
                },
            ),
            400,
        )
        asyncio.run(verify_central_received(context, central_context["order_id"]))

        legacy_transfer = create_approved_transfer(client, headers, context, 1)
        legacy_item_id = asyncio.run(
            post_legacy_destination_at_ship(context, legacy_transfer["id"])
        )
        normalized_legacy = expect(
            client.post(
                f"/api/v1/transfer/orders/{legacy_transfer['id']}/receive",
                headers=headers,
                json={
                    "items": [
                        {
                            "item_id": legacy_item_id,
                            "qty_received": 1,
                        }
                    ],
                    "finalize": True,
                },
            ),
            200,
        )
        if normalized_legacy["status"] != "completed":
            raise RuntimeError("Legacy destination-posted transfer did not complete")
        asyncio.run(verify_legacy_receive(context, legacy_transfer["id"]))
    print(
        "transfer_correctness_api_smoke=ok "
        f"partial_transfer={transfer['id']} concurrent_transfer={concurrent_transfer['id']} "
        f"central_order={central_context['order_id']} legacy_transfer={legacy_transfer['id']}"
    )


if __name__ == "__main__":
    run()
