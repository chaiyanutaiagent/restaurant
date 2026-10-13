import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import TokenData, get_legacy_model_operational_db, require_permission
from app.routers.products import ok
from app.schemas.retail_transfer import RetailTransferCreate, RetailTransferCommand
from app.services.retail_transfer_service import RetailTransferService

router=APIRouter(prefix="/api/v1/retail/transfers",tags=["retail-transfers"])


def service(current:TokenData=Depends(require_permission("inventory.transfer.view")),db:AsyncSession=Depends(get_legacy_model_operational_db)):
    return RetailTransferService(db,current)


@router.get("/options")
async def options(s=Depends(service)):
    return ok(await s.options())


@router.get("/stock")
async def stock(source_id:uuid.UUID,search:str=Query(default="",max_length=150),s=Depends(service)):
    return ok(await s.stock(source_id,search.strip()))


@router.get("")
async def listing(page:int=Query(default=1,ge=1),s=Depends(service)):
    return ok(await s.listing(page))


@router.post("",status_code=201)
async def create(payload:RetailTransferCreate,s=Depends(service)):
    return ok(await s.request(payload))


@router.get("/{order_id}")
async def read(order_id:uuid.UUID,s=Depends(service)):
    return ok(await s.read(order_id))


@router.post("/{order_id}/commands")
async def command(order_id:uuid.UUID,payload:RetailTransferCommand,s=Depends(service)):
    return ok(await s.request(payload,order_id))
