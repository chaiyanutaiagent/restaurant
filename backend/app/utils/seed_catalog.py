from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import PriceList, Unit
from app.models.stock import StockLocation


DEFAULT_UNITS = [
    {"code": "PCS", "name": "ชิ้น", "name_en": "Piece", "decimal_places": 0},
    {"code": "BOX", "name": "กล่อง", "name_en": "Box", "decimal_places": 0},
    {"code": "KG", "name": "กิโลกรัม", "name_en": "Kilogram", "decimal_places": 3},
    {"code": "G", "name": "กรัม", "name_en": "Gram", "decimal_places": 2},
    {"code": "L", "name": "ลิตร", "name_en": "Liter", "decimal_places": 3},
    {"code": "ML", "name": "มิลลิลิตร", "name_en": "Milliliter", "decimal_places": 2},
    {"code": "M", "name": "เมตร", "name_en": "Meter", "decimal_places": 2},
    {"code": "SET", "name": "ชุด", "name_en": "Set", "decimal_places": 0},
]


async def seed_default_catalog(db: AsyncSession, company_id: uuid.UUID) -> None:
    unit_exists = await db.scalar(
        select(Unit.id).where(Unit.company_id == company_id, Unit.deleted_at.is_(None)).limit(1)
    )
    if unit_exists is None:
        for item in DEFAULT_UNITS:
            db.add(Unit(company_id=company_id, **item))

    price_list_exists = await db.scalar(
        select(PriceList.id).where(
            PriceList.company_id == company_id,
            PriceList.deleted_at.is_(None),
        ).limit(1)
    )
    if price_list_exists is None:
        db.add(
            PriceList(
                company_id=company_id,
                name="ราคาปลีก",
                is_default=True,
                currency="THB",
                is_active=True,
            )
        )


async def seed_default_stock_location(
    db: AsyncSession, company_id: uuid.UUID, branch_id: uuid.UUID
) -> StockLocation:
    location = await db.scalar(
        select(StockLocation).where(
            StockLocation.company_id == company_id,
            StockLocation.branch_id == branch_id,
            StockLocation.code == "MAIN",
            StockLocation.deleted_at.is_(None),
        )
    )
    if location is not None:
        return location

    location = StockLocation(
        company_id=company_id,
        branch_id=branch_id,
        code="MAIN",
        name="คลังหลัก",
        is_active=True,
    )
    db.add(location)
    await db.flush()
    return location
