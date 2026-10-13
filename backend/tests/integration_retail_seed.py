"""Check additive seed repeatability on an empty disposable Retail schema only."""
import asyncio
import importlib.util
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from sqlalchemy import select, func, text
from alembic.operations import Operations
from alembic.migration import MigrationContext
import app.models
from app.database import engine, AsyncSessionLocal
from app.models.company import Company
from app.models.branch import Branch
from app.models.restaurant import Brand, BrandBranch
from app.models.stock import StockLocation, StockBalance, StockMovement
from app.models.product import Product, ProductVariant


async def main():
    assert engine.url.database.endswith("_intake_test")
    async with AsyncSessionLocal() as db: assert await db.scalar(select(func.count()).select_from(Company))==0
    for filename in ("retailcatalog0009_product_brands.py","retailtransfer0010_store_transfers.py"):
        spec=importlib.util.spec_from_file_location("migration","/app/alembic_retail/versions/"+filename)
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        def apply(conn):
            with Operations.context(MigrationContext.configure(conn)): migration.upgrade()
        async with engine.begin() as conn: await conn.run_sync(apply)
    company,brand,branch,user,location=[uuid.uuid4() for _ in range(5)]
    async with AsyncSessionLocal() as db:
        db.add(Company(id=company,name="Seed isolated",business_slug="seed-isolated"));await db.flush()
        db.add(Branch(id=branch,company_id=company,code="STORE",name="Store"))
        db.add(Brand(id=brand,company_id=company,slug="seed",name="Retail",business_type="retail_pos"));await db.flush()
        db.add(BrandBranch(company_id=company,branch_id=branch,brand_id=brand))
        db.add(StockLocation(id=location,company_id=company,branch_id=branch,code="STORE",name="Store"))
        await db.execute(text("INSERT INTO users(id,company_id,username,hashed_password) VALUES (:id,:company,'seed-test','disabled')"),{"id":user,"company":company})
        await db.commit()
    spec=importlib.util.spec_from_file_location("seed","/checks/seed-retail-catalog-uat.py")
    seed=importlib.util.module_from_spec(spec);spec.loader.exec_module(seed)
    seed.PlatformSessionLocal=seed.RetailSessionLocal=AsyncSessionLocal
    seed.project_retail_reference_snapshot=AsyncMock() # Reference boundary covered separately; same disposable DB here.
    args=SimpleNamespace(company=str(company),brand=str(brand),branch=str(branch),user=str(user),apply=True)
    with patch.object(seed.settings,"environment","development"),patch.object(seed.settings,"saas_public_base_url","https://uat-test.invalid"),patch.object(seed.settings,"retail_service_database","retail"):
        await seed.main(args)
        await seed.main(args)
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(Product))==4
        assert await db.scalar(select(func.count()).select_from(ProductVariant))==6
        assert await db.scalar(select(func.count()).select_from(StockBalance))==14
        assert await db.scalar(select(func.count()).select_from(StockMovement))==14
        assert await db.scalar(select(func.sum(StockBalance.qty_on_hand)))==7*(15+40)
    print("PASS seed creates 4 product families, 7 SKUs, 14 balances; replay does not refill stock")
    await engine.dispose()


asyncio.run(main())
