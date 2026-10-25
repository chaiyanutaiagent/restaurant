import os
import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from app.services import uat_owner_identity as bridge


class OwnerIdentityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.uid, self.oid = uuid.uuid4(), uuid.uuid4()
        self.env = patch.dict(os.environ, {
            "UAT_OWNER_TENANT_USER_ID": str(self.uid),
            "UAT_OWNER_PLATFORM_OPERATOR_ID": str(self.oid),
        })
        self.env.start()
        self.config = patch.object(bridge, "settings", SimpleNamespace(
            environment="development", identity_database="platform_core",
            saas_public_base_url="https://uat-app.example.com"))
        self.config.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.config.stop)
        self.operator = SimpleNamespace(id=self.oid, is_active=True, hashed_password="obsolete",
                                        credential_version=1)
        self.user = SimpleNamespace(id=self.uid, company_id=uuid.uuid4(), is_active=True,
            deleted_at=None, is_superuser=True, hashed_password="canonical", credential_version=1)
        self.db = AsyncMock()
        self.db.get.side_effect = [self.user, SimpleNamespace(is_active=True)]

    async def test_only_explicit_uuid_pair_uses_canonical_password(self):
        self.assertEqual(await bridge.platform_password_hash(self.db, self.operator), "canonical")

    async def test_other_operator_keeps_separate_identity(self):
        self.operator.id = uuid.uuid4()
        self.assertEqual(await bridge.platform_password_hash(self.db, self.operator), "obsolete")
        self.db.get.assert_not_called()

    async def test_inactive_owner_fails_closed(self):
        self.user.is_active = False
        with self.assertRaises(HTTPException):
            await bridge.platform_password_hash(self.db, self.operator)

    async def test_removed_superuser_grant_fails_closed(self):
        self.user.is_superuser = False
        with self.assertRaises(HTTPException):
            await bridge.linked_owner_user(self.db, self.operator)

    async def test_production_rejects_link(self):
        bridge.settings.environment = "production"
        with self.assertRaises(HTTPException):
            bridge.owner_link()

    async def test_unconfigured_system_is_unchanged(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(bridge.owner_link())

    async def test_partial_mapping_is_rejected(self):
        os.environ.pop("UAT_OWNER_TENANT_USER_ID")
        with self.assertRaises(HTTPException):
            bridge.owner_link()

    async def test_reset_invalidates_platform_sessions(self):
        self.db.get.side_effect = None
        self.db.get.return_value = self.operator
        await bridge.revoke_linked_platform_sessions(self.db, self.user)
        self.assertEqual(self.operator.credential_version, 2)
        self.db.execute.assert_awaited_once()

    async def test_pam_reset_does_not_modify_platform(self):
        self.user.id = uuid.uuid4()
        await bridge.revoke_linked_platform_sessions(self.db, self.user)
        self.db.execute.assert_not_called()

    async def test_platform_password_change_updates_canonical_only(self):
        self.assertTrue(await bridge.change_linked_owner_password(
            self.db, self.operator, "new-hash", datetime.now(timezone.utc)))
        self.assertEqual(self.user.hashed_password, "new-hash")
        self.assertEqual(self.user.credential_version, 2)
        self.assertEqual(self.operator.hashed_password, "obsolete")
        self.assertEqual(self.db.execute.await_count, 2)


if __name__ == "__main__":
    unittest.main()
