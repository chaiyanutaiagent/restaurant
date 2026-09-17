from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sys


REQUIRED_CONTROLS = {
    "record_count",
    "historical_sales_total",
    "opening_stock_on_hand",
    "opening_stock_reserved",
    "opening_stock_value",
    "opening_credit_balance",
}


def validate(document: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if document.get("scope") != "WP25-TAKEAWAY-APPROVED-DATA-DRY-RUN":
        errors.append("scope_mismatch")
    if document.get("environment") != "isolated":
        errors.append("isolated_target_required")
    bundle = document.get("bundle")
    if not isinstance(bundle, dict):
        errors.append("bundle_required")
    else:
        if bundle.get("seal_status") != "verified":
            errors.append("trusted_bundle_seal_required")
        if not re.fullmatch(r"[0-9a-f]{64}", str(bundle.get("manifest_sha256", ""))):
            errors.append("manifest_sha256_invalid")
    controls = document.get("controls")
    if not isinstance(controls, dict):
        errors.append("controls_required")
        controls = {}
    missing = REQUIRED_CONTROLS - set(controls)
    if missing:
        errors.append("missing_controls:" + ",".join(sorted(missing)))
    for name in sorted(REQUIRED_CONTROLS & set(controls)):
        row = controls[name]
        if not isinstance(row, dict):
            errors.append(f"control_invalid:{name}")
            continue
        try:
            source = Decimal(str(row.get("source")))
            target = Decimal(str(row.get("target")))
        except InvalidOperation:
            errors.append(f"control_not_decimal:{name}")
            continue
        if source != target:
            errors.append(f"control_mismatch:{name}")
    unresolved = document.get("unresolved_count")
    waiver = document.get("waiver")
    if unresolved != 0:
        if not isinstance(waiver, dict) or waiver.get("status") != "approved" or not waiver.get("reference"):
            errors.append("unresolved_requires_owner_waiver")
    if document.get("idempotent_replay") is not True:
        errors.append("idempotent_replay_required")
    if document.get("historical_side_effects") != 0:
        errors.append("historical_side_effects_must_be_zero")
    if document.get("runtime_side_effects_disabled") is not True:
        errors.append("runtime_side_effects_must_be_disabled")
    approval = document.get("approval")
    if not isinstance(approval, dict) or approval.get("status") != "approved":
        errors.append("data_privacy_approval_required")
    elif not approval.get("data_owner") or not approval.get("privacy_owner") or not approval.get("approved_at"):
        errors.append("approval_identity_and_time_required")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate WP25 approved-data dry-run evidence")
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    try:
        value = json.loads(args.evidence.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("evidence must be an object")
        errors = validate(value)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "errors": [str(exc)]}))
        return 1
    print(json.dumps({"status": "passed" if not errors else "blocked", "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
