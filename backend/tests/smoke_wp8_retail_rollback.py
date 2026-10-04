from __future__ import annotations

import asyncio
from decimal import Decimal
import os

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.database import (
    AsyncSessionLocal,
    PlatformSessionLocal,
    engine,
    platform_engine,
    restaurant_engine,
    retail_engine,
)
from app.main import app
from app.models.company import Company
from app.models.product import Product
from app.models.restaurant import Brand, BrandBranch
from app.models.stock import StockBalance
from app.models.user import User


PROJECT_PREFIX = "restaurant-wp8-retail"
PASSWORD = os.environ.get("WP8_RETAIL_SMOKE_PASSWORD", "")


def expect(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    payload = response.json()
    return payload.get("data", payload)


async def discover() -> dict[str, str]:
    compose_project = os.environ.get("WP8_RETAIL_PROJECT_NAME", "")
    if not compose_project.startswith(PROJECT_PREFIX):
        raise RuntimeError("WP8 rollback smoke refuses to run outside its isolated project")
    if len(PASSWORD) < 16:
        raise RuntimeError(
            "WP8 rollback smoke requires a temporary password of at least 16 characters"
        )
    if settings.identity_database != "platform_core" or settings.retail_service_database != "legacy":
        raise RuntimeError("WP8 rollback smoke requires Platform identity and Legacy Retail routing")

    async with PlatformSessionLocal() as platform_db:
        company = await platform_db.scalar(
            select(Company).where(Company.business_slug.like("wp8-retail-%"))
        )
        if company is None:
            raise RuntimeError("WP8 rollback Company fixture is missing")
        brand = await platform_db.scalar(
            select(Brand).where(
                Brand.company_id == company.id,
                Brand.business_type == "retail_pos",
            )
        )
        user = await platform_db.scalar(
            select(User).where(
                User.company_id == company.id,
                User.username.like("wp8-retail-owner-%"),
            )
        )
        link = await platform_db.scalar(
            select(BrandBranch).where(BrandBranch.brand_id == brand.id)
        ) if brand is not None else None
        if brand is None or user is None or link is None:
            raise RuntimeError("WP8 rollback Platform fixture is incomplete")

    async with AsyncSessionLocal() as legacy_db:
        product = await legacy_db.scalar(
            select(Product).where(
                Product.company_id == company.id,
                Product.brand_id == brand.id,
            )
        )
        balance = await legacy_db.scalar(
            select(StockBalance).where(
                StockBalance.company_id == company.id,
                StockBalance.product_id == product.id,
            )
        ) if product is not None else None
        if product is None or balance is None or Decimal(balance.qty_on_hand) != Decimal("20"):
            raise RuntimeError("WP8 rollback source does not retain the untouched Legacy snapshot")
    return {
        "company_id": str(company.id),
        "branch_id": str(link.branch_id),
        "brand_id": str(brand.id),
        "username": user.username,
        "product_id": str(product.id),
        "barcode": str(product.barcode),
    }


def run() -> None:
    context = asyncio.run(discover())
    # The discovery loop and TestClient lifespan are separate event loops.
    for database_engine in (
        engine,
        platform_engine,
        restaurant_engine,
        retail_engine,
    ):
        if database_engine is not None:
            database_engine.sync_engine.dispose(close=False)
    with TestClient(app) as client:
        login = expect(
            client.post(
                "/api/v1/auth/login",
                json={
                    "company_id": context["company_id"],
                    "branch_id": context["branch_id"],
                    "username": context["username"],
                    "password": PASSWORD,
                },
            ),
            200,
            "rollback login",
        )
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        products = expect(
            client.get(f"/api/v1/products?search={context['barcode']}", headers=headers),
            200,
            "rollback barcode search",
        )
        if [row["id"] for row in products] != [context["product_id"]]:
            raise RuntimeError("Rollback route did not read the Legacy Retail product")
    print(
        "PASS: WP8 Retail rollback route "
        "identity=platform_core operational=legacy source_stock=20 barcode=passed"
    )


if __name__ == "__main__":
    run()
