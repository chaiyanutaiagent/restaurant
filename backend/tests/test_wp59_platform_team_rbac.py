from __future__ import annotations

from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.dependencies import PlatformTokenData
from app.services.platform_access_service import (
    PLATFORM_ROLE_PERMISSIONS,
    has_permission,
    permissions_for_roles,
    require_platform_permission,
)
from app.services.platform_team_service import PlatformTeamService


class PlatformPermissionMatrixTests(unittest.TestCase):
    def test_roles_are_least_privilege_and_owner_is_explicit_wildcard(self) -> None:
        self.assertEqual(PLATFORM_ROLE_PERMISSIONS["platform_owner"], frozenset({"*"}))
        self.assertTrue(has_permission(permissions_for_roles(["billing"]), "platform.billing.manage"))
        self.assertFalse(has_permission(permissions_for_roles(["billing"]), "platform.team.manage"))
        self.assertTrue(has_permission(permissions_for_roles(["security"]), "platform.security.session.revoke"))
        self.assertFalse(has_permission(permissions_for_roles(["support"]), "platform.billing.view"))
        self.assertFalse(has_permission(permissions_for_roles(["auditor"]), "platform.operations.manage"))

    def test_server_permission_is_deny_by_default(self) -> None:
        current = PlatformTokenData(
            operator_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            username="auditor",
            display_name="Auditor",
            is_superuser=False,
            mfa_verified=True,
            role_codes=["auditor"],
            permissions=list(permissions_for_roles(["auditor"])),
            environment="uat",
        )
        require_platform_permission(current, "platform.audit.view")
        with self.assertRaises(HTTPException) as raised:
            require_platform_permission(current, "platform.company.manage")
        self.assertEqual(raised.exception.status_code, 403)


class PlatformTeamGovernanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_last_owner_cannot_be_removed(self) -> None:
        service = PlatformTeamService(AsyncMock(), actor_id=uuid.uuid4())
        with patch(
            "app.services.platform_team_service.active_owner_count",
            new=AsyncMock(return_value=0),
        ):
            with self.assertRaises(HTTPException) as raised:
                await service._protect_last_owner(uuid.uuid4(), "uat")
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["code"], "last_platform_owner")

    async def test_access_change_increments_version_and_revokes_sessions(self) -> None:
        db = AsyncMock()
        operator = SimpleNamespace(id=uuid.uuid4(), credential_version=4)
        await PlatformTeamService(db, actor_id=uuid.uuid4())._invalidate_access(
            operator, reason="role-revoked"
        )
        self.assertEqual(operator.credential_version, 5)
        db.execute.assert_awaited_once()

    async def test_stale_operator_version_fails_closed(self) -> None:
        operator = SimpleNamespace(credential_version=7)
        with self.assertRaises(HTTPException) as raised:
            PlatformTeamService._check_version(operator, 6)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["code"], "stale_operator_version")


if __name__ == "__main__":
    unittest.main()
