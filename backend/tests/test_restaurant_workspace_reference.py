import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from app.config import settings
from app.dependencies import TokenData
from app.services.restaurant_workspace_reference import ensure_restaurant_workspace_reference


class RestaurantWorkspaceReferenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.source = AsyncMock()
        self.target = AsyncMock()
        self.target.scalar.return_value = None
        self.current = TokenData(user_id=uuid.uuid4(), company_id=uuid.uuid4(),
                                 branch_id=uuid.uuid4(), brand_id=uuid.uuid4(),
                                 business_type="restaurant", permissions=["fb.settings.manage"])
        self.enterContext(patch.object(settings, "identity_database", "platform_core"))
        self.enterContext(patch.object(settings, "restaurant_service_database", "legacy"))

    async def test_cutover_and_legacy_identity_do_not_bootstrap(self):
        for key, value in (("identity_database", "legacy"), ("restaurant_service_database", "restaurant")):
            with patch.object(settings, key, value):
                await ensure_restaurant_workspace_reference(self.source, self.target, self.current)
        self.target.scalar.assert_not_awaited()
        self.source.execute.assert_not_awaited()

    async def test_existing_operational_branch_is_not_overwritten(self):
        self.target.scalar.return_value = SimpleNamespace(company_id=self.current.company_id, is_active=True, deleted_at=None)
        await ensure_restaurant_workspace_reference(self.source, self.target, self.current)
        self.source.execute.assert_not_awaited()
        self.target.execute.assert_not_awaited()

    async def test_cross_company_or_inactive_operational_branch_denied(self):
        for company, active in ((uuid.uuid4(), True), (self.current.company_id, False)):
            self.target.scalar.return_value = SimpleNamespace(company_id=company, is_active=active, deleted_at=None)
            with self.assertRaises(HTTPException) as raised:
                await ensure_restaurant_workspace_reference(self.source, self.target, self.current)
            self.assertEqual(raised.exception.status_code, 403)
        self.target.execute.assert_not_awaited()

    async def test_missing_canonical_context_explains_workspace_selection(self):
        self.current.brand_id = None
        with self.assertRaises(HTTPException) as raised:
            await ensure_restaurant_workspace_reference(self.source, self.target, self.current)
        self.assertEqual(raised.exception.status_code, 409)
        self.target.execute.assert_not_awaited()

    async def test_missing_or_foreign_canonical_link_denied_before_write(self):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        self.source.execute.return_value = result
        with self.assertRaises(HTTPException) as raised:
            await ensure_restaurant_workspace_reference(self.source, self.target, self.current)
        self.assertEqual(raised.exception.status_code, 403)
        self.target.execute.assert_not_awaited()
