from uuid import UUID
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import TokenData, require_permission
from app.models.credit_sales import CreditSale
from app.models.crm import Customer
from app.models.product import Product
from app.models.stock import StockLocation
from app.schemas.credit_sales import CreditSaleCreate, SaleAction, DeliveryRequest, ReceiptRequest
from app.services import credit_sales_service as svc

router = APIRouter(prefix="/api/v1/company/credit-sales", tags=["credit-sales-uat"])
view = require_permission("accounting.invoice.view")


@router.get("")
async def listing(response: Response, page: int = Query(1, ge=1, le=10000),
                  current: TokenData = Depends(view), db: AsyncSession = Depends(get_db)):
    svc.check_access(current)
    response.headers["Cache-Control"] = "private, no-store"
    rows = (await db.scalars(select(CreditSale).where(CreditSale.company_id == current.company_id,
        CreditSale.branch_id == current.branch_id).order_by(CreditSale.created_at.desc(), CreditSale.id)
        .offset((page - 1) * 25).limit(26))).all()
    return {"data": {"items": [svc.columns(r) for r in rows[:25]], "has_more": len(rows) > 25}, "error": None}


@router.get("/options")
async def options(response: Response, search: str = Query("", max_length=100),
                  current: TokenData = Depends(view), db: AsyncSession = Depends(get_db)):
    svc.check_access(current)
    response.headers["Cache-Control"] = "private, no-store"
    customers = (await db.scalars(select(Customer).where(Customer.company_id == current.company_id,
        Customer.is_active.is_(True), Customer.deleted_at.is_(None), Customer.is_blacklisted.is_(False))
        .order_by(Customer.customer_code).limit(200))).all()
    products = (await db.scalars(select(Product).where(Product.company_id == current.company_id,
        Product.is_active.is_(True), Product.is_for_sale.is_(True), Product.deleted_at.is_(None),
        Product.name.icontains(search, autoescape=True)).order_by(Product.name, Product.id).limit(100))).all()
    locations = (await db.scalars(select(StockLocation).where(StockLocation.company_id == current.company_id,
        StockLocation.branch_id == current.branch_id, StockLocation.deleted_at.is_(None), StockLocation.is_active.is_(True))
        .order_by(StockLocation.name).limit(100))).all()
    return {"data": {"customers": [{"id": c.id, "name": c.full_name, "code": c.customer_code} for c in customers],
        "products": [{"id": p.id, "name": p.name, "price": p.selling_price, "vat_type": p.vat_type} for p in products],
        "locations": [{"id": loc.id, "name": loc.name} for loc in locations],
        "notice": "แสดงลูกค้าสูงสุด 200 ราย สินค้า 100 รายการ; ค้นชื่อสินค้าเพื่อลดรายการ"}, "error": None}


@router.get("/{sale_id}")
async def get_sale(sale_id: UUID, response: Response, current: TokenData = Depends(view), db: AsyncSession = Depends(get_db)):
    response.headers["Cache-Control"] = "private, no-store"
    return {"data": await svc.detail(db, current, sale_id), "error": None}


@router.post("")
async def create_sale(payload: CreditSaleCreate, current: TokenData = Depends(view), db: AsyncSession = Depends(get_db)):
    return {"data": await svc.create(db, current, payload), "error": None}


@router.post("/{sale_id}/approve")
async def approve(sale_id: UUID, payload: SaleAction, current: TokenData = Depends(view), db: AsyncSession = Depends(get_db)):
    return {"data": await svc.action(db, current, sale_id, "approve", payload), "error": None}


@router.post("/{sale_id}/deliver")
async def deliver(sale_id: UUID, payload: DeliveryRequest, current: TokenData = Depends(view), db: AsyncSession = Depends(get_db)):
    return {"data": await svc.action(db, current, sale_id, "deliver", payload), "error": None}


@router.post("/{sale_id}/bill")
async def bill(sale_id: UUID, payload: SaleAction, current: TokenData = Depends(view), db: AsyncSession = Depends(get_db)):
    return {"data": await svc.action(db, current, sale_id, "bill", payload), "error": None}


@router.post("/{sale_id}/receive")
async def receive(sale_id: UUID, payload: ReceiptRequest, current: TokenData = Depends(view), db: AsyncSession = Depends(get_db)):
    return {"data": await svc.action(db, current, sale_id, "receive", payload), "error": None}


@router.post("/{sale_id}/cancel")
async def cancel(sale_id: UUID, payload: SaleAction, current: TokenData = Depends(view), db: AsyncSession = Depends(get_db)):
    return {"data": await svc.action(db, current, sale_id, "cancel", payload), "error": None}
