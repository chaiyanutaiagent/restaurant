from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest
import uuid

from fastapi import HTTPException

from app.models.pos import PosHoldDraft
from app.schemas.pos import HoldDraftCreateRequest
from app.services.hold_draft_service import HoldDraftService


def _draft(*, status: str = "active", version: int = 1) -> PosHoldDraft:
    now = datetime.now(timezone.utc)
    return PosHoldDraft(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        branch_id=uuid.uuid4(),
        location_id=uuid.uuid4(),
        origin_shift_id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        draft_no="HD20260920-0001",
        label="โต๊ะ A1",
        source_type="restaurant_table",
        content_json={"pricing_items": []},
        pricing_context={},
        pricing_snapshot={},
        status=status,
        version=version,
        idempotency_key="wp44-create-key",
        request_hash="a" * 64,
        expires_at=now + timedelta(hours=2),
        created_at=now,
        updated_at=now,
    )


class WP44HoldDraftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = HoldDraftService(None)  # type: ignore[arg-type]

    def test_expiry_is_server_authoritative_and_increments_version(self) -> None:
        draft = _draft(status="active", version=4)
        draft.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

        changed = self.service._expire_if_needed(draft, datetime.now(timezone.utc))

        self.assertEqual(changed, "expire")
        self.assertEqual(draft.status, "expired")
        self.assertEqual(draft.version, 5)
        self.assertIsNotNone(draft.expired_at)

    def test_expired_claim_is_released_without_expiring_draft(self) -> None:
        draft = _draft(status="claimed", version=2)
        draft.claim_id = uuid.uuid4()
        draft.claimed_by = uuid.uuid4()
        draft.claim_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

        changed = self.service._expire_if_needed(draft, datetime.now(timezone.utc))

        self.assertEqual(changed, "claim_expire")
        self.assertEqual(draft.status, "active")
        self.assertEqual(draft.version, 3)
        self.assertIsNone(draft.claim_id)

    def test_optimistic_concurrency_fails_closed(self) -> None:
        draft = _draft(version=7)

        with self.assertRaises(HTTPException) as caught:
            self.service._assert_version(draft, 6)

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail["code"], "draft_conflict")
        self.assertEqual(caught.exception.detail["current_version"], 7)

    def test_hold_contract_cannot_accept_payment_or_client_total(self) -> None:
        payload = HoldDraftCreateRequest.model_validate(
            {
                "shift_id": str(uuid.uuid4()),
                "location_id": str(uuid.uuid4()),
                "label": "ลูกค้ารอรับ",
                "items": [{"product_id": str(uuid.uuid4()), "qty": "2"}],
                "order_discount": "10",
                "idempotency_key": "wp44-safe-payload",
                "payment_method": "cash",
                "paid_amount": "9999",
                "total_amount": "0.01",
                "reference_no": "must-not-persist",
            }
        )

        serialized = payload.model_dump(mode="json")
        self.assertNotIn("payment_method", serialized)
        self.assertNotIn("paid_amount", serialized)
        self.assertNotIn("total_amount", serialized)
        self.assertNotIn("reference_no", serialized)
        self.assertEqual(payload.items[0].qty, Decimal("2"))


if __name__ == "__main__":
    unittest.main()
