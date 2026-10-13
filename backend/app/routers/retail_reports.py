"""Branch-local Retail SKU report. Reads transactions, never reprices old bills."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import TokenData, get_legacy_model_operational_db, require_permission
from app.routers.products import ok
from app.services.retail_intake_service import require_retail
from app.services.stock_access_service import StockAccessService

router = APIRouter(prefix="/api/v1/retail/reports", tags=["retail-reports"])


@router.get("/skus")
async def sku_report(
    start: date, end: date, search: str = Query(default="", max_length=150),
    page: int = Query(default=1, ge=1),
    current: TokenData = Depends(require_permission("pos.report.view")),
    db: AsyncSession = Depends(get_legacy_model_operational_db),
):
    require_retail(current)
    if end < start or (end-start).days > 366:
        raise HTTPException(422, "เลือกช่วงวันที่ไม่เกิน 367 วัน และวันสิ้นสุดไม่น้อยกว่าวันเริ่ม")
    scope = await StockAccessService(db).resolve_scope(current)
    bkk = ZoneInfo("Asia/Bangkok")
    params = dict(company=current.company_id, branch=current.branch_id, brand=current.brand_id,
        locations=list(scope.location_ids or ()), start=datetime.combine(start,time.min,bkk),
        end=datetime.combine(end+timedelta(days=1),time.min,bkk),
        search=f"%{search.strip()}%", offset=(page-1)*100)
    result = await db.execute(text("""
        WITH catalog AS (
          SELECT p.id product_id, v.id variant_id, p.name product_name, v.name variant_name,
            COALESCE(v.sku,p.sku) sku, COALESCE(v.barcode,p.barcode) barcode,
            pb.name product_brand_name, COALESCE(v.attributes,'{}'::json) attributes,
            p.is_active AND p.deleted_at IS NULL AND (v.id IS NULL OR (v.is_active AND v.deleted_at IS NULL)) active
          FROM products p LEFT JOIN product_variants v ON v.product_id=p.id AND v.company_id=p.company_id
          LEFT JOIN retail_product_brand_links bl ON bl.product_id=p.id AND bl.company_id=p.company_id
          LEFT JOIN retail_product_brands pb ON pb.id=bl.product_brand_id AND pb.company_id=p.company_id
          WHERE p.company_id=:company AND p.brand_id=:brand AND
            ((p.product_type='simple' AND v.id IS NULL) OR (p.product_type='variant' AND v.id IS NOT NULL))
        ), inventory AS (
          SELECT product_id,variant_id,sum(qty_on_hand) on_hand,sum(qty_reserved) reserved
          FROM stock_balances WHERE company_id=:company AND branch_id=:branch
            AND location_id=ANY(CAST(:locations AS uuid[])) GROUP BY product_id,variant_id
        ), sales AS (
          SELECT i.product_id,i.variant_id,sum(i.qty) sold,sum(i.subtotal) line_subtotal
          FROM sale_order_items i JOIN sale_orders o ON o.id=i.order_id AND o.company_id=i.company_id
          WHERE o.company_id=:company AND o.branch_id=:branch AND o.location_id=ANY(CAST(:locations AS uuid[]))
            AND o.status IN ('completed','partially_refunded','refunded') AND o.created_at>=:start AND o.created_at<:end
          GROUP BY i.product_id,i.variant_id
        ), returns AS (
          SELECT i.product_id,i.variant_id,sum(i.quantity) returned,sum(i.total_amount) refund_amount
          FROM refund_operation_items i JOIN refund_operations r ON r.id=i.operation_id
          JOIN sale_orders o ON o.id=r.order_id AND o.company_id=r.company_id
          WHERE r.company_id=:company AND r.branch_id=:branch AND o.location_id=ANY(CAST(:locations AS uuid[]))
            AND r.finalized_at>=:start AND r.finalized_at<:end AND r.status='completed'
          GROUP BY i.product_id,i.variant_id
        ), transit AS (
          SELECT i.product_id,i.variant_id,
            sum(CASE WHEN o.to_branch_id=:branch THEN greatest(COALESCE(i.qty_sent,0)-COALESCE(i.qty_received,0)-i.qty_discrepancy,0) ELSE 0 END) incoming,
            sum(CASE WHEN o.from_branch_id=:branch THEN greatest(COALESCE(i.qty_sent,0)-COALESCE(i.qty_received,0)-i.qty_discrepancy,0) ELSE 0 END) outgoing
          FROM transfer_order_items i JOIN transfer_orders o ON o.id=i.to_id AND o.company_id=i.company_id
          JOIN retail_transfer_scopes s ON s.order_id=o.id AND s.company_id=o.company_id
          WHERE o.company_id=:company AND s.brand_id=:brand AND o.status IN ('in_transit','partially_received')
            AND ((o.to_branch_id=:branch AND o.to_location_id=ANY(CAST(:locations AS uuid[]))) OR
                 (o.from_branch_id=:branch AND o.from_location_id=ANY(CAST(:locations AS uuid[]))))
          GROUP BY i.product_id,i.variant_id
        )
        SELECT c.*,COALESCE(b.on_hand,0) on_hand,COALESCE(b.reserved,0) reserved,
          COALESCE(b.on_hand,0)-COALESCE(b.reserved,0) available,
          COALESCE(s.sold,0) sold,COALESCE(s.line_subtotal,0) line_subtotal,
          COALESCE(r.returned,0) returned,COALESCE(r.refund_amount,0) refund_amount,
          COALESCE(s.sold,0)-COALESCE(r.returned,0) net_quantity,
          COALESCE(t.incoming,0) incoming,COALESCE(t.outgoing,0) outgoing,count(*) OVER() total_count
        FROM catalog c LEFT JOIN inventory b ON b.product_id=c.product_id AND b.variant_id IS NOT DISTINCT FROM c.variant_id
        LEFT JOIN sales s ON s.product_id=c.product_id AND s.variant_id IS NOT DISTINCT FROM c.variant_id
        LEFT JOIN returns r ON r.product_id=c.product_id AND r.variant_id IS NOT DISTINCT FROM c.variant_id
        LEFT JOIN transit t ON t.product_id=c.product_id AND t.variant_id IS NOT DISTINCT FROM c.variant_id
        WHERE c.product_name ILIKE :search OR c.sku ILIKE :search OR c.barcode ILIKE :search
          OR c.product_brand_name ILIKE :search OR c.variant_name ILIKE :search
        ORDER BY c.product_name,c.sku,c.product_id,c.variant_id LIMIT 100 OFFSET :offset
    """),params)
    rows=[dict(row) for row in result.mappings()]
    return ok(dict(rows=rows,page=page,total=rows[0]["total_count"] if rows else 0,
        branch_id=current.branch_id,brand_id=current.brand_id,start=start,end=end,
        generated_at=datetime.now(timezone.utc),timezone="Asia/Bangkok"))
