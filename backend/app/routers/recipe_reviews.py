from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from app.database import get_db, active_identity_session_factory
from app.dependencies import TokenData, require_any_permission
from app.models.restaurant import Brand, BrandBranch
from app.models.branch import Branch
from app.models.recipe_review import RecipeReview
from app.schemas.recipe_review import ReviewCreate, ReviewAction
from app.services import recipe_review_service as service

router=APIRouter(prefix="/api/v1/company/recipe-reviews",tags=["recipe-reviews"])
actor=Depends(require_any_permission("fb.recipe.manage","takeaway.production.manage","company.kitchen.manage"))

@router.get("/options")
async def options(response:Response,current:TokenData=actor):
    response.headers["Cache-Control"]="private, no-store"
    systems=[s for s,p in service.PERMISSIONS.items() if service.can_manage(current) or p in current.permissions]
    if not systems: service.access(current,"restaurant")
    service.access(current,systems[0])
    async with active_identity_session_factory()() as db:
        q=select(Brand).where(Brand.company_id==current.company_id,Brand.is_active.is_(True),Brand.business_type.in_(systems))
        if not service.can_manage(current): q=q.where(Brand.id==current.brand_id)
        brands=(await db.scalars(q.order_by(Brand.name))).all()
        bq=select(BrandBranch.brand_id,Branch.id,Branch.code,Branch.name).join(Branch,Branch.id==BrandBranch.branch_id).where(
            BrandBranch.company_id==current.company_id,Branch.company_id==current.company_id,
            BrandBranch.brand_id.in_([b.id for b in brands]),BrandBranch.is_active.is_(True),Branch.deleted_at.is_(None),Branch.is_active.is_(True))
        if not service.can_manage(current): bq=bq.where(Branch.id==current.branch_id)
        branches=(await db.execute(bq)).mappings().all()
    return {"data":{"company_id":current.company_id,"manager":service.can_manage(current),
        "brands":[{"id":b.id,"name":b.name,"system":b.business_type} for b in brands],
        "branches":[dict(b) for b in branches],"activation":"held","source_writes":False},"error":None}

@router.get("/sources")
async def sources(response:Response,system:Literal["restaurant","takeaway"],brand_id:UUID,
    search:str=Query("",max_length=100),current:TokenData=actor):
    response.headers["Cache-Control"]="private, no-store"
    return {"data":await service.sources(current,system,brand_id,search=search),"error":None}

@router.get("/catalog")
async def catalog(response:Response,system:Literal["restaurant","takeaway"],brand_id:UUID,
    search:str=Query("",max_length=100),current:TokenData=actor):
    response.headers["Cache-Control"]="private, no-store"
    return {"data":await service.catalog(current,system,brand_id,search=search),"error":None}

@router.get("")
async def listing(response:Response,system:Literal["restaurant","takeaway"],brand_id:UUID,
    state:Literal["all","draft","submitted","returned","rejected","approved_hold"]="all",
    page:int=Query(1,ge=1,le=10000),current:TokenData=actor,db=Depends(get_db)):
    response.headers["Cache-Control"]="private, no-store"
    await service.scope(current,system,brand_id)
    q=service.visible(current).where(RecipeReview.system==system,RecipeReview.brand_id==brand_id)
    if state!="all": q=q.where(RecipeReview.status==state)
    rows=(await db.scalars(q.order_by(RecipeReview.updated_at.desc(),RecipeReview.id).offset((page-1)*25).limit(26))).all()
    return {"data":{"items":[service.serial(r) for r in rows[:25]],"has_more":len(rows)>25},"error":None}

@router.post("",status_code=201)
async def create(payload:ReviewCreate,current:TokenData=actor,db=Depends(get_db)):
    return {"data":await service.create(db,current,payload),"error":None}

@router.post("/{id}/actions")
async def action(id:UUID,payload:ReviewAction,current:TokenData=actor,db=Depends(get_db)):
    return {"data":await service.act(db,current,id,payload),"error":None}
