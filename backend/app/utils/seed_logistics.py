from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.logistics import Carrier, ShippingRate

DEFAULT_CARRIERS = [
    {
        "code": "THPOST",
        "name": "ไปรษณีย์ไทย",
        "name_en": "Thailand Post",
        "tracking_url": "https://track.thailandpost.co.th/?barcode={tracking_no}",
        "is_cod": True,
        "sort_order": 1,
    },
    {
        "code": "FLASH",
        "name": "Flash Express",
        "name_en": "Flash Express",
        "tracking_url": "https://www.flashexpress.co.th/tracking/?se={tracking_no}",
        "is_cod": True,
        "sort_order": 2,
    },
    {
        "code": "JT",
        "name": "J&T Express",
        "name_en": "J&T Express",
        "tracking_url": "https://www.jtexpress.co.th/trajectoryQuery?billCode={tracking_no}",
        "is_cod": True,
        "sort_order": 3,
    },
    {
        "code": "KERRY",
        "name": "Kerry Express",
        "name_en": "Kerry Express",
        "tracking_url": "https://th.kerryexpress.com/th/track/?track={tracking_no}",
        "is_cod": True,
        "sort_order": 4,
    },
]

DEFAULT_SHIPPING_RATES = [
    {"carrier_code": "THPOST", "service_name": "EMS", "zone": "all", "min_weight_g": 0, "max_weight_g": 500, "base_rate": Decimal("50"), "per_kg_rate": Decimal("0"), "cod_fee": Decimal("0")},
    {"carrier_code": "THPOST", "service_name": "EMS", "zone": "all", "min_weight_g": 501, "max_weight_g": 1000, "base_rate": Decimal("70"), "per_kg_rate": Decimal("0"), "cod_fee": Decimal("0")},
    {"carrier_code": "THPOST", "service_name": "EMS", "zone": "all", "min_weight_g": 1001, "max_weight_g": None, "base_rate": Decimal("70"), "per_kg_rate": Decimal("25"), "cod_fee": Decimal("0")},
    {"carrier_code": "FLASH", "service_name": "Flash Standard", "zone": "bangkok", "min_weight_g": 0, "max_weight_g": None, "base_rate": Decimal("35"), "per_kg_rate": Decimal("0"), "cod_fee": Decimal("20")},
    {"carrier_code": "FLASH", "service_name": "Flash Standard", "zone": "all", "min_weight_g": 0, "max_weight_g": None, "base_rate": Decimal("45"), "per_kg_rate": Decimal("0"), "cod_fee": Decimal("25")},
    {"carrier_code": "JT", "service_name": "J&T Standard", "zone": "all", "min_weight_g": 0, "max_weight_g": None, "base_rate": Decimal("40"), "per_kg_rate": Decimal("0"), "cod_fee": Decimal("20")},
    {"carrier_code": "KERRY", "service_name": "Kerry Standard", "zone": "all", "min_weight_g": 0, "max_weight_g": None, "base_rate": Decimal("48"), "per_kg_rate": Decimal("0"), "cod_fee": Decimal("20")},
]


async def seed_default_carriers(db: AsyncSession, company_id: UUID) -> None:
    values = [{**row, "company_id": company_id} for row in DEFAULT_CARRIERS]
    if not values:
        return
    statement = insert(Carrier).values(values)
    statement = statement.on_conflict_do_nothing(constraint="uq_carriers_company_id_code")
    await db.execute(statement)
    await db.flush()


async def seed_default_shipping_rates(db: AsyncSession, company_id: UUID) -> None:
    carriers = (
        await db.scalars(select(Carrier).where(Carrier.company_id == company_id))
    ).all()
    carrier_by_code = {carrier.code: carrier for carrier in carriers}

    for row in DEFAULT_SHIPPING_RATES:
        carrier = carrier_by_code.get(row["carrier_code"])
        if carrier is None:
            continue
        exists = await db.scalar(
            select(ShippingRate.id).where(
                ShippingRate.company_id == company_id,
                ShippingRate.carrier_id == carrier.id,
                ShippingRate.service_name == row["service_name"],
                ShippingRate.zone == row["zone"],
                ShippingRate.min_weight_g == row["min_weight_g"],
                ShippingRate.max_weight_g.is_(row["max_weight_g"]) if row["max_weight_g"] is None else ShippingRate.max_weight_g == row["max_weight_g"],
            )
        )
        if exists is not None:
            continue
        db.add(
            ShippingRate(
                company_id=company_id,
                carrier_id=carrier.id,
                service_name=row["service_name"],
                zone=row["zone"],
                min_weight_g=row["min_weight_g"],
                max_weight_g=row["max_weight_g"],
                base_rate=row["base_rate"],
                per_kg_rate=row["per_kg_rate"],
                cod_fee=row["cod_fee"],
                is_active=True,
            )
        )
    await db.flush()
