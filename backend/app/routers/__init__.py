from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
api_router = APIRouter(prefix="/api/v1", tags=["system"])


@api_router.get("/ping")
async def ping() -> dict[str, str]:
    return {"message": "pong"}


router.include_router(api_router)
