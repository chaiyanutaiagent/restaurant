"""Onboarding issues only product-specific sessions, including for multi-store owners."""
from __future__ import annotations

from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_identity_db, get_db
from app.dependencies import TokenData, get_current_user, require_permission
from app.services.crm_service import CRMService
from app.schemas.crm import CustomerSearchResult
from app.models.branch import Branch
from app.routers.auth import _token_response, ok
from app.routers.mobile_store_auth import StoreCredentials, StoreLogin, authenticate
from app.services.mobile_pos_policy import pos_permissions, POS_SURFACES
from app.services.mobile_store_policy import MOBILE_STORE_SURFACE, store_permissions

router = APIRouter(prefix="/api/v1/mobile-pos", tags=["mobile-pos"])
SURFACES = {"restaurant": "restaurant_pos", "retail_pos": "retail_pos", "takeaway": MOBILE_STORE_SURFACE}

@router.get("/customers/search")
async def customers(q: str = Query(min_length=3), limit: int = Query(default=10, ge=1, le=50),
    current: TokenData = Depends(require_permission("pos.sale.view")), db: AsyncSession = Depends(get_db)):
    if current.client_surface not in POS_SURFACES:
        raise HTTPException(403, "Native POS session required")
    rows = await CRMService(db).search_customers(current.company_id, q, limit)
    return ok([CustomerSearchResult.model_validate(row).model_dump() for row in rows])

class PosCredentials(StoreCredentials):
    product: Literal["restaurant", "retail_pos", "takeaway"]

class PosLogin(StoreLogin):
    product: Literal["restaurant", "retail_pos", "takeaway"]

def allowed(payload, user, context, permissions):
    args = dict(user=user, context=context, permissions=permissions, device_id=str(payload.device_id))
    if payload.product == "takeaway":
        return store_permissions(**args)
    return pos_permissions(surface=SURFACES[payload.product], **args)

@router.post("/branches")
async def branches(payload: PosCredentials, request: Request, db: AsyncSession = Depends(get_identity_db)):
    company, user, service = await authenticate(payload, request, db)
    candidates = (await db.scalars(select(Branch).where(Branch.company_id == company.id,
        Branch.is_active.is_(True), Branch.deleted_at.is_(None)).order_by(Branch.code))).all()
    result = []
    for branch in candidates:
        try:
            permissions, _, context, _, _, _ = await service.get_user_permissions(user, branch.id, payload.station_key)
            allowed(payload, user, context, permissions)
        except HTTPException as exc:
            if exc.status_code in {400, 403, 404, 409}:
                continue
            raise
        result.append({"id": str(branch.id), "code": branch.code, "name": branch.name, "product": payload.product})
    if not result:
        raise HTTPException(403, "No assigned branch for this POS product")
    return ok(result)

@router.post("/login")
async def login(payload: PosLogin, request: Request, db: AsyncSession = Depends(get_identity_db)):
    _, user, service = await authenticate(payload, request, db)
    tokens = await service.create_session(user=user, branch_id=payload.branch_id, station_key=payload.station_key,
        ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"),
        client_surface=SURFACES[payload.product], store_device_id=str(payload.device_id))
    return ok((await _token_response(*tokens, user, db)).model_dump())

@router.get("/context")
async def context(current: TokenData = Depends(get_current_user), db: AsyncSession = Depends(get_identity_db)):
    if current.client_surface not in POS_SURFACES:
        raise HTTPException(403, "Native POS session required")
    branch = await db.get(Branch, current.branch_id)
    if branch is None or branch.company_id != current.company_id:
        raise HTTPException(403, "Branch unavailable")
    return ok([{"branch_id": str(branch.id), "branch_code": branch.code, "branch_name": branch.name,
        "is_default": True, "role_name": "POS", "business_type": current.business_type,
        "target_database": current.target_database, "station_key": current.station_key}])
