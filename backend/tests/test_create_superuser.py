import uuid
import unittest

from app.models.user import User
from app.utils.create_superuser import DEFAULT_BRANCHES, _ensure_existing_admin_access


class CreateSuperuserTests(unittest.TestCase):
    def test_default_company_bootstrap_contains_only_bkk01(self) -> None:
        self.assertEqual([branch["code"] for branch in DEFAULT_BRANCHES], ["BKK-01"])

    def test_existing_admin_bootstrap_preserves_password(self) -> None:
        user = User(
            company_id=uuid.uuid4(),
            username="admin",
            hashed_password="existing-password-hash",
            is_active=False,
            is_superuser=False,
        )

        _ensure_existing_admin_access(user)

        self.assertEqual(user.hashed_password, "existing-password-hash")
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_superuser)
