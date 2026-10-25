"""Password setup remains scoped when a tenant is provisioned without signup."""
import uuid
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from app.models.company import Company
from app.models.user import User
from app.services.saas_membership_service import SaasMembershipService

class PlatformStaffPasswordResetTests(unittest.IsolatedAsyncioTestCase):
    async def run_reset(self, *, mismatch=False, active=True, profile=True, suspended=False, member=False):
        company_id, user_id = uuid.uuid4(), uuid.uuid4()
        credential = NS(company_id=company_id, owner_user_id=user_id, used_at=None)
        user = NS(id=user_id, company_id=uuid.uuid4() if mismatch else company_id,
                  username='loft.admin', email=None, is_active=active, deleted_at=None,
                  hashed_password='previous', credential_version=2)
        membership = NS(company_id=company_id, owner_email='owner@example.com') if member else None
        db = NS(scalar=AsyncMock(side_effect=[membership, NS(suspended_at=object() if suspended else None) if profile else None]),
                execute=AsyncMock(), add=MagicMock(), commit=AsyncMock())
        async def get(model, ident):
            return user if model is User else NS(is_active=True) if model is Company else None
        db.get = AsyncMock(side_effect=get)
        service = SaasMembershipService(db)
        service._valid_credential = AsyncMock(return_value=credential)
        with patch('app.services.saas_membership_service.hash_password', return_value='new-hash'), \
             patch('app.services.saas_membership_service.revoke_linked_platform_sessions', new=AsyncMock()):
            result = await service.reset_password('opaque-one-use-token','test-password',ip_address=None,user_agent=None)
        self.assertEqual(user.hashed_password,'new-hash')
        self.assertEqual(user.credential_version,3)
        self.assertIsNotNone(credential.used_at)
        db.commit.assert_awaited_once()
        self.assertEqual(db.add.call_args.args[0].company_id, company_id)
        return result

    async def test_platform_staff_without_membership(self):
        self.assertIsNone(await self.run_reset())

    async def test_existing_membership_unchanged(self):
        self.assertIsNotNone(await self.run_reset(member=True))

    async def test_cross_company_token_rejected(self):
        with self.assertRaises(HTTPException): await self.run_reset(mismatch=True)

    async def test_inactive_staff_rejected(self):
        with self.assertRaises(HTTPException): await self.run_reset(active=False)

    async def test_missing_or_suspended_platform_profile_rejected(self):
        for kwargs in [{'profile':False},{'suspended':True}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(HTTPException):
                await self.run_reset(**kwargs)
