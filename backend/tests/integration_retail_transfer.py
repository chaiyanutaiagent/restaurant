"""Retail migration + transfer regression on an EMPTY disposable schema snapshot only."""
import asyncio
import importlib.util
import uuid
from dataclasses import replace
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
import httpx
from sqlalchemy import select, func, text
from alembic.migration import MigrationContext
from alembic.operations import Operations

import app.models
from app.database import engine, AsyncSessionLocal
from app.dependencies import TokenData, get_current_user, get_legacy_model_operational_db
from app.models.company import Company
from app.models.branch import Branch
from app.models.restaurant import Brand, BrandBranch
from app.models.product import Product, ProductVariant, Unit
from app.models.stock import StockBalance, StockLocation, StockMovement
from app.models.audit import AuditLog
from app.models.retail_transfer import RetailTransferScope
from app.models.transfer import TransferOrder
from app.schemas.retail_transfer import RetailTransferCreate, RetailTransferCommand
from app.services.retail_transfer_service import RetailTransferService, RECEIPT
from app.services.stock_access_service import StockAccessService
from app.services.stock_service import StockService
from app.routers.retail_transfer import router
from app.routers.transfer import router as generic_router


async def main():
    assert engine.url.database.endswith("_transfer_test"), "Disposable database only"
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(Company))==0, "Empty database only"
    spec=importlib.util.spec_from_file_location("transfer_migration","/app/alembic_retail/versions/retailtransfer0010_store_transfers.py")
    migration=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    def migrate(connection):
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.downgrade()
            migration.upgrade()
    async with engine.begin() as conn:
        await conn.run_sync(migrate)
    company,source_branch,dest_branch,other_branch,brand,other_brand,user,approver,unit,source,dest,kitchen,product,variant=[uuid.uuid4() for _ in range(14)]
    async with AsyncSessionLocal() as db:
        db.add(Company(id=company,name="Transfer test",business_slug="transfer-test"))
        await db.flush()
        db.add_all([Branch(id=source_branch,company_id=company,code="WH",name="Warehouse",is_warehouse=True),
            Branch(id=dest_branch,company_id=company,code="STORE",name="Store"),
            Branch(id=other_branch,company_id=company,code="OTHER",name="Other"),
            Brand(id=brand,company_id=company,slug="retail",name="Retail",business_type="retail_pos"),
            Brand(id=other_brand,company_id=company,slug="other",name="Other",business_type="retail_pos"),
            Unit(id=unit,company_id=company,code="PC",name="Piece")])
        await db.flush()
        for identity in (user,approver):
            await db.execute(text("INSERT INTO users(id,company_id,username,hashed_password) VALUES (:id,:company,:name,'disabled')"),{"id":identity,"company":company,"name":str(identity)})
        db.add_all([StockLocation(id=source,company_id=company,branch_id=source_branch,code="SOURCE",name="Source"),
            StockLocation(id=dest,company_id=company,branch_id=dest_branch,code="DEST",name="Destination"),
            StockLocation(id=kitchen,company_id=company,branch_id=source_branch,code="KITCHEN",name="Kitchen")])
        await db.flush()
        db.add_all([BrandBranch(company_id=company,brand_id=brand,branch_id=source_branch,store_location_id=source),
            BrandBranch(company_id=company,brand_id=brand,branch_id=dest_branch,store_location_id=dest),
            BrandBranch(company_id=company,brand_id=other_brand,branch_id=other_branch)])
        (await db.get(Brand,other_brand)).central_location_id=kitchen
        db.add(Product(id=product,company_id=company,brand_id=brand,name="Shirt",sku="SHIRT",product_type="variant",unit_id=unit,selling_price=100,cost_price=20))
        await db.flush()
        db.add(ProductVariant(id=variant,company_id=company,product_id=product,name="Black M",sku="SHIRT-BLACK-M",attributes={"color":"black","size":"M"},selling_price=110,cost_price=20))
        await db.flush()
        db.add(StockBalance(company_id=company,branch_id=source_branch,location_id=source,product_id=product,variant_id=variant,qty_on_hand=30,qty_reserved=0,cost_per_unit=20))
        await db.commit()
    store=TokenData(company_id=company,branch_id=dest_branch,brand_id=brand,user_id=user,permissions=["*"],business_type="retail_pos",target_database="retail_pos")
    warehouse=replace(store,branch_id=source_branch,user_id=approver)
    async def run(payload,order_id=None,actor=store):
        async with AsyncSessionLocal() as db:
            return await RetailTransferService(db,actor).request(payload,uuid.UUID(order_id) if order_id else None)
    async def reject(coro,status):
        try: await coro
        except HTTPException as e: assert e.status_code==status,(e.status_code,e.detail)
        else: raise AssertionError(f"Expected {status}")
    def create(qty=10,**changes):
        return RetailTransferCreate(**{**dict(request_id=uuid.uuid4(),from_location_id=source,to_location_id=dest,
            items=[dict(product_id=product,variant_id=variant,qty_requested=qty)]),**changes})
    def cmd(order,action,qty=None,**changes):
        return RetailTransferCommand(**{**dict(request_id=uuid.uuid4(),expected_version=order["version"],action=action,
            items=[dict(item_id=i["id"],quantity=qty) for i in order["items"]] if qty is not None else []),**changes})
    async def balance(location):
        async with AsyncSessionLocal() as db:
            row=await db.scalar(select(StockBalance).where(StockBalance.location_id==location))
            return (row.qty_on_hand,row.qty_reserved) if row else (Decimal(0),Decimal(0))
    async def read(identity,actor=store):
        async with AsyncSessionLocal() as db: return await RetailTransferService(db,actor).read(uuid.UUID(identity))
    async with AsyncSessionLocal() as db:
        service=RetailTransferService(db,store)
        assert {o['id'] for o in await service.options()}=={source,dest}
        assert (await service.stock(source,"BLACK"))[0]["variant_id"]==variant
        await reject(StockAccessService(db).resolve_scope(warehouse,store_only=True),403)
    await reject(run(create(),actor=replace(store,branch_id=other_branch)),403)
    await reject(run(create(from_location_id=kitchen)),404)
    await reject(run(create(),actor=replace(store,permissions=["inventory.transfer.view"])),403)
    await reject(run(create(items=[dict(product_id=product,qty_requested=1)])),422)
    request=create()
    first,replay=await asyncio.gather(run(request),run(request))
    assert first["id"]==replay["id"] and sorted([first["replayed"],replay["replayed"]])==[False,True]
    assert first["version"]==1
    await reject(run(request.model_copy(update={"note":"changed"})),409)
    await reject(read(first["id"],replace(store,brand_id=other_brand)),404)
    await reject(read(first["id"],replace(store,company_id=uuid.uuid4())),404)
    await reject(read(first["id"],replace(store,branch_id=other_branch)),404)
    pending=await run(cmd(first,"submit"),first["id"])
    await reject(run(cmd(pending,"approve",10),first["id"]),403) # destination cannot approve
    await reject(run(cmd(pending,"approve",10),first["id"],replace(warehouse,user_id=user)),409) # no self approval
    approved=await run(cmd(pending,"approve",10),first["id"],warehouse)
    assert await balance(source)==(Decimal(30),Decimal(10))
    await reject(run(cmd(approved,"ship"),first["id"]),403)
    shipped=await run(cmd(approved,"ship"),first["id"],warehouse)
    assert shipped["status"]=="in_transit" and shipped["version"]==4
    assert await balance(source)==(Decimal(20),Decimal(0))
    assert await balance(dest)==(Decimal(0),Decimal(0))
    await reject(run(cmd(shipped,"receive",4),first["id"],warehouse),403)
    await reject(run(cmd(shipped,"receive",11),first["id"]),400)
    receipt=cmd(shipped,"receive",4)
    partial,replay=await asyncio.gather(run(receipt,first["id"]),run(receipt,first["id"]))
    assert partial["status"]=="partially_received" and partial["version"]==5
    assert sorted([partial["replayed"],replay["replayed"]])==[False,True]
    assert await balance(dest)==(Decimal(4),Decimal(0))
    await reject(run(cmd(shipped,"receive",5),first["id"]),409) # stale snapshot
    await reject(run(cmd(partial,"receive",3),first["id"]),400) # cannot reverse receipt
    await reject(run(cmd(partial,"receive",4),first["id"]),409) # no delta
    await reject(run(cmd(partial,"receive",7,finalize=True),first["id"]),400) # discrepancy note mandatory
    failure=cmd(partial,"receive",7)
    with patch("app.services.stock_service.StockService._record_movement",new=AsyncMock(side_effect=RuntimeError("injected failure"))):
        try: await run(failure,first["id"])
        except RuntimeError: pass
        else: raise AssertionError("Expected stock failure")
    assert (await read(first["id"]))["version"]==5 and await balance(dest)==(Decimal(4),Decimal(0))
    async with AsyncSessionLocal() as db:
        assert not await db.scalar(select(AuditLog.id).where(AuditLog.action==RECEIPT,AuditLog.resource_id==str(failure.request_id)))
    complete=await run(cmd(partial,"receive",7,finalize=True,note="3 damaged in transit"),first["id"])
    assert complete["status"]=="completed" and complete["has_discrepancy"]
    assert Decimal(complete["items"][0]["qty_discrepancy"])==3
    assert Decimal(complete["items"][0]["qty_in_transit"])==0
    assert await balance(source)==(Decimal(20),Decimal(0)) and await balance(dest)==(Decimal(7),Decimal(0))
    assert (await run(receipt,first["id"]))["replayed"] # saved partial receipt stays valid after completion
    await reject(run(cmd(complete,"receive",10),first["id"]),409)
    await reject(run(cmd(complete,"cancel",note="too late"),first["id"]),409)
    # Approved cancellation must release reservation without changing on-hand.
    second=await run(create(2))
    second=await run(cmd(second,"submit"),second["id"])
    second=await run(cmd(second,"approve",2),second["id"],warehouse)
    assert await balance(source)==(Decimal(20),Decimal(2))
    cancelled=await run(cmd(second,"cancel",note="not needed"),second["id"])
    assert cancelled["status"]=="cancelled" and await balance(source)==(Decimal(20),Decimal(0))
    # Complete receipt without finalize=true closes normally with zero discrepancies.
    third=await run(create(2))
    third=await run(cmd(third,"submit"),third["id"])
    third=await run(cmd(third,"approve",2),third["id"],warehouse)
    third=await run(cmd(third,"ship"),third["id"],warehouse)
    third=await run(cmd(third,"receive",2),third["id"])
    assert third["status"]=="completed" and not third["has_discrepancy"]
    assert await balance(source)==(Decimal(18),Decimal(0)) and await balance(dest)==(Decimal(9),Decimal(0))
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(StockBalance).where(StockBalance.variant_id.is_(None)))==0
        assert await db.scalar(select(func.count()).select_from(StockMovement))==5
        assert await db.scalar(select(StockBalance.cost_per_unit).where(StockBalance.location_id==dest))==20
        assert len((await RetailTransferService(db,store).listing())["orders"])==3
    # Routes use real validation and the signed operational DB; old generic route cannot bypass.
    app=FastAPI();app.include_router(router);app.include_router(generic_router)
    app.dependency_overrides[get_current_user]=lambda:store
    async def test_db():
        async with AsyncSessionLocal() as db: yield db
    app.dependency_overrides[get_legacy_model_operational_db]=test_db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
        response=await client.get("/api/v1/retail/transfers")
        assert response.status_code==200,response.text
        response=await client.post("/api/v1/retail/transfers",json=create().model_dump(mode="json"))
        assert response.status_code==201,response.text
        invalid=create().model_dump(mode="json");invalid["items"]*=2
        response=await client.post("/api/v1/retail/transfers",json=invalid)
        assert response.status_code==422,response.text
        response=await client.get("/api/v1/transfer/orders")
        assert response.status_code==403,response.text
    # Concurrent first receipts from any inventory workflow must create one base
    # balance, not two rows allowed by a nullable variant unique constraint.
    simple=uuid.uuid4()
    async with AsyncSessionLocal() as db:
        db.add(Product(id=simple,company_id=company,brand_id=brand,name="Water",sku="WATER",product_type="simple",unit_id=unit,selling_price=10,cost_price=5))
        await db.commit()
    async def initial_receipt():
        async with AsyncSessionLocal() as db:
            service=StockService(db)
            row=await service._get_or_create_balance(company,dest_branch,dest,simple,None)
            await service._record_movement(balance=row,movement_type="receive",qty_delta=Decimal(1),user_id=user,cost_per_unit=Decimal(5))
            await db.commit()
    await asyncio.gather(initial_receipt(),initial_receipt())
    async with AsyncSessionLocal() as db:
        balances=(await db.scalars(select(StockBalance).where(StockBalance.product_id==simple))).all()
        assert len(balances)==1 and balances[0].qty_on_hand==2
    print("PASS migration upgrade/downgrade/upgrade on empty Retail schema; brand/branch/permission/warehouse guards")
    print("PASS variant transfer reserve/ship/in-transit/partial/final shortage/full receipt/cancel, unchanged SKU cost")
    print("PASS concurrent retries, stale version, over/under-receive, rollback, maker-checker, scoped API and generic bypass")
    print("PASS concurrent first receipt for nullable/base SKU uses one stock balance with total quantity 2")
    await engine.dispose()


asyncio.run(main())
