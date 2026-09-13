from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.main import app
from app.models.audit import AuditLog
from app.models.branch import Branch
from app.models.company import Company
from app.models.platform import PlatformTenantProfile
from app.models.restaurant import Brand, BrandBranch
from app.models.user import User
from app.utils.security import hash_password


DATABASE_PREFIX = "restaurant_wp3_workspace_"
OWNER_PASSWORD = "WP3-Company-Owner-Password!"


def expect(response, expected: int, label: str):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    if expected >= 400:
        return response.json()
    return response.json()["data"]


async def seed_companies() -> tuple[uuid.UUID, uuid.UUID]:
    configured_database = os.environ.get("WP3_WORKSPACE_DATABASE_NAME", "")
    if not configured_database.startswith(DATABASE_PREFIX):
        raise RuntimeError("WP3 workspace smoke refuses to write a non-isolated database")
    async with AsyncSessionLocal() as db:
        actual_database = await db.scalar(func.current_database())
        if actual_database != configured_database:
            raise RuntimeError(
                f"WP3 workspace database mismatch: {actual_database} != {configured_database}"
            )
        marker = uuid.uuid4().hex[:8]
        company = Company(
            name="WP3 Workspace Company",
            business_slug=f"wp3-workspace-{marker}",
            is_active=True,
        )
        foreign_company = Company(
            name="WP3 Foreign Company",
            business_slug=f"wp3-foreign-{marker}",
            is_active=True,
        )
        db.add_all([company, foreign_company])
        await db.flush()
        db.add_all([
            PlatformTenantProfile(
                company_id=company.id,
                plan_code="starter",
                feature_flags={
                    "restaurant": True,
                    "restaurant_pos": True,
                    "takeaway": False,
                    "takeaway_pos": False,
                    "retail_pos": False,
                },
                plan_limits={"brands": 1, "branches": 1, "users": 10, "devices": 3},
                created_by=None,
            ),
            User(
                company_id=company.id,
                username="wp3.owner",
                display_name="WP3 Company Owner",
                hashed_password=hash_password(OWNER_PASSWORD),
                is_active=True,
                is_superuser=True,
            ),
            User(
                company_id=company.id,
                username="wp3.viewer",
                display_name="WP3 Viewer",
                hashed_password=hash_password(OWNER_PASSWORD),
                is_active=True,
                is_superuser=False,
            ),
            User(
                company_id=foreign_company.id,
                username="wp3.foreign",
                display_name="WP3 Foreign Owner",
                hashed_password=hash_password(OWNER_PASSWORD),
                is_active=True,
                is_superuser=True,
            ),
        ])
        await db.commit()
        return company.id, foreign_company.id


async def verify_evidence(
    company_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> None:
    async with AsyncSessionLocal() as db:
        brand_count = int(
            await db.scalar(
                select(func.count()).select_from(Brand).where(Brand.company_id == company_id)
            )
            or 0
        )
        branch_count = int(
            await db.scalar(
                select(func.count()).select_from(Branch).where(Branch.company_id == company_id)
            )
            or 0
        )
        link_count = int(
            await db.scalar(
                select(func.count()).select_from(BrandBranch).where(
                    BrandBranch.company_id == company_id
                )
            )
            or 0
        )
        actions = list(
            await db.scalars(
                select(AuditLog.action).where(
                    AuditLog.company_id == company_id,
                    AuditLog.resource_id.in_([
                        "wp3-provision-request-001",
                        "wp3-provision-request-002",
                        str(workspace_id),
                    ]),
                )
            )
        )
        if (brand_count, branch_count, link_count) != (1, 1, 1):
            raise RuntimeError(
                f"Workspace idempotency counts failed: {brand_count}/{branch_count}/{link_count}"
            )
        required_actions = {
            "company.workspace.provision",
            "company.workspace.deactivate",
            "company.workspace.reactivate",
        }
        if not required_actions.issubset(set(actions)):
            raise RuntimeError(f"Workspace audit evidence is incomplete: {actions}")


def login(client: TestClient, company_id: uuid.UUID, username: str) -> dict:
    return expect(
        client.post(
            "/api/v1/auth/login",
            headers={"X-Company-ID": str(company_id)},
            json={"username": username, "password": OWNER_PASSWORD},
        ),
        200,
        f"login {username}",
    )


def main() -> None:
    with TestClient(app) as client:
        company_id, foreign_company_id = client.portal.call(seed_companies)
        owner = login(client, company_id, "wp3.owner")
        foreign = login(client, foreign_company_id, "wp3.foreign")
        viewer = login(client, company_id, "wp3.viewer")
        owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
        foreign_headers = {"Authorization": f"Bearer {foreign['access_token']}"}
        viewer_headers = {"Authorization": f"Bearer {viewer['access_token']}"}

        directory = expect(
            client.get("/api/v1/membership/workspaces", headers=owner_headers),
            200,
            "empty Company workspace directory",
        )
        module_by_key = {row["module_key"]: row for row in directory["modules"]}
        if not module_by_key["restaurant_pos"]["can_provision"]:
            raise RuntimeError("Restaurant workspace is not provisionable for the active Company")
        if module_by_key["takeaway_pos"]["can_provision"]:
            raise RuntimeError("Takeaway dark launch escaped its Company/plan gate")
        if module_by_key["hotel_pms"]["access"]["reason_code"] != "lifecycle_planned":
            raise RuntimeError("Hotel planned lifecycle is not preserved")
        expect(
            client.get("/api/v1/membership/workspaces", headers=viewer_headers),
            403,
            "workspace management permission",
        )

        payload = {
            "idempotency_key": "wp3-provision-request-001",
            "module_key": "restaurant_pos",
            "brand_slug": "wp3-sample-cafe",
            "brand_name": "WP3 Sample Cafe",
            "branch_code": "WP3-BKK-01",
            "branch_name": "WP3 Main Branch",
            "branch_type": "company_owned",
            "storefront_mode": "food_stall",
        }
        forbidden = {**payload, "target_database": "takeaway"}
        expect(
            client.post(
                "/api/v1/membership/workspaces",
                headers=owner_headers,
                json=forbidden,
            ),
            422,
            "client-selected target database",
        )
        created = expect(
            client.post(
                "/api/v1/membership/workspaces",
                headers=owner_headers,
                json=payload,
            ),
            200,
            "Restaurant workspace provisioning",
        )
        if not created["created"] or set(created["created_resources"]) != {
            "brand",
            "branch",
            "workspace",
        }:
            raise RuntimeError(f"Initial provisioning evidence is incomplete: {created}")
        workspace = created["workspace"]
        workspace_id = uuid.UUID(workspace["workspace_id"])
        if "target_database" in workspace or workspace["business_type"] != "restaurant":
            raise RuntimeError("Workspace API exposed or accepted an unsafe database target")

        replay = expect(
            client.post(
                "/api/v1/membership/workspaces",
                headers=owner_headers,
                json=payload,
            ),
            200,
            "same-key idempotent replay",
        )
        if replay["created"] or replay["workspace"]["workspace_id"] != str(workspace_id):
            raise RuntimeError("Same-key replay created a duplicate workspace")
        expect(
            client.post(
                "/api/v1/membership/workspaces",
                headers=owner_headers,
                json={**payload, "branch_name": "Different Branch"},
            ),
            409,
            "same-key payload conflict",
        )
        natural_replay = expect(
            client.post(
                "/api/v1/membership/workspaces",
                headers=owner_headers,
                json={**payload, "idempotency_key": "wp3-provision-request-002"},
            ),
            200,
            "natural-key idempotent replay",
        )
        if natural_replay["created"]:
            raise RuntimeError("Natural workspace identity created a duplicate")
        expect(
            client.post(
                "/api/v1/membership/workspaces",
                headers=owner_headers,
                json={
                    **payload,
                    "idempotency_key": "wp3-provision-request-003",
                    "brand_slug": "second-brand",
                    "brand_name": "Second Brand",
                    "branch_code": "WP3-BKK-02",
                    "branch_name": "Second Branch",
                },
            ),
            409,
            "Company plan workspace limit",
        )
        expect(
            client.post(
                "/api/v1/membership/workspaces",
                headers=owner_headers,
                json={**payload, "idempotency_key": "wp3-takeaway-001", "module_key": "takeaway_pos"},
            ),
            403,
            "Takeaway dark launch gate",
        )

        expect(
            client.patch(
                f"/api/v1/membership/workspaces/{workspace_id}",
                headers=foreign_headers,
                json={"active": False, "reason": "foreign tenant attempt"},
            ),
            404,
            "cross-tenant workspace mutation",
        )
        paused = expect(
            client.patch(
                f"/api/v1/membership/workspaces/{workspace_id}",
                headers=owner_headers,
                json={"active": False, "reason": "WP3 rollback rehearsal"},
            ),
            200,
            "workspace deactivate",
        )
        if paused["is_active"] or paused["can_open"]:
            raise RuntimeError("Deactivated workspace remains open")
        restored = expect(
            client.patch(
                f"/api/v1/membership/workspaces/{workspace_id}",
                headers=owner_headers,
                json={"active": True, "reason": "WP3 restore rehearsal"},
            ),
            200,
            "workspace reactivate",
        )
        if not restored["is_active"] or not restored["can_open"]:
            raise RuntimeError("Reactivated workspace did not become available")

        final_directory = expect(
            client.get("/api/v1/membership/workspaces", headers=owner_headers),
            200,
            "populated Company workspace directory",
        )
        restaurant_rows = next(
            row for row in final_directory["modules"] if row["module_key"] == "restaurant_pos"
        )["workspaces"]
        if len(restaurant_rows) != 1 or restaurant_rows[0]["workspace_id"] != str(workspace_id):
            raise RuntimeError("Directory does not return the canonical Restaurant workspace")

        client.portal.call(verify_evidence, company_id, workspace_id)
        print(
            "wp3_company_workspace_api=ok "
            f"company={company_id} workspace={workspace_id} "
            "tenant_isolation=ok idempotency=ok audit=ok module_gates=ok"
        )


if __name__ == "__main__":
    main()
