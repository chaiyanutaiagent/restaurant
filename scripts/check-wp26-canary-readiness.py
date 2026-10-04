from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sys


def sha(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "")))


def validate(document: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if document.get("scope") != "WP26-TAKEAWAY-CANARY-CUTOVER":
        errors.append("scope_mismatch")
    release = document.get("release")
    if not isinstance(release, dict) or not re.fullmatch(r"[0-9a-f]{40}", str(release.get("git_commit", ""))) or not sha(release.get("artifact_sha256")):
        errors.append("release_identity_invalid")
    dependencies = document.get("dependencies")
    if not isinstance(dependencies, dict):
        errors.append("wp24_wp25_evidence_required")
    else:
        for wp in ("wp24", "wp25"):
            if dependencies.get(f"{wp}_status") != "passed" or not sha(dependencies.get(f"{wp}_evidence_sha256")):
                errors.append(f"{wp}_must_pass")
    backup = document.get("final_backup")
    if not isinstance(backup, dict) or backup.get("status") != "passed" or not backup.get("reference") or not sha(backup.get("sha256")) or backup.get("restore_verified") is not True:
        errors.append("verified_final_backup_required")
    canary = document.get("canary")
    if not isinstance(canary, dict) or canary.get("status") != "passed" or not canary.get("branch_id") or not canary.get("started_at") or not canary.get("ended_at") or not canary.get("evidence"):
        errors.append("one_branch_canary_must_pass")
    monitoring = document.get("monitoring")
    try:
        monitoring_minutes = int(monitoring.get("duration_minutes", 0)) if isinstance(monitoring, dict) else 0
    except (TypeError, ValueError):
        monitoring_minutes = 0
    if not isinstance(monitoring, dict) or monitoring.get("status") != "passed" or monitoring_minutes < 60:
        errors.append("monitoring_window_must_pass_60_minutes")
    elif any(monitoring.get(key) != 0 for key in ("duplicate_orders", "stock_mismatches", "payment_mismatches")):
        errors.append("canary_control_mismatch")
    else:
        try:
            if Decimal(str(monitoring.get("error_rate_percent"))) > Decimal("1.00"):
                errors.append("canary_error_rate_too_high")
        except InvalidOperation:
            errors.append("canary_error_rate_invalid")
    rollback = document.get("rollback_drill")
    try:
        recovery_minutes = int(rollback.get("recovery_minutes", 0)) if isinstance(rollback, dict) else 0
    except (TypeError, ValueError):
        recovery_minutes = 0
    if not isinstance(rollback, dict) or rollback.get("status") != "passed" or not rollback.get("reference") or recovery_minutes <= 0:
        errors.append("rollback_drill_must_pass")
    decision = document.get("owner_decision")
    if not isinstance(decision, dict) or decision.get("decision") != "go" or not decision.get("owner") or not decision.get("decided_at"):
        errors.append("owner_go_required")
    activation = document.get("production_activation")
    if not isinstance(activation, dict) or activation.get("status") not in {"not_started", "completed"}:
        errors.append("production_activation_state_invalid")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Check WP26 canary/cutover evidence; this tool never activates production")
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    try:
        value = json.loads(args.evidence.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("evidence must be an object")
        errors = validate(value)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "production_activated": False, "errors": [str(exc)]}))
        return 1
    activation = value.get("production_activation")
    print(json.dumps({"status": "ready" if not errors else "blocked", "production_activated": isinstance(activation, dict) and activation.get("status") == "completed", "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
