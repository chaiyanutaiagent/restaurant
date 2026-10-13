"""Run only against an empty disposable PostgreSQL database ending in _intake_test."""
import asyncio
import io
import base64
import uuid
import importlib.util
from dataclasses import replace
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException, UploadFile
import httpx
from sqlalchemy import func, select, text

import app.models  # register metadata
from app.database import engine, AsyncSessionLocal
from app.dependencies import TokenData
from app.models.company import Company
from app.models.branch import Branch
from app.models.restaurant import Brand
from app.models.product import Product, ProductVariant, Unit, ProductImage
from app.models.retail_catalog import RetailProductBrandLink
from app.services import retail_catalog_service
from app.services.stock_access_service import StockAccessService
from app.services.sale_service import SaleService
from app.services.product_service import ProductService
from app.models.stock import StockBalance, StockLocation, StockMovement
from app.models.audit import AuditLog
from app.schemas.retail_intake import RetailIntakeRequest
from app.services.retail_intake_service import intake, lookup, ACTION
from app.dependencies import get_current_user, get_legacy_model_operational_db
from app.routers.products import router


async def main():
    assert engine.url.database.endswith("_intake_test"), "Disposable test database required"
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(Company)) == 0, "Empty test database required"
    # Exercise the exact additive migration and its empty-schema rollback, never a live database.
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    spec = importlib.util.spec_from_file_location("catalog_migration", "/app/alembic_retail/versions/retailcatalog0009_product_brands.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    def migrate(connection):
        with Operations.context(MigrationContext.configure(connection)):
            # Supports schema-only snapshots taken both before and after this release.
            from sqlalchemy import inspect
            if inspect(connection).has_table("retail_product_brands"):
                migration.downgrade()
            migration.upgrade()
            migration.downgrade()
            migration.upgrade()
    async with engine.begin() as connection:
        await connection.run_sync(migrate)
    # Load schema-only from Retail migrations before running; never create/drop live tables here.
    company, branch, other_branch, brand, user, unit, location = [uuid.uuid4() for _ in range(7)]
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(Company)) == 0
        db.add(Company(id=company, name="Intake test", business_slug="intake-test"))
        await db.flush()
        db.add_all([Branch(id=branch, company_id=company, code="A", name="Retail A"),
            Branch(id=other_branch, company_id=company, code="B", name="Other branch"),
            Brand(id=brand, company_id=company, slug="retail-test", name="Retail", business_type="retail_pos"),
            Unit(id=unit, company_id=company, code="PC", name="Piece")])
        await db.flush()
        # Retail's user table is a reference projection, not the full identity model.
        await db.execute(text("INSERT INTO users (id, company_id, username, hashed_password) VALUES (:id,:company,'intake-test','disabled')"), {"id":user,"company":company})
        db.add(StockLocation(id=location, company_id=company, branch_id=branch, code="SHOP", name="Shop"))
        await db.commit()
    current = TokenData(company_id=company, branch_id=branch, brand_id=brand, user_id=user,
                        permissions=["*"], business_type="retail_pos", target_database="retail_pos")
    def data(**changes):
        return RetailIntakeRequest(**{**dict(request_id=uuid.uuid4(), barcode="0000123456789",
            name="Water", unit_id=unit, location_id=location, qty="10", cost_price="5", selling_price="10"), **changes})
    async def run(payload, actor=current, image=None):
        async with AsyncSessionLocal() as db:
            try:
                return await intake(db, actor, payload, image)
            except Exception:
                await db.rollback()
                raise
    async def rejects(request, status, actor=current):
        try:
            await run(request, actor)
        except HTTPException as error:
            assert error.status_code == status, (error.status_code, error.detail)
        else:
            raise AssertionError("Expected rejection")

    request = data()
    first, replay = await asyncio.gather(run(request), run(request))
    assert first["product_id"] == replay["product_id"]
    assert sorted([first["replayed"], replay["replayed"]]) == [False, True]
    product_id = uuid.UUID(first["product_id"])
    await rejects(request.model_copy(update={"qty":Decimal("11")}), 409)
    await rejects(data(), 409)
    received = await run(data(existing_product_id=product_id, qty=2, selling_price=999))
    assert not received["created"]
    async with AsyncSessionLocal() as db:
        assert (await db.get(Product, product_id)).selling_price == Decimal("10")
        assert await db.scalar(select(StockBalance.qty_on_hand)) == Decimal("12")
        assert await db.scalar(select(func.count()).select_from(StockMovement)) == 2
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action==ACTION)) == 2
        assert (await lookup(db,current,"0000123456789"))["product"]["id"] == str(product_id)
    await rejects(data(barcode="other-branch"),404,replace(current,branch_id=other_branch))
    await rejects(data(barcode="other-brand"),404,replace(current,company_id=uuid.uuid4()))
    await rejects(data(),403,replace(current,permissions=["inventory.product.create"]))
    await rejects(data(unit_id=uuid.uuid4(),barcode="bad-unit"),404)
    with patch("app.services.retail_intake_service.UploadService.save_image", new=AsyncMock(side_effect=HTTPException(400,"bad image"))):
        try:
            await run(data(barcode="bad-image"), image=UploadFile(io.BytesIO(b"bad"),filename="bad.png"))
        except HTTPException as error: assert error.status_code == 400
        else: raise AssertionError("Image failure required")
    with patch("app.services.retail_intake_service.UploadService.save_image",new=AsyncMock(return_value="/uploads/test.png")):
        image_result=await run(data(barcode="with-image",qty=0),image=UploadFile(io.BytesIO(b"image"),filename="test.png"))
        assert image_result["image_url"] == "/uploads/test.png"
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(Product).where(Product.barcode=="bad-image")) == 0
        assert await db.scalar(select(func.count()).select_from(ProductImage)) == 1
        assert await db.scalar(select(func.count()).select_from(Product)) == 2
    # Failed stock write must also roll back product creation, not just the movement.
    with patch("app.services.retail_intake_service.StockService.receive",new=AsyncMock(side_effect=RuntimeError("stock failed"))):
        try: await run(data(barcode="failed-stock"))
        except RuntimeError: pass
        else: raise AssertionError("Expected stock failure")
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(Product).where(Product.barcode=="failed-stock")) == 0
    # Exercise real multipart parsing and image validation, not just the service call.
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: current
    async def test_db():
        async with AsyncSessionLocal() as session:
            yield session
    app.dependency_overrides[get_legacy_model_operational_db] = test_db
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1V8AAAAASUVORK5CYII=")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
        response = await client.post("/api/v1/products/retail/intake",data={"payload":data(barcode="multipart-real-image",qty=0).model_dump_json()},files={"image":("test.png",png,"image/png")})
        assert response.status_code == 201, response.text
        assert response.json()["data"]["image_url"].startswith("/uploads/products/")
        response = await client.post("/api/v1/products/retail/intake",data={"payload":"not-json"})
        assert response.status_code == 422
        response = await client.get("/api/v1/products/retail/intake-lookup",params={"barcode":"0000123456789"})
        assert response.status_code == 200
        assert response.json()["data"]["product"]["id"] == str(product_id)
    print("PASS: atomic create/stock, concurrent retry, duplicate, existing receipt, unchanged price, tenant/branch/permission guards, image failure and stock rollback")
    print("PASS: multipart route, real PNG upload, malformed payload and exact lookup route")
    # Variant-specific receipts reuse the same inventory engine without touching base stock.
    async with AsyncSessionLocal() as db:
        maker = await retail_catalog_service.create_brand(db,current,"Test Maker")
        same = await retail_catalog_service.create_brand(db,current,"test maker")
        assert maker["id"] == same["id"] and same["reused"]
        assert await retail_catalog_service.list_brands(db,replace(current,company_id=uuid.uuid4())) == []
    request = data(barcode="shirt-black-m",name="Shirt",product_type="variant",
        product_brand_id=maker["id"],attributes={"สี":"ดำ","ไซซ์":"M"},qty=3,selling_price=199)
    first,replay = await asyncio.gather(run(request),run(request))
    assert first["variant_id"] == replay["variant_id"]
    assert sorted([first["replayed"],replay["replayed"]]) == [False,True]
    parent, black = uuid.UUID(first["product_id"]), uuid.UUID(first["variant_id"])
    added = await run(data(barcode="shirt-white-l",parent_product_id=parent,attributes={"สี":"ขาว","ไซซ์":"L"},qty=5,selling_price=299))
    white = uuid.UUID(added["variant_id"])
    await rejects(data(barcode="duplicate-options",parent_product_id=parent,attributes={"ไซซ์":"m","สี":"ดำ"}),409)
    await rejects(data(barcode="wrong-dimensions",parent_product_id=parent,attributes={"ขนาด":"XL"}),422)
    await rejects(data(barcode="cross-brand-parent",parent_product_id=parent,attributes={"สี":"แดง","ไซซ์":"M"}),404,replace(current,brand_id=uuid.uuid4()))
    await rejects(data(barcode="not-a-family",parent_product_id=product_id,attributes={"สี":"แดง"}),404)
    await rejects(data(barcode="wrong-brand-id",product_brand_id=uuid.uuid4()),404)
    await rejects(data(barcode="shirt-black-m",existing_product_id=parent,existing_variant_id=white),409)
    await run(data(barcode="shirt-black-m",existing_product_id=parent,existing_variant_id=black,qty=2,selling_price=999))
    async with AsyncSessionLocal() as db:
        assert (await db.get(ProductVariant,black)).selling_price == Decimal("199")
        balances = list((await db.scalars(select(StockBalance).where(StockBalance.product_id==parent))).all())
        assert {row.variant_id:row.qty_on_hand for row in balances} == {black:Decimal(5),white:Decimal(5)}
        assert all(row.branch_id==branch and row.location_id==location for row in balances)
        assert await db.get(RetailProductBrandLink,parent)
        found = (await lookup(db,current,"shirt-black-m"))["product"]
        assert found["variant_id"] == str(black) and found["selling_price"] == "199.0000"
        families = await retail_catalog_service.parents(db,current,"Shirt")
        assert len(families)==1 and families[0]["product_brand_name"]=="Test Maker"
        products,_ = await ProductService(db).list_products(company, search="Test Maker",brand_id=brand,retail_merchandising=True)
        assert [p.id for p in products] == [parent]
        # The POS lookup provides the chosen variant price/stock and demands selection for the parent.
        from app.routers.products import lookup_retail_product
        found = await lookup_retail_product(code="shirt-black-m",location_id=location,qty=Decimal(1),current=current,db=db)
        assert found["data"]["product"]["selected_variant_id"] == str(black)
        assert Decimal(found["data"]["product"]["server_price"]) == 199
        family = await db.get(Product,parent)
        found = await lookup_retail_product(code=family.sku,location_id=location,qty=Decimal(1),current=current,db=db)
        assert found["data"]["result"] == "variant_required" and len(found["data"]["product"]["variants"])==2
        from app.schemas.pos import OpenShiftRequest, CreateSaleRequest
        seller=SaleService(db,legacy_side_effects_enabled=False,retail_actor=current)
        shift=await seller.open_shift(company,branch,user,OpenShiftRequest(location_id=location))
        shift_id=shift.id
        def sale(variant_id=black,price=199):
            return CreateSaleRequest(shift_id=shift_id,location_id=location,payment_method="cash",paid_amount=price,
                client_order_id=str(uuid.uuid4()),items=[dict(product_id=parent,variant_id=variant_id,qty=1,
                    unit_price=price,original_price=price,vat_type="included",vat_rate=7)])
        try:
            await seller.create_sale(company,branch,user,sale(None),brand_id=brand)
        except HTTPException as error:
            assert error.status_code==422
            await db.rollback()
        else: raise AssertionError("Parent-only stock must never be sold")
        sold=await seller.create_sale(company,branch,user,sale(),brand_id=brand)
        assert sold.status=="completed" and sold.total_amount==Decimal(199)
        assert sold.items[0].variant_id==black
        assert sold.items[0].variant_name and sold.items[0].sku
        sold_id,sold_item=sold.id,sold.items[0].id
        db.expire_all()
        balances=list((await db.scalars(select(StockBalance).where(StockBalance.product_id==parent))).all())
        assert {row.variant_id:row.qty_on_hand for row in balances}=={black:Decimal(4),white:Decimal(5)}
        # Work item 7: refund uses immutable bill price/SKU, never today's catalog price.
        from app.services.refund_service import RefundService
        from app.services.approval_service import ApprovalEvidence
        from app.schemas.pos import RefundQuoteCreateRequest, RefundExecuteRequest, RefundOperationActionRequest
        approver=uuid.uuid4()
        await db.execute(text("INSERT INTO users(id,company_id,username,hashed_password) VALUES (:id,:company,'refund-approver','disabled')"),{"id":approver,"company":company})
        (await db.get(ProductVariant,black)).selling_price=999
        await db.commit()
        refunds=RefundService(db,retail_cash_pilot=True)
        async def refund(disposition):
            quote=await refunds.create_quote(company_id=company,branch_id=branch,user_id=user,
                data=RefundQuoteCreateRequest(order_id=sold_id,shift_id=shift_id,items=[dict(order_item_id=sold_item,qty="0.5")],
                    reason_code="other",reason_note="Variant acceptance",stock_disposition=disposition,idempotency_key=str(uuid.uuid4())))
            assert Decimal(quote.totals_snapshot["total_amount"])==Decimal("99.50")
            assert quote.items_snapshot[0]["variant_id"]==str(black)
            assert "ดำ" in quote.items_snapshot[0]["product_name"] or "Black" in quote.items_snapshot[0]["product_name"]
            request=RefundExecuteRequest(quote_id=quote.id,quote_hash=quote.quote_hash,order_id=sold_id,
                expected_order_version=quote.order_version,total_amount="99.50",reason_code="other",reason_note="Variant acceptance",
                stock_disposition=disposition,idempotency_key=str(uuid.uuid4()))
            op=await refunds.execute(company_id=company,branch_id=branch,user_id=user,data=request,
                approval=ApprovalEvidence(action="pos.refund.create",requester_id=user,approver_id=approver,reason="Test",mode="test"))
            action=RefundOperationActionRequest(expected_version=op.row_version,idempotency_key=str(uuid.uuid4()))
            completed=await refunds.confirm_cash(op.id,company,branch,user,action)
            assert completed.status=="completed"
            assert (await refunds.confirm_cash(op.id,company,branch,user,action)).id==completed.id
        await refund("sellable")
        await refund("none")
        db.expire_all()
        balances=list((await db.scalars(select(StockBalance).where(StockBalance.product_id==parent))).all())
        assert {row.variant_id:row.qty_on_hand for row in balances}=={black:Decimal("4.5"),white:Decimal(5)}
        # Report requires the additive transfer table migration as well.
        spec2=importlib.util.spec_from_file_location("transfer_migration","/app/alembic_retail/versions/retailtransfer0010_store_transfers.py")
        migration2=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(migration2)
        def transfer_schema(conn):
            with Operations.context(MigrationContext.configure(conn)): migration2.upgrade()
        await db.commit()
        async with engine.begin() as conn: await conn.run_sync(transfer_schema)
        from app.routers.retail_reports import sku_report
        from datetime import datetime
        from zoneinfo import ZoneInfo
        today=datetime.now(ZoneInfo("Asia/Bangkok")).date()
        report=(await sku_report(start=today,end=today,search="",page=1,current=current,db=db))["data"]
        black_row=next(r for r in report["rows"] if r["variant_id"]==black)
        assert black_row["sold"]==1 and black_row["returned"]==1 and black_row["net_quantity"]==0
        assert black_row["refund_amount"]==199 and black_row["line_subtotal"]==199 and black_row["available"]==Decimal("4.5")
        assert black_row["product_brand_name"]
        empty=(await sku_report(start=today,end=today,search="",page=1,current=replace(current,brand_id=uuid.uuid4()),db=db))["data"]
        assert empty["rows"]==[]
        print("PASS SKU receipt snapshot; partial sellable/non-sellable cash returns; replay; original price; branch/brand report totals")
        # A central location in the very same branch is not a retail stock location, even for '*'.
        central_id=uuid.uuid4()
        db.add(StockLocation(id=central_id,company_id=company,branch_id=branch,code="CENTRAL",name="Central"))
        await db.flush()
        shop_brand=await db.get(Brand,brand)
        shop_brand.central_location_id=central_id
        await db.commit()
        scope=await StockAccessService(db).resolve_scope(current)
        assert scope.branch_id==branch and location in scope.location_ids and central_id not in scope.location_ids
        for operation in (
            StockAccessService(db).resolve_scope(current,requested_branch_id=other_branch),
            SaleService(db,retail_actor=current)._get_location(company,central_id),
            lookup_retail_product(code="shirt-black-m",location_id=central_id,qty=Decimal(1),current=current,db=db),
        ):
            try: await operation
            except HTTPException as error: assert error.status_code==404
            else: raise AssertionError("Cross-store/central scope should fail")
    await rejects(data(barcode="central-intake",location_id=central_id),404)
    print("PASS: Retail migration roundtrip; brand isolation/reuse; variant create/append/receive/retry; independent stock; duplicate attributes; POS price/selection; branch and central exclusion")
    await engine.dispose()


asyncio.run(main())
