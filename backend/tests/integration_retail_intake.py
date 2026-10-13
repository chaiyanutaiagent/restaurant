"""Run only against an empty disposable PostgreSQL database ending in _intake_test."""
import asyncio
import io
import base64
import uuid
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
from app.models.product import Product, Unit, ProductImage
from app.models.stock import StockBalance, StockLocation, StockMovement
from app.models.audit import AuditLog
from app.schemas.retail_intake import RetailIntakeRequest
from app.services.retail_intake_service import intake, lookup, ACTION
from app.dependencies import get_current_user, get_legacy_model_operational_db
from app.routers.products import router


async def main():
    assert engine.url.database.endswith("_intake_test"), "Disposable test database required"
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
    await engine.dispose()


asyncio.run(main())
