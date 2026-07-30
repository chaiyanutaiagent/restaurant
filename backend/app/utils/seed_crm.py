from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import CustomerTier, LoyaltySettings

DEFAULT_TIERS: list[dict[str, object]] = [
    {"name": "Bronze", "name_th": "บรอนซ์", "min_lifetime_spend": 0, "points_multiplier": 1.0, "color": "#CD7F32", "sort_order": 1},
    {"name": "Silver", "name_th": "ซิลเวอร์", "min_lifetime_spend": 5000, "points_multiplier": 1.25, "color": "#C0C0C0", "sort_order": 2},
    {"name": "Gold", "name_th": "ทอง", "min_lifetime_spend": 15000, "points_multiplier": 1.5, "color": "#FFD700", "sort_order": 3},
    {"name": "Platinum", "name_th": "แพลทินัม", "min_lifetime_spend": 50000, "points_multiplier": 2.0, "color": "#E5E4E2", "sort_order": 4},
]


async def seed_default_tiers(db: AsyncSession, company_id: uuid.UUID) -> None:
    values = [{"company_id": company_id, "is_active": True, **tier} for tier in DEFAULT_TIERS]
    statement = insert(CustomerTier).values(values)
    statement = statement.on_conflict_do_nothing(index_elements=["company_id", "name"])
    await db.execute(statement)


async def seed_loyalty_settings(db: AsyncSession, company_id: uuid.UUID) -> None:
    existing = await db.scalar(select(LoyaltySettings.id).where(LoyaltySettings.company_id == company_id))
    if existing is not None:
        return
    db.add(
        LoyaltySettings(
            company_id=company_id,
            earn_rate=0.1,
            earn_min_spend=0,
            redeem_rate=0.1,
            redeem_min_points=100,
            redeem_max_pct=100,
            points_expiry_months=12,
            enabled=True,
            require_phone=True,
        )
    )
