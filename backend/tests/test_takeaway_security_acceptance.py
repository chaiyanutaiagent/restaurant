from __future__ import annotations

import inspect
from pathlib import Path
import unittest

from fastapi.params import Depends
from pydantic import ValidationError
from sqlalchemy import UniqueConstraint

from app.models.takeaway import (
    TakeawayCreditEntry,
    TakeawayCutoverRun,
    TakeawayOperationalOutbox,
    TakeawayOrder,
    TakeawayStockMovement,
)
from app.routers import takeaway
from app.schemas.takeaway import TakeawayCreditTopupCreate
from app.services.role_preset_service import ROLE_PRESET_POLICIES


def unique_columns(model: object) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


class TakeawaySecurityAcceptanceTests(unittest.TestCase):
    def test_every_private_mutation_has_explicit_user_dependency(self) -> None:
        failures: list[str] = []
        for route in takeaway.router.routes:
            methods = set(route.methods or [])
            if not methods.intersection({"POST", "PUT", "PATCH", "DELETE"}):
                continue
            signature = inspect.signature(route.endpoint)
            current = signature.parameters.get("current")
            if current is None or not isinstance(current.default, Depends):
                failures.append(f"{','.join(sorted(methods))} {route.path}")
        self.assertEqual(failures, [])

    def test_cutover_apply_is_owner_only_in_default_role_presets(self) -> None:
        permissions = {
            preset.key: set(preset.permission_codes)
            for preset in ROLE_PRESET_POLICIES
        }
        self.assertIn("takeaway.import.apply", permissions["company-owner"])
        self.assertNotIn("takeaway.import.apply", permissions["brand-manager"])
        self.assertNotIn("takeaway.import.apply", permissions["branch-manager"])
        self.assertNotIn("takeaway.import.apply", permissions["cashier"])
        self.assertNotIn("takeaway.import.apply", permissions["kitchen-staff"])

    def test_evidence_url_rejects_unsafe_schemes_and_local_targets(self) -> None:
        base = {
            "amount": "100.00",
            "payment_method": "bank_transfer",
            "idempotency_key": "topup-security-001",
        }
        for value in (
            "javascript:alert(1)",
            "data:image/png;base64,AAAA",
            "file:///etc/passwd",
            "http://localhost/secret",
            "https://user:pass@example.com/slip.png",
            "/uploads/../secret",
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                TakeawayCreditTopupCreate(**base, evidence_url=value)
        self.assertEqual(
            TakeawayCreditTopupCreate(
                **base, evidence_url="/uploads/evidence/slip-001.png"
            ).evidence_url,
            "/uploads/evidence/slip-001.png",
        )
        self.assertEqual(
            TakeawayCreditTopupCreate(
                **base, evidence_url="https://files.foodchainservice.com/evidence/slip.png"
            ).evidence_url,
            "https://files.foodchainservice.com/evidence/slip.png",
        )

    def test_replay_sensitive_tables_have_database_uniqueness(self) -> None:
        self.assertIn(("branch_id", "idempotency_key"), unique_columns(TakeawayOrder))
        self.assertIn(("idempotency_key",), unique_columns(TakeawayStockMovement))
        self.assertIn(("idempotency_key",), unique_columns(TakeawayCreditEntry))
        self.assertIn(("idempotency_key",), unique_columns(TakeawayOperationalOutbox))
        self.assertIn(("company_id", "execution_key"), unique_columns(TakeawayCutoverRun))

    def test_takeaway_domain_does_not_import_other_operational_models(self) -> None:
        app_root = Path(__file__).resolve().parents[1] / "app"
        targets = [app_root / "routers" / "takeaway.py"]
        targets.extend(sorted((app_root / "services").glob("takeaway*.py")))
        forbidden = ("app.models.restaurant", "app.models.retail", "get_restaurant_service_db", "get_retail")
        findings = [
            f"{path.name}:{marker}"
            for path in targets
            for marker in forbidden
            if marker in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
