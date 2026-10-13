"""Explicit UAT-only additive examples. Rerunning never refills stock already used."""
import argparse
import asyncio
import json
import uuid
from sqlalchemy import select
from sqlalchemy.orm import load_only
from app.config import settings
from app.database import PlatformSessionLocal, RetailSessionLocal
from app.dependencies import TokenData
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.product import Unit, Category
from app.models.restaurant import Brand, BrandBranch
from app.models.stock import StockLocation
from app.models.user import User
from app.schemas.retail_intake import RetailIntakeRequest
from app.schemas.stock import ReceiveStockRequest
from app.services.retail_intake_service import intake, lock
from app.services.retail_catalog_service import create_brand
from app.services.retail_reference_projector import project_retail_reference_snapshot
from app.services.stock_service import StockService


async def main(args):
    if not args.apply or settings.environment != "development" or not settings.saas_public_base_url.startswith("https://uat-") or settings.retail_service_database != "retail" or RetailSessionLocal is None:
        raise RuntimeError("Explicit --apply and configured UAT Retail boundary required")
    company,brand,branch,user=map(uuid.UUID,(args.company,args.brand,args.branch,args.user))
    identity=lambda key:uuid.uuid5(company,"retail-catalog-demo-v1:"+str(brand)+":"+key)
    warehouse_id,warehouse_location=identity("warehouse-branch"),identity("warehouse-location")
    async with PlatformSessionLocal() as db:
        b=await db.get(Brand,brand)
        link=await db.scalar(select(BrandBranch).where(BrandBranch.company_id==company,BrandBranch.brand_id==brand,BrandBranch.branch_id==branch,BrandBranch.is_active.is_(True)))
        actor=await db.scalar(select(User).where(User.id==user).options(load_only(User.id,User.company_id,User.is_active)))
        assert b and b.company_id==company and b.business_type=="retail_pos" and link
        assert actor and actor.company_id==company and actor.is_active
        if not await db.get(Branch,warehouse_id):
            db.add(Branch(id=warehouse_id,company_id=company,code="UAT-RTL-WH",name="UAT คลังกลาง Retail ตัวอย่าง",is_warehouse=True))
            await db.flush()
            db.add(BrandBranch(id=identity("warehouse-link"),company_id=company,brand_id=brand,branch_id=warehouse_id))
            db.add(AuditLog(company_id=company,user_id=user,action="retail.demo.warehouse.create",resource="Branch",resource_id=str(warehouse_id),new_value={"uat_only":True}))
            await db.commit()
    await project_retail_reference_snapshot(company_id=company,brand_ids=(brand,))
    async with RetailSessionLocal() as db:
        location=await db.scalar(select(StockLocation).where(StockLocation.company_id==company,StockLocation.branch_id==branch,StockLocation.is_active.is_(True),StockLocation.deleted_at.is_(None)).order_by(StockLocation.created_at).limit(1))
        if not location: raise RuntimeError("Configure the store location before seeding")
        store_location=location.id
        if not await db.get(StockLocation,warehouse_location):
            db.add(StockLocation(id=warehouse_location,company_id=company,branch_id=warehouse_id,code="UAT-RTL-WH",name="UAT สต๊อกคลังกลาง Retail"))
        unit_id=identity("unit")
        if not await db.get(Unit,unit_id): db.add(Unit(id=unit_id,company_id=company,code="UAT-PC",name="ชิ้น (UAT ตัวอย่าง)"))
        for name in ("ขนม","เสื้อผ้า","รองเท้า","ของใช้"):
            if not await db.get(Category,identity(name)): db.add(Category(id=identity(name),company_id=company,code="UAT-"+str(identity(name))[:8],name="UAT ตัวอย่าง · "+name))
        await db.commit()
    current=TokenData(company_id=company,brand_id=brand,branch_id=branch,user_id=user,permissions=["*"],business_type="retail_pos",target_database="retail_pos")
    catalog=[
        ("ขนม","UAT Snack","UAT มันฝรั่งทอด",[("FCS-UAT-SNACK-01",{"รสชาติ":"ดั้งเดิม","ขนาด":"48 กรัม"},20,12),("FCS-UAT-SNACK-02",{"รสชาติ":"บาร์บีคิว","ขนาด":"48 กรัม"},22,13)]),
        ("เสื้อผ้า","UAT Wear","UAT เสื้อยืด",[("FCS-UAT-SHIRT-01",{"สี":"ดำ","ไซซ์":"M"},199,90),("FCS-UAT-SHIRT-02",{"สี":"ขาว","ไซซ์":"L"},219,100)]),
        ("รองเท้า","UAT Step","UAT รองเท้าผ้าใบ",[("FCS-UAT-SHOE-01",{"สี":"ดำ","เบอร์":"42"},590,300),("FCS-UAT-SHOE-02",{"สี":"ขาว","เบอร์":"43"},690,350)]),
        ("ของใช้","UAT Home","UAT ถุงผ้า",[("FCS-UAT-BAG-01",{},49,20)]),
    ]
    results=[]
    for category,product_brand,name,variants in catalog:
        async with RetailSessionLocal() as db: brand_row=await create_brand(db,current,product_brand)
        parent=None
        for barcode,attributes,price,cost in variants:
            async with RetailSessionLocal() as db:
                result=await intake(db,current,RetailIntakeRequest(request_id=identity(barcode),barcode=barcode,name=name,
                    unit_id=unit_id,category_id=identity(category),product_brand_id=brand_row["id"],
                    product_type="variant" if attributes else "simple",parent_product_id=parent,attributes=attributes,
                    location_id=store_location,qty=15,cost_price=cost,selling_price=price),None)
            if attributes: parent=uuid.UUID(str(result["product_id"]))
            async with RetailSessionLocal() as db:
                marker="warehouse:"+barcode
                await lock(db,"retail-demo:"+str(company)+marker)
                if not await db.scalar(select(AuditLog.id).where(AuditLog.company_id==company,AuditLog.action=="retail.demo.opening",AuditLog.resource_id==marker)):
                    await StockService(db).receive(company,user,ReceiveStockRequest(location_id=warehouse_location,
                        items=[dict(product_id=result["product_id"],variant_id=result.get("variant_id"),qty=40,cost_per_unit=cost)],
                        note="UAT ตัวอย่างเท่านั้น",reference_type="opening",reference_id=marker),commit=False)
                    db.add(AuditLog(company_id=company,branch_id=warehouse_id,user_id=user,action="retail.demo.opening",resource="StockLocation",resource_id=marker,new_value={"product_id":str(result["product_id"]),"qty":40}))
                    await db.commit()
            results.append({"barcode":barcode,"product_id":str(result["product_id"]),"variant_id":str(result.get("variant_id") or ""),"replayed":result["replayed"]})
    print(json.dumps({"company_id":str(company),"brand_id":str(brand),"store_branch_id":str(branch),"warehouse_branch_id":str(warehouse_id),"warehouse_location_id":str(warehouse_location),"store_initial_per_sku":15,"warehouse_initial_per_sku":40,"items":results,"sales_or_payments_created":False},ensure_ascii=False))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    for option in ("company","brand","branch","user"): parser.add_argument("--"+option,required=True)
    parser.add_argument("--apply",action="store_true")
    asyncio.run(main(parser.parse_args()))
