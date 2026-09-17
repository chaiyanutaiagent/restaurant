from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


REQUIRED_CHECKS = {
    "android_install_launch",
    "ipad_safari_layout_touch",
    "camera_qr_scan",
    "bluetooth_pair_permission",
    "customer_merchant_print_cut",
    "printer_reconnect_paper_out",
    "offline_sale_lost_ack_replay",
    "kds_multi_device_concurrency",
    "pickup_public_status",
    "shift_stock_central_transfer",
    "operator_handoff",
}


def validate(document: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if document.get("scope") != "WP24-TAKEAWAY-PHYSICAL-UAT":
        errors.append("scope_mismatch")
    if document.get("environment") != "uat":
        errors.append("uat_environment_required")
    build = document.get("build")
    if not isinstance(build, dict):
        errors.append("build_required")
    else:
        if not re.fullmatch(r"[0-9a-f]{40}", str(build.get("git_commit", ""))):
            errors.append("git_commit_invalid")
        if build.get("package_id") != "com.foodchainservice.takeaway.uat":
            errors.append("uat_package_id_invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", str(build.get("apk_sha256", ""))):
            errors.append("apk_sha256_invalid")
    devices = document.get("devices")
    device_types = {
        str(row.get("type"))
        for row in devices or []
        if isinstance(row, dict) and row.get("alias") and row.get("os_version")
    }
    if not {"android", "ipad"}.issubset(device_types):
        errors.append("android_and_ipad_evidence_required")
    checks = document.get("checks")
    by_id = {
        str(row.get("id")): row
        for row in checks or []
        if isinstance(row, dict)
    }
    missing = REQUIRED_CHECKS - set(by_id)
    if missing:
        errors.append("missing_checks:" + ",".join(sorted(missing)))
    for check_id in sorted(REQUIRED_CHECKS & set(by_id)):
        row = by_id[check_id]
        if row.get("status") != "passed":
            errors.append(f"check_not_passed:{check_id}")
        evidence = row.get("evidence")
        if not isinstance(evidence, list) or not evidence or not all(
            isinstance(item, str) and item.strip() for item in evidence
        ):
            errors.append(f"evidence_required:{check_id}")
    approval = document.get("approval")
    if not isinstance(approval, dict) or approval.get("status") != "approved":
        errors.append("owner_approval_required")
    elif not approval.get("operator") or not approval.get("owner") or not approval.get("approved_at"):
        errors.append("approval_identity_and_time_required")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate WP24 physical UAT evidence")
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
