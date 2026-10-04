from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.schemas.platform import PlatformOperatorInvitationAccept, PlatformPasswordChangeRequest
from app.utils.password_policy import validate_platform_password


class PlatformPasswordPolicyTests(unittest.TestCase):
    def test_accepts_password_with_all_required_character_classes(self) -> None:
        password = "Abcd12!x"
        self.assertEqual(validate_platform_password(password), password)
        invitation = PlatformOperatorInvitationAccept(token="t" * 32, password=password)
        self.assertEqual(invitation.password, password)

    def test_rejects_password_shorter_than_eight_characters(self) -> None:
        with self.assertRaises(ValueError):
            validate_platform_password("Ab1!xyz")

    def test_rejects_password_without_uppercase_number_or_special_character(self) -> None:
        for password in (
            "lowercase-123!",
            "No-Numbers-Here!",
            "NoSpecial12345",
            "Has Space 123!",
        ):
            with self.subTest(password=password), self.assertRaises(ValueError):
                validate_platform_password(password)

    def test_change_password_schema_enforces_policy(self) -> None:
        with self.assertRaises(ValidationError):
            PlatformPasswordChangeRequest(
                current_password="Existing-Owner-12!",
                new_password="long-but-weak-password",
            )


if __name__ == "__main__":
    unittest.main()
