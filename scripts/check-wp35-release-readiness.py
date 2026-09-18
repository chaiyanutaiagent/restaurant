from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from typing import Any


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
ENGINEERING_WPS = tuple(f"wp{number}" for number in range(27, 35))
EXTERNAL_GATES = (
    "platform_operator_mfa",
    "accountant_tax_review",
    "restaurant_physical_pilot",
    "retail_physical_pilot",
    "central_kitchen_opening_stock",
    "takeaway_approved_snapshot_canary",
    "residual_defect_acceptance",
)
ROLLOUT_WAVES = (
    "platform_company_admin",
    "shared_erp",
    "restaurant_one_branch",
    "retail_one_branch",
    "central_kitchen_limited_scope",
    "takeaway_one_branch",
)


def _valid_time(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _approval_errors(name: str, value: object) -> list[str]:
    if not isinstance(value, dict):
        return [f"{name}_missing"]
    errors: list[str] = []
    if value.get("status") != "passed":
        errors.append(f"{name}_must_pass")
    if not value.get("approved_by"):
        errors.append(f"{name}_approver_required")
    if not _valid_time(value.get("approved_at")):
        errors.append(f"{name}_approval_time_required")
    if not SHA256_RE.fullmatch(str(value.get("evidence_sha256") or "")):
        errors.append(f"{name}_evidence_sha256_required")
    return errors


def validate(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if document.get("scope") != "WP35-FOODCHAINSERVICE-RELEASE":
        errors.append("scope_mismatch")

    release = document.get("release")
    if not isinstance(release, dict):
        errors.append("release_identity_missing")
    else:
        if not COMMIT_RE.fullmatch(str(release.get("git_commit") or "")):
            errors.append("release_commit_invalid")
        if not SHA256_RE.fullmatch(str(release.get("artifact_sha256") or "")):
            errors.append("release_artifact_sha256_invalid")
        if release.get("immutable") is not True:
            errors.append("release_must_be_immutable")

    engineering = document.get("engineering")
    if not isinstance(engineering, dict):
        errors.append("engineering_evidence_missing")
    else:
        for wp in ENGINEERING_WPS:
            value = engineering.get(wp)
            if not isinstance(value, dict) or value.get("status") != "passed":
                errors.append(f"{wp}_engineering_must_pass")
            elif not SHA256_RE.fullmatch(str(value.get("evidence_sha256") or "")):
                errors.append(f"{wp}_engineering_evidence_sha256_required")

    external = document.get("external_gates")
    if not isinstance(external, dict):
        errors.append("external_gates_missing")
    else:
        for gate in EXTERNAL_GATES:
            errors.extend(_approval_errors(gate, external.get(gate)))

    recovery = document.get("recovery")
    if not isinstance(recovery, dict):
        errors.append("recovery_evidence_missing")
    else:
        if recovery.get("status") != "passed":
            errors.append("recovery_must_pass")
        if recovery.get("five_boundaries_restored") is not True:
            errors.append("five_boundary_restore_required")
        if not recovery.get("server_backup_reference") or not recovery.get("mac_backup_reference"):
            errors.append("server_and_mac_backup_references_required")
        if not SHA256_RE.fullmatch(str(recovery.get("manifest_sha256") or "")):
            errors.append("backup_manifest_sha256_required")

    rollout = document.get("rollout")
    if not isinstance(rollout, dict):
        errors.append("rollout_plan_missing")
    else:
        for wave in ROLLOUT_WAVES:
            value = rollout.get(wave)
            if not isinstance(value, dict) or value.get("status") != "approved":
                errors.append(f"{wave}_wave_must_be_approved")
            elif not value.get("owner") or not value.get("rollback_owner"):
                errors.append(f"{wave}_owners_required")

    monitoring = document.get("monitoring")
    try:
        duration_minutes = int(monitoring.get("minimum_minutes", 0)) if isinstance(monitoring, dict) else 0
    except (TypeError, ValueError):
        duration_minutes = 0
    if not isinstance(monitoring, dict) or monitoring.get("status") != "ready":
        errors.append("monitoring_must_be_ready")
    elif duration_minutes < 60 or not monitoring.get("owner") or not monitoring.get("alert_route"):
        errors.append("monitoring_owner_route_and_60_minutes_required")

    rollback = document.get("rollback")
    try:
        rto_minutes = int(rollback.get("verified_rto_minutes", 0)) if isinstance(rollback, dict) else 0
    except (TypeError, ValueError):
        rto_minutes = 0
    if not isinstance(rollback, dict) or rollback.get("status") != "passed":
        errors.append("rollback_drill_must_pass")
    elif rto_minutes <= 0 or not rollback.get("owner") or not rollback.get("reference"):
        errors.append("rollback_owner_reference_and_rto_required")

    decision = document.get("owner_decision")
    if not isinstance(decision, dict) or decision.get("decision") != "go":
        errors.append("final_owner_go_required")
    elif not decision.get("owner") or not _valid_time(decision.get("decided_at")):
        errors.append("final_owner_identity_and_time_required")

    activation = document.get("production_activation")
    if not isinstance(activation, dict) or activation.get("status") not in {"not_started", "completed"}:
        errors.append("production_activation_state_invalid")
    return sorted(set(errors))


def _self_test() -> int:
    blocked = {"scope": "WP35-FOODCHAINSERVICE-RELEASE"}
    if not validate(blocked):
        raise AssertionError("incomplete release evidence must be blocked")

    evidence = "a" * 64
    approval = {
        "status": "passed",
        "approved_by": "test-owner",
        "approved_at": "2026-09-18T10:00:00+07:00",
        "evidence_sha256": evidence,
    }
    ready = {
        "scope": "WP35-FOODCHAINSERVICE-RELEASE",
        "release": {"git_commit": "b" * 40, "artifact_sha256": evidence, "immutable": True},
        "engineering": {wp: {"status": "passed", "evidence_sha256": evidence} for wp in ENGINEERING_WPS},
        "external_gates": {gate: dict(approval) for gate in EXTERNAL_GATES},
        "recovery": {
            "status": "passed",
            "five_boundaries_restored": True,
            "server_backup_reference": "server-ref",
            "mac_backup_reference": "mac-ref",
            "manifest_sha256": evidence,
        },
        "rollout": {
            wave: {"status": "approved", "owner": "owner", "rollback_owner": "rollback"}
            for wave in ROLLOUT_WAVES
        },
        "monitoring": {"status": "ready", "minimum_minutes": 60, "owner": "ops", "alert_route": "incident"},
        "rollback": {"status": "passed", "verified_rto_minutes": 5, "owner": "ops", "reference": "drill"},
        "owner_decision": {"decision": "go", "owner": "owner", "decided_at": "2026-09-18T10:00:00+07:00"},
        "production_activation": {"status": "not_started"},
    }
    errors = validate(ready)
    if errors:
        raise AssertionError(f"complete release evidence should pass: {errors}")
    print("PASS: WP35 release readiness validator self-test")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail closed until all Foodchainservice WP35 release gates are evidenced")
    parser.add_argument("evidence", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    if args.evidence is None:
        parser.error("evidence file is required unless --self-test is used")
    try:
        document = json.loads(args.evidence.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("evidence must be a JSON object")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "production_activated": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 1
    errors = validate(document)
    activation = document.get("production_activation")
    print(json.dumps({
        "status": "ready" if not errors else "blocked",
        "production_activated": isinstance(activation, dict) and activation.get("status") == "completed",
        "errors": errors,
    }, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
