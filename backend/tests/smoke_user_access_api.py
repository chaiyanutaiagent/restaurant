from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.utils.create_superuser import DEFAULT_COMPANY_ID


def expect_status(response, expected: int) -> dict:
    if response.status_code != expected:
        raise RuntimeError(
            f"Expected HTTP {expected}, got {response.status_code}: {response.text}"
        )
    return response.json()["data"]


def run() -> None:
    if not settings.default_admin_password:
        raise RuntimeError("DEFAULT_ADMIN_PASSWORD is required for API smoke test")
    marker = uuid.uuid4().hex[:8]
    with TestClient(app) as client:
        login = expect_status(
            client.post(
                "/api/v1/auth/login",
                json={
                    "company_id": str(DEFAULT_COMPANY_ID),
                    "username": "admin",
                    "password": settings.default_admin_password,
                },
            ),
            200,
        )
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        branches = expect_status(
            client.get("/api/v1/system/me/branches", headers=headers),
            200,
        )
        if not branches:
            raise RuntimeError("Default admin has no branch assignment")
        switched = expect_status(
            client.post(
                "/api/v1/auth/switch-branch",
                headers=headers,
                json={"branch_id": branches[0]["branch_id"]},
            ),
            200,
        )
        headers = {"Authorization": f"Bearer {switched['access_token']}"}
        roles = expect_status(
            client.get("/api/v1/system/branch-assignable-roles", headers=headers),
            200,
        )
        store_role = next((role for role in roles if role["name"] == "store_cashier"), None)
        if store_role is None:
            raise RuntimeError("store_cashier is not branch assignable")

        created = expect_status(
            client.post(
                "/api/v1/system/user-access-requests",
                headers=headers,
                json={
                    "brand_slug": "restaurant",
                    "requested_role_id": store_role["id"],
                    "username": f"api-cashier-{marker}",
                    "password": "CashierPass123!",
                    "first_name": "API",
                    "last_name": "Cashier",
                    "email": f"api-cashier-{marker}@example.com",
                },
            ),
            201,
        )
        scoped_requests = expect_status(
            client.get(
                "/api/v1/system/user-access-requests",
                headers=headers,
                params={"brand_slug": "restaurant", "status": "pending"},
            ),
            200,
        )
        if not any(row["id"] == created["id"] for row in scoped_requests):
            raise RuntimeError("Brand center list did not include the new request")
        if any(row["brand_slug"] != "restaurant" for row in scoped_requests):
            raise RuntimeError("Brand center list leaked a request from another brand")

        branch_requests = expect_status(
            client.get(
                "/api/v1/system/user-access-requests/mine",
                headers=headers,
                params={"brand_slug": "restaurant", "status": "pending"},
            ),
            200,
        )
        if not any(row["id"] == created["id"] for row in branch_requests):
            raise RuntimeError("Branch brand list did not include the new request")

        approved = expect_status(
            client.post(
                f"/api/v1/system/user-access-requests/{created['id']}/approve",
                headers=headers,
                json={"approved_role_id": store_role["id"]},
            ),
            200,
        )
        username = f"api-cashier-{marker}"
        password = "CashierPass123!"
        if approved["activation_mode"] != "activated" or approved["created_username"] != username:
            raise RuntimeError(f"Approval did not activate the requested login: {approved}")
        if approved["invitation_id"] is not None or approved["otp_code"] is not None:
            raise RuntimeError("Direct credential approval unexpectedly created an invitation")
        employee_login = expect_status(
            client.post(
                "/api/v1/auth/login",
                json={
                    "company_id": str(DEFAULT_COMPANY_ID),
                    "username": username,
                    "password": password,
                },
            ),
            200,
        )
        if employee_login["user"]["username"] != username:
            raise RuntimeError("Activated employee could not log in")

        detail = expect_status(
            client.get(
                f"/api/v1/system/user-access-requests/{created['id']}",
                headers=headers,
            ),
            200,
        )
        if detail["status"] != "activated":
            raise RuntimeError(f"Expected activated request, got {detail['status']}")
        print(f"user_access_api_smoke=ok request={created['id']} username={username}")


if __name__ == "__main__":
    run()
