from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.utils.create_superuser import DEFAULT_COMPANY_ID


EXPECTED_KEYS = [
    "company-owner",
    "brand-manager",
    "branch-manager",
    "cashier",
    "kitchen-staff",
]


def expect_data(response, expected_status: int = 200):
    if response.status_code != expected_status:
        raise RuntimeError(
            f"Expected HTTP {expected_status}, got {response.status_code}: {response.text}"
        )
    return response.json()["data"]


def run() -> None:
    if not settings.default_admin_password:
        raise RuntimeError("DEFAULT_ADMIN_PASSWORD is required for API smoke test")

    with TestClient(app) as client:
        login = expect_data(
            client.post(
                "/api/v1/auth/login",
                json={
                    "company_id": str(DEFAULT_COMPANY_ID),
                    "username": "admin",
                    "password": settings.default_admin_password,
                },
            )
        )
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        presets = expect_data(client.get("/api/v1/system/role-presets", headers=headers))

    if [preset["key"] for preset in presets] != EXPECTED_KEYS:
        raise RuntimeError(f"Unexpected role preset order: {presets}")
    if any(not preset["is_available"] for preset in presets):
        missing = {
            preset["key"]: preset["missing_permission_codes"]
            for preset in presets
            if not preset["is_available"]
        }
        raise RuntimeError(f"Role preset permission catalog is incomplete: {missing}")

    by_key = {preset["key"]: preset for preset in presets}
    cashier_codes = set(by_key["cashier"]["permission_codes"])
    if cashier_codes.intersection(
        {"pos.sale.void", "pos.discount.override", "pos.refund.create", "fb.settings.manage"}
    ):
        raise RuntimeError("Cashier preset contains manager-only permissions")

    kitchen = by_key["kitchen-staff"]
    if kitchen["default_scope"] != "station":
        raise RuntimeError(f"Kitchen Staff scope is not station: {kitchen}")
    if set(kitchen["permission_codes"]) != {"fb.menu.view", "fb.kitchen.manage"}:
        raise RuntimeError(f"Kitchen Staff permissions escaped kitchen boundary: {kitchen}")

    print(
        "role_presets_api_smoke=ok "
        f"policy={presets[0]['policy_version']} presets={len(presets)}"
    )


if __name__ == "__main__":
    run()
