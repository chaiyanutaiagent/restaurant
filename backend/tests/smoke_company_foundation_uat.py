"""Read-only UAT smoke checks for the WP36-WP41 Company foundation.

The script intentionally avoids operational writes. It uses the guarded UAT
auto-login endpoint, validates the Company contracts, switches to an existing
branch to exercise signed context issuance, and checks the public shell routes.
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any


BASE_URL = os.environ.get("UAT_BASE_URL", "https://uat-pos.foodchainservice.com").rstrip("/")
TIMEOUT_SECONDS = int(os.environ.get("UAT_SMOKE_TIMEOUT_SECONDS", "30"))
EXPECTED_MODULES = {
    "erp",
    "restaurant_pos",
    "retail_pos",
    "takeaway_pos",
    "central_kitchen",
    "hotel_pms",
}
VALID_OPERATIONAL_STATES = {
    "online",
    "offline",
    "degraded",
    "pending_sync",
    "stale",
    "error",
    "disabled",
}


class SmokeFailure(RuntimeError):
    pass


@dataclass
class SmokeReport:
    passed: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def check(self, condition: bool, label: str, detail: str = "") -> None:
        if not condition:
            suffix = f": {detail}" if detail else ""
            raise SmokeFailure(f"{label}{suffix}")
        self.passed.append(label)


def request_json(
    path: str,
    *,
    token: str | None = None,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    expected_status: int = 200,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json", "User-Agent": "foodchainservice-uat-smoke/1.0"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            raw = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        raw = error.read()
    except (urllib.error.URLError, TimeoutError, ssl.SSLError) as error:
        raise SmokeFailure(f"request failed for {path}: {error}") from error

    payload: dict[str, Any] = {}
    if raw:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise SmokeFailure(f"invalid JSON from {path} (HTTP {status})") from error
    if status != expected_status:
        detail = payload.get("detail") or payload.get("error") or payload
        raise SmokeFailure(f"{path} returned HTTP {status}, expected {expected_status}: {detail}")
    return status, payload


def request_page(path: str, *, expected_status: int = 200) -> int:
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers={"User-Agent": "foodchainservice-uat-smoke/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            response.read(1024)
    except urllib.error.HTTPError as error:
        status = error.code
    except (urllib.error.URLError, TimeoutError, ssl.SSLError) as error:
        raise SmokeFailure(f"request failed for {path}: {error}") from error
    if status != expected_status:
        raise SmokeFailure(f"{path} returned HTTP {status}, expected {expected_status}")
    return status


def response_data(payload: dict[str, Any], label: str) -> Any:
    if payload.get("error") is not None or "data" not in payload:
        raise SmokeFailure(f"{label} does not use the expected response envelope")
    return payload["data"]


def main() -> int:
    report = SmokeReport()

    for path in ("/", "/company", "/company/apps", "/company/actions", "/admin"):
        report.check(request_page(path) == 200, f"shell page {path}")

    _, health = request_json("/health")
    report.check(health.get("status") == "ok", "backend health")
    request_json("/health/ready")
    report.passed.append("backend readiness")

    request_json("/api/v1/company/context", expected_status=401)
    report.passed.append("unauthenticated Company context is rejected")

    _, login_payload = request_json("/api/v1/auth/uat/auto-login", method="POST", body={})
    login = response_data(login_payload, "UAT auto-login")
    token = login.get("access_token")
    report.check(isinstance(token, str) and len(token) > 20, "guarded UAT login")

    _, me_payload = request_json("/api/v1/auth/me", token=token)
    me = response_data(me_payload, "current user")
    report.check(me.get("company_id") is not None, "signed Company identity")
    report.check("*" in me.get("permissions", []), "UAT owner permission context")

    _, context_payload = request_json("/api/v1/company/context", token=token)
    context = response_data(context_payload, "Company context")
    report.check(context.get("environment") == "uat", "canonical UAT environment")
    report.check(context.get("company", {}).get("id") == me.get("company_id"), "Company context")
    transport = context.get("transport", {})
    report.check(
        transport.get("authoritative_source") == "signed_token"
        and transport.get("client_context_is_trusted") is False
        and transport.get("switch_requires_new_token") is True,
        "signed context transport policy",
    )

    _, access_payload = request_json("/api/v1/company/access", token=token)
    access = response_data(access_payload, "effective access")
    report.check(access.get("default_route") == "/company", "owner role-based landing")
    module_rows = access.get("modules", [])
    module_keys = {row.get("module_key") for row in module_rows}
    report.check(module_keys == EXPECTED_MODULES, "Product Readiness module coverage")
    report.check(
        all(
            not row.get("allowed_actions")
            for row in module_rows
            if row.get("module_key") in {"takeaway_pos", "hotel_pms"}
        ),
        "non-live product actions fail closed",
    )
    report.check(
        all(
            action not in {"create", "update", "execute", "approve"}
            for row in module_rows
            if row.get("module_key") == "central_kitchen"
            for action in row.get("allowed_actions", [])
        ),
        "Central Kitchen write actions remain closed",
    )

    _, branches_payload = request_json("/api/v1/system/me/branches", token=token)
    branches = response_data(branches_payload, "accessible branches")
    report.check(isinstance(branches, list) and bool(branches), "accessible branch list")
    switchable = next(
        (row for row in branches if row.get("branch_id") or row.get("id")),
        None,
    )
    report.check(switchable is not None, "branch available for context switch")
    branch_id = switchable.get("branch_id") or switchable.get("id")
    _, switched_payload = request_json(
        "/api/v1/auth/switch-branch",
        token=token,
        method="POST",
        body={"branch_id": branch_id},
    )
    switched = response_data(switched_payload, "branch switch")
    branch_token = switched.get("access_token")
    report.check(isinstance(branch_token, str) and len(branch_token) > 20, "new signed branch token")
    _, branch_context_payload = request_json("/api/v1/company/context", token=branch_token)
    branch_context = response_data(branch_context_payload, "branch Company context")
    report.check(branch_context.get("branch", {}).get("id") == branch_id, "Branch context")
    if switchable.get("brand_id"):
        report.check(
            branch_context.get("brand", {}).get("id") == switchable.get("brand_id"),
            "Brand context",
        )
    else:
        report.notes.append("Selected branch has no Brand mapping; Brand context is not asserted.")

    _, actions_payload = request_json("/api/v1/company/action-center", token=branch_token)
    actions = response_data(actions_payload, "Action Center")
    action_items = actions.get("items", [])
    report.check(actions.get("total") == len(action_items), "Action Center totals")
    report.check(
        all(item.get("deep_link", "").startswith("/") for item in action_items),
        "Action Center deep links",
    )

    _, overview_payload = request_json("/api/v1/company/overview", token=branch_token)
    overview = response_data(overview_payload, "Company Dashboard")
    sections = overview.get("sections", [])
    report.check(
        {section.get("module_key") for section in sections} == EXPECTED_MODULES,
        "Company Dashboard module coverage",
    )
    report.check(isinstance(overview.get("task_summary"), dict), "Dashboard task summary")

    _, state_payload = request_json("/api/v1/company/operational-status", token=branch_token)
    operational = response_data(state_payload, "Device/Sync state")
    components = operational.get("components", [])
    report.check(
        all(component.get("state") in VALID_OPERATIONAL_STATES for component in components),
        "normalized Device/Sync states",
    )
    report.check(
        set(operational.get("summary", {})).issubset(VALID_OPERATIONAL_STATES),
        "Device/Sync summary states",
    )

    _, audit_payload = request_json("/api/v1/company/audit?limit=5", token=branch_token)
    audit = response_data(audit_payload, "Company audit")
    report.check(isinstance(audit.get("items"), list), "Company audit timeline")

    _, presets_payload = request_json("/api/v1/system/role-presets", token=token)
    presets = response_data(presets_payload, "role presets")
    preset_keys = {preset.get("key") for preset in presets if preset.get("is_available")}
    report.check(
        {"company-owner", "brand-manager", "branch-manager", "cashier"}.issubset(preset_keys),
        "role preset availability",
    )

    print(f"PASS: {len(report.passed)} UAT smoke assertions")
    print(f"Base URL: {BASE_URL}")
    print(f"Company: {context.get('company', {}).get('name')} ({context.get('company', {}).get('id')})")
    print(f"Branch: {branch_context.get('branch', {}).get('name')} ({branch_id})")
    print(f"Brand: {branch_context.get('brand', {}).get('name') or 'not mapped'}")
    print(f"Action Center items: {len(action_items)}")
    print(f"Operational components: {len(components)}")
    for note in report.notes:
        print(f"NOTE: {note}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
