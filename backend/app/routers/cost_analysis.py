from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, Query, Response
from app.dependencies import TokenData, require_permission
from app.services.cost_analysis_service import report

router = APIRouter(prefix="/api/v1/company/cost-analysis", tags=["cost-analysis"])

@router.get("")
async def cost_analysis(response: Response, start: date, end: date,
    fixed_cost: Decimal = Query(Decimal(0), ge=0, le=999999999999, decimal_places=2),
    variable_pct: Decimal = Query(Decimal(0), ge=0, le=100, decimal_places=4),
    target_sales: Decimal = Query(Decimal(0), ge=0, le=999999999999, decimal_places=2),
    current: TokenData = Depends(require_permission("accounting.report.view")),
):
    response.headers["Cache-Control"] = "private, no-store"
    return {"data": await report(current, start, end, fixed_cost=fixed_cost,
        variable_pct=variable_pct, target_sales=target_sales), "error": None}
