from typing import Literal
from fastapi import APIRouter, Depends, Query, Response
from app.dependencies import TokenData, require_permission
from app.services.debt_aging_service import report

router = APIRouter(prefix="/api/v1/company/debt-aging", tags=["debt-aging"])


@router.get("")
async def aging(response: Response, side: Literal["payable", "receivable"],
    search: str = Query("", max_length=100),
    window: Literal["all", "overdue", "today", "next7", "next30"] = "all",
    bucket: Literal["all", "not_due", "due_today", "days_1_30", "days_31_60", "days_61_90", "days_91_plus"] = "all",
    page: int = Query(1, ge=1, le=10000), limit: int = Query(25, ge=1, le=100),
    current: TokenData = Depends(require_permission("accounting.report.view")),
):
    response.headers["Cache-Control"] = "private, no-store"
    return {"data": await report(current, side, search=search, window=window, bucket=bucket, page=page, limit=limit), "error": None}
