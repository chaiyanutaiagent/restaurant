from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import func

from app.database import AsyncSessionLocal
from app.main import app
from app.models.branch import Branch
from app.models.product import Product


DATABASE_PREFIX = "restaurant_saas_routing_"
PASSWORD = "Routing-Owner-Password!"
BUSINESSES = (
    ("alpha-cafe", "Alpha Cafe", "alpha.owner@example.com", "alpha.owner", "ALPHA-COFFEE"),
    ("beta-bistro", "Beta Bistro", "beta.owner@example.com", "beta.owner", "BETA-PASTA"),
)


def expect(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    if expected >= 400:
        return response.json()
    return response.json()["data"]


async def prepare_catalog(company_ids: dict[str, str]) -> None:
    configured = os.environ.get("SAAS_ROUTING_DATABASE_NAME", "")
    if not configured.startswith(DATABASE_PREFIX):
        raise RuntimeError("Tenant routing smoke refuses to write a non-isolated database")
    async with AsyncSessionLocal() as db:
        if await db.scalar(func.current_database()) != configured:
            raise RuntimeError("Tenant routing smoke database mismatch")
        for index, (slug, name, _email, _username, sku) in enumerate(BUSINESSES, start=1):
            company_id = uuid.UUID(company_ids[slug])
            db.add(
                Branch(
                    company_id=company_id,
                    code=f"R{index}",
                    name=f"{name} Branch",
                    is_active=True,
                    is_warehouse=False,
                )
            )
            db.add(
                Product(
                    company_id=company_id,
                    sku=sku,
                    name=f"{name} Product",
                    selling_price=100 + index,
                    is_active=True,
                    is_for_sale=True,
                )
            )
        await db.commit()


def main() -> None:
    delivered: list[tuple[str, str, str]] = []

    async def capture_email(*, recipient: str, purpose: str, token: str) -> bool:
        delivered.append((recipient, purpose, token))
        return True

    with (
        patch(
            "app.routers.membership.deliver_membership_email",
            new=AsyncMock(side_effect=capture_email),
        ),
        patch(
            "app.routers.membership.check_public_rate_limit",
            new=AsyncMock(return_value=True),
        ),
        TestClient(app) as client,
    ):
        company_ids: dict[str, str] = {}
        for slug, name, email, username, _sku in BUSINESSES:
            signup = expect(
                client.post(
                    "/api/v1/membership/signup",
                    json={
                        "company_name": name,
                        "business_slug": slug,
                        "owner_display_name": f"{name} Owner",
                        "owner_email": email,
                        "username": username,
                        "password": PASSWORD,
                        "terms_accepted": True,
                        "privacy_accepted": True,
                    },
                ),
                201,
                f"Signup {slug}",
            )
            if signup["business_slug"] != slug:
                raise RuntimeError("Signup did not return the canonical business slug")
            company_ids[slug] = signup["company_id"]

        expect(
            client.post(
                "/api/v1/membership/signup",
                json={
                    "company_name": "Slug Collision",
                    "business_slug": BUSINESSES[0][0],
                    "owner_display_name": "Collision Owner",
                    "owner_email": "collision@example.com",
                    "username": "collision.owner",
                    "password": PASSWORD,
                    "terms_accepted": True,
                    "privacy_accepted": True,
                },
            ),
            409,
            "Duplicate business slug",
        )
        expect(
            client.post(
                "/api/v1/membership/signup",
                json={
                    "company_name": "Reserved Route",
                    "business_slug": "platform",
                    "owner_display_name": "Reserved Owner",
                    "owner_email": "reserved@example.com",
                    "username": "reserved.owner",
                    "password": PASSWORD,
                    "terms_accepted": True,
                    "privacy_accepted": True,
                },
            ),
            422,
            "Reserved business slug",
        )

        client.portal.call(prepare_catalog, company_ids)
        for slug, name, _email, _username, sku in BUSINESSES:
            business = expect(
                client.get(f"/api/v1/membership/businesses/{slug}"),
                200,
                f"Public business resolver {slug}",
            )
            if business != {
                "company_id": company_ids[slug],
                "business_slug": slug,
                "name": name,
                "logo_url": None,
            }:
                raise RuntimeError("Public business resolver returned unexpected fields")
            summary = expect(
                client.get(f"/api/public/storefront/businesses/{slug}"),
                200,
                f"Storefront summary {slug}",
            )
            if summary["company"]["business_slug"] != slug or summary["company"]["name"] != name:
                raise RuntimeError("Storefront summary crossed the Company boundary")
            products = expect(
                client.get(f"/api/public/storefront/businesses/{slug}/products"),
                200,
                f"Storefront products {slug}",
            )
            if [item["sku"] for item in products] != [sku]:
                raise RuntimeError("Slug storefront exposed another Tenant's product")
            branches = expect(
                client.get(f"/api/public/storefront/businesses/{slug}/branches"),
                200,
                f"Storefront branches {slug}",
            )
            if len(branches) != 1 or name not in branches[0]["name"]:
                raise RuntimeError("Slug storefront exposed another Tenant's branch")

        expect(client.get("/api/v1/membership/businesses/missing-business"), 404, "Unknown business")
        expect(client.get("/api/public/storefront/businesses/missing-business"), 404, "Unknown storefront")

        verification_token = next(token for email, purpose, token in delivered if email == BUSINESSES[0][2] and purpose == "verify_email")
        expect(
            client.post("/api/v1/membership/verification/confirm", json={"token": verification_token}),
            200,
            "Verify slug owner",
        )
        login = expect(
            client.post(
                "/api/v1/auth/login",
                headers={"X-Company-ID": company_ids[BUSINESSES[0][0]]},
                json={"username": BUSINESSES[0][3], "password": PASSWORD},
            ),
            200,
            "Slug owner login",
        )
        if login["business_slug"] != BUSINESSES[0][0]:
            raise RuntimeError("Login session did not bind the canonical business slug")

    print("SaaS Tenant business-slug routing API smoke passed")


if __name__ == "__main__":
    main()
