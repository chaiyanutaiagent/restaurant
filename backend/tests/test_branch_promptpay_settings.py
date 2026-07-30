from __future__ import annotations

import unittest

from fastapi import HTTPException
from pydantic import ValidationError

from app.routers.pos import get_promptpay_qr
from app.schemas.user_mgmt import BranchSettingsUpdate


class BranchPromptPaySettingsTests(unittest.IsolatedAsyncioTestCase):
    def test_accepts_valid_promptpay_targets(self) -> None:
        self.assertEqual(BranchSettingsUpdate(promptpay_target="081-234-5678").promptpay_target, "081-234-5678")
        self.assertEqual(BranchSettingsUpdate(promptpay_target="1234567890123").promptpay_target, "1234567890123")
        self.assertIsNone(BranchSettingsUpdate(promptpay_target="  ").promptpay_target)

    def test_rejects_invalid_promptpay_target(self) -> None:
        with self.assertRaises(ValidationError):
            BranchSettingsUpdate(promptpay_target="1234")

    async def test_qr_endpoint_returns_bad_request_for_invalid_target(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await get_promptpay_qr(amount=None, target="1234", db=None)  # type: ignore[arg-type]
        self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
