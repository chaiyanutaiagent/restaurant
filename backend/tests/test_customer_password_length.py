"""Keep customer signup, owner creation and password reset limits consistent."""
import unittest

from pydantic import ValidationError

from app.schemas.membership import SaasPasswordResetConfirm, SaasSignupRequest
from app.schemas.platform import PlatformCompanyOwnerCreate


class CustomerPasswordLengthTests(unittest.TestCase):
    def requests(self, password):
        return (
            (SaasPasswordResetConfirm, {
                "token": "t" * 32, "new_password": password,
            }),
            (PlatformCompanyOwnerCreate, {
                "username": "sample.owner", "display_name": "Sample Owner",
                "password": password,
            }),
            (SaasSignupRequest, {
                "company_name": "Sample Company", "owner_display_name": "Sample Owner",
                "owner_email": "owner@example.com", "username": "sample.owner",
                "password": password, "terms_accepted": True, "privacy_accepted": True,
            }),
        )

    def test_accepts_eight_through_128_characters(self):
        for length in (8, 12, 128):
            for model, payload in self.requests("x" * length):
                with self.subTest(model=model.__name__, length=length):
                    model(**payload)

    def test_rejects_short_and_oversized_passwords(self):
        for length in (0, 6, 7, 129):
            for model, payload in self.requests("x" * length):
                with self.subTest(model=model.__name__, length=length):
                    with self.assertRaises(ValidationError):
                        model(**payload)


if __name__ == "__main__":
    unittest.main()
