"""Retail scope/idempotency adapter around the existing transfer state machine.

All postings stay in the signed Retail DB. Warehouse branches must be linked to
the same store brand. This is not a bridge into Restaurant/Central Kitchen DBs.
"""
import hashlib
import uuid
from datetime import date

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.product import Product, ProductVariant
from app.models.restaurant import Brand, BrandBranch
from app.models.retail_transfer import RetailTransferScope
from app.models.stock import StockBalance, StockLocation
from app.models.transfer import TransferOrder
from app.models.user import User
from app.schemas.transfer import CreateTORequest, ApproveTORequest, ShipTORequest, ReceiveTORequest, TransferOrderRead
from app.services.retail_intake_service import lock, require_retail
from app.services.transfer_service import TransferService

RECEIPT = "retail.transfer.request"


def permit(current, permission):
    require_retail(current)
    if "*" not in current.permissions and permission not in current.permissions:
        raise HTTPException(403, "ไม่มีสิทธิ์ดำเนินการใบโอนสินค้า")


class RetailTransferEngine(TransferService):
    async def _generate_number(self, company_id, target_date: date):
        # Avoid the legacy process-local Python hash used by its daily counter.
        await lock(self.db, f"retail-transfer-number:{target_date.isoformat()}")
        return await super()._generate_number(company_id, target_date)

    async def _get_to_entity(self, to_id, company_id, *, lock=False):
        statement = select(TransferOrder).where(TransferOrder.id==to_id,TransferOrder.company_id==company_id).options(
            selectinload(TransferOrder.items), selectinload(TransferOrder.from_branch),selectinload(TransferOrder.to_branch),
            selectinload(TransferOrder.from_location),selectinload(TransferOrder.to_location),
            selectinload(TransferOrder.requester).load_only(User.id,User.username,User.display_name),
        ).execution_options(populate_existing=True)
        if lock:
            statement=statement.with_for_update()
        order=await self.db.scalar(statement)
        if order is None:
            raise HTTPException(404,"ไม่พบใบโอนสินค้า")
        order.items.sort(key=lambda row:(str(row.product_id),str(row.variant_id or "")))
        return order


class RetailTransferService:
    def __init__(self, db, current):
        require_retail(current)
        self.db,self.current=db,current
        self.engine=RetailTransferEngine(db)

    async def options(self):
        c=self.current
        permit(c,"inventory.transfer.view")
        if not await self.db.scalar(select(BrandBranch.id).where(BrandBranch.company_id==c.company_id,
            BrandBranch.brand_id==c.brand_id,BrandBranch.branch_id==c.branch_id,BrandBranch.is_active.is_(True))):
            raise HTTPException(403,"สาขาที่เลือกไม่อยู่ในแบรนด์ Retail นี้")
        kitchen_rows=(await self.db.execute(select(Brand.central_location_id,Brand.central_ready_location_id).where(Brand.company_id==c.company_id))).all()
        kitchen={identity for row in kitchen_rows for identity in row if identity}
        kitchen.update(identity for identity in (await self.db.scalars(select(BrandBranch.store_location_id).where(
            BrandBranch.company_id==c.company_id,BrandBranch.brand_id!=c.brand_id,BrandBranch.is_active.is_(True)))).all() if identity)
        rows=(await self.db.execute(select(StockLocation,Branch).join(Branch,Branch.id==StockLocation.branch_id).join(
            BrandBranch,(BrandBranch.branch_id==Branch.id)&(BrandBranch.brand_id==c.brand_id)&(BrandBranch.company_id==c.company_id)
        ).where(StockLocation.company_id==c.company_id,StockLocation.is_active.is_(True),StockLocation.deleted_at.is_(None),
            Branch.company_id==c.company_id,Branch.is_active.is_(True),Branch.deleted_at.is_(None),BrandBranch.is_active.is_(True)))).all()
        return [{"id":loc.id,"name":loc.name,"branch_id":branch.id,"branch_name":branch.name,"is_warehouse":branch.is_warehouse}
            for loc,branch in rows if loc.id not in kitchen]

    async def pair(self, from_id, to_id):
        options={row["id"]:row for row in await self.options()}
        source,dest=options.get(from_id),options.get(to_id)
        if not source or not dest or not source["is_warehouse"] or dest["is_warehouse"] or from_id==to_id:
            raise HTTPException(404,"เลือกคลังสินค้ากลาง Retail และคลังหน้าร้านของแบรนด์เดียวกัน (ไม่ใช่ครัวกลาง)")
        if self.current.branch_id not in (source["branch_id"],dest["branch_id"]):
            raise HTTPException(403,"ต้องทำงานในสาขาต้นทางหรือปลายทางของใบโอนนี้")
        return source,dest

    async def stock(self, source_id, search):
        locations={row["id"]:row for row in await self.options()}
        if source_id not in locations or not locations[source_id]["is_warehouse"]:
            raise HTTPException(404,"ไม่พบคลังสินค้ากลาง Retail")
        c=self.current
        statement=select(StockBalance,Product,ProductVariant).join(Product,Product.id==StockBalance.product_id).outerjoin(
            ProductVariant,ProductVariant.id==StockBalance.variant_id).where(
            StockBalance.company_id==c.company_id,StockBalance.location_id==source_id,
            Product.company_id==c.company_id,Product.brand_id==c.brand_id,Product.is_active.is_(True),Product.deleted_at.is_(None),
            or_((Product.product_type=="simple")&(StockBalance.variant_id.is_(None)),
                (Product.product_type=="variant")&(ProductVariant.company_id==c.company_id)&(ProductVariant.product_id==Product.id)&
                ProductVariant.is_active.is_(True)&ProductVariant.deleted_at.is_(None)))
        if search:
            like=f"%{search}%"
            statement=statement.where(or_(Product.name.ilike(like),Product.sku.ilike(like),Product.barcode.ilike(like),
                ProductVariant.name.ilike(like),ProductVariant.sku.ilike(like),ProductVariant.barcode.ilike(like)))
        rows=(await self.db.execute(statement.order_by(Product.name,StockBalance.id).limit(100))).all()
        return [{"product_id":p.id,"variant_id":v.id if v else None,"name":p.name+(f" · {v.name}" if v else ""),
            "sku":v.sku if v else p.sku,"available":str(b.qty_available)} for b,p,v in rows]

    async def scope(self, order_id, *, locking=False):
        c=self.current
        statement=select(RetailTransferScope).join(TransferOrder,TransferOrder.id==RetailTransferScope.order_id).where(
            RetailTransferScope.order_id==order_id,RetailTransferScope.company_id==c.company_id,RetailTransferScope.brand_id==c.brand_id,
            TransferOrder.company_id==c.company_id,or_(TransferOrder.from_branch_id==c.branch_id,TransferOrder.to_branch_id==c.branch_id))
        if locking:
            statement=statement.with_for_update(of=RetailTransferScope).execution_options(populate_existing=True)
        row=await self.db.scalar(statement)
        if not row:
            raise HTTPException(404,"ไม่พบใบโอนในบริษัท แบรนด์ และสาขาที่เลือก")
        return row

    async def read(self, order_id):
        permit(self.current,"inventory.transfer.view")
        scope=await self.scope(order_id)
        order=await self.engine.get_to(order_id,self.current.company_id)
        return {**TransferOrderRead.model_validate(order).model_dump(mode="json"),"version":scope.version}

    async def listing(self, page=1):
        c=self.current
        permit(c,"inventory.transfer.view")
        ids=(await self.db.scalars(select(TransferOrder.id).join(RetailTransferScope,RetailTransferScope.order_id==TransferOrder.id).where(
            RetailTransferScope.company_id==c.company_id,RetailTransferScope.brand_id==c.brand_id,TransferOrder.company_id==c.company_id,
            or_(TransferOrder.from_branch_id==c.branch_id,TransferOrder.to_branch_id==c.branch_id)
        ).order_by(TransferOrder.created_at.desc()).offset((page-1)*20).limit(21))).all()
        return {"orders":[await self.read(identity) for identity in ids[:20]],"has_more":len(ids)>20}

    async def request(self, payload, order_id=None):
        c=self.current
        action=payload.action if order_id else "create"
        permit(c,"inventory.transfer.approve" if action in ("approve","ship") else "inventory.transfer.create")
        permit(c,"inventory.transfer.view")
        fingerprint=hashlib.sha256((payload.model_dump_json()+str(order_id)+str(c.user_id)+str(c.branch_id)+str(c.brand_id)).encode()).hexdigest()
        try:
            await lock(self.db,f"{RECEIPT}:{c.company_id}:{payload.request_id}")
            receipt=await self.db.scalar(select(AuditLog).where(AuditLog.company_id==c.company_id,
                AuditLog.action==RECEIPT,AuditLog.resource_id==str(payload.request_id)))
            if receipt:
                if receipt.new_value["fingerprint"]!=fingerprint:
                    raise HTTPException(409,"คำขอนี้เคยบันทึกด้วยข้อมูลอื่นแล้ว")
                return {**receipt.new_value["result"],"replayed":True}
            if order_id is None:
                source,dest=await self.pair(payload.from_location_id,payload.to_location_id)
                for item in payload.items:
                    p=await self.db.scalar(select(Product).where(Product.id==item.product_id,Product.company_id==c.company_id,
                        Product.brand_id==c.brand_id,Product.is_active.is_(True),Product.deleted_at.is_(None)))
                    if not p or p.product_type not in ("simple","variant") or (p.product_type=="variant")!=(item.variant_id is not None):
                        raise HTTPException(422,"เลือกสินค้า Retail และแบบสินค้าให้ถูกต้อง")
                    if item.variant_id and not await self.db.scalar(select(ProductVariant.id).where(ProductVariant.id==item.variant_id,
                        ProductVariant.product_id==p.id,ProductVariant.company_id==c.company_id,ProductVariant.is_active.is_(True),ProductVariant.deleted_at.is_(None))):
                        raise HTTPException(404,"ไม่พบแบบสินค้า")
                order=await self.engine.create_to(c.company_id,c.user_id,CreateTORequest(
                    from_branch_id=source["branch_id"],to_branch_id=dest["branch_id"],from_location_id=payload.from_location_id,
                    to_location_id=payload.to_location_id,note=payload.note,items=[i.model_dump() for i in payload.items]),commit=False)
                order_id=order.id
                scope=RetailTransferScope(order_id=order_id,company_id=c.company_id,brand_id=c.brand_id,version=1)
                self.db.add(scope)
            else:
                scope=await self.scope(order_id,locking=True)
                order=await self.engine._get_to_entity(order_id,c.company_id,lock=True)
                await self.pair(order.from_location_id,order.to_location_id)
                if scope.version!=payload.expected_version:
                    raise HTTPException(409,"ใบโอนเปลี่ยนแปลงแล้ว กรุณาโหลดข้อมูลใหม่ก่อนทำรายการ")
                if action in ("approve","ship") and c.branch_id!=order.from_branch_id:
                    raise HTTPException(403,"ต้องอนุมัติและส่งจากสาขาคลังต้นทางเท่านั้น")
                if action=="receive" and c.branch_id!=order.to_branch_id:
                    raise HTTPException(403,"ต้องรับสินค้าที่สาขาปลายทางเท่านั้น")
                if action=="submit":
                    await self.engine.submit_to(order_id,c.company_id,c.user_id,commit=False)
                elif action=="approve":
                    await self.engine.approve_to(order_id,c.company_id,c.user_id,ApproveTORequest(
                        items=[{"item_id":i.item_id,"qty_approved":i.quantity} for i in payload.items],note=payload.note),commit=False)
                elif action=="ship":
                    await self.engine.ship_to(order_id,c.company_id,c.user_id,ShipTORequest(note=payload.note),commit=False)
                elif action=="receive":
                    await self.engine.receive_to(order_id,c.company_id,c.user_id,ReceiveTORequest(
                        items=[{"item_id":i.item_id,"qty_received":i.quantity} for i in payload.items],note=payload.note,finalize=payload.finalize),commit=False)
                elif action=="cancel":
                    await self.engine.cancel_to(order_id,c.company_id,c.user_id,payload.note,commit=False)
                scope.version+=1
            await self.db.flush()
            result=await self.read(order_id)
            self.db.add(AuditLog(company_id=c.company_id,branch_id=c.branch_id,user_id=c.user_id,action=RECEIPT,
                resource="RetailTransfer",resource_id=str(payload.request_id),new_value={"fingerprint":fingerprint,"result":result}))
            await self.db.commit()
            return {**result,"replayed":False}
        except Exception:
            await self.db.rollback()
            raise
