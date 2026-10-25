"""One-shot UAT cleanup. Default read-only plan; --apply requires backup marker.

No transactional business rows, Pam records or Production databases are changed.
Private output contains a one-use credential and must remain mode 0600.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import uuid
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import select, text, update
from app.config import settings
from app.database import PlatformSessionLocal
from app.models.user import User
from app.models.auth import RefreshToken
from app.models.audit import AuditLog
from app.models.platform import PlatformOperator, PlatformSession, SaasAccountCredential
from app.services.auth_service import AuthService
from app.services.platform_service import PlatformAuthService
from app.services.platform_access_service import effective_platform_access
from app.services.saas_membership_service import SaasMembershipService, hash_account_credential
from app.services.uat_owner_identity import owner_link
from app.utils.security import hash_password, verify_password
from app.cli.prepare_sketch_biz_test_staff import _load_workspaces

OWNER = uuid.UUID('8b45ab10-41ca-4aed-8e90-662f39392996')
OPERATOR = uuid.UUID('0a3d6f49-2264-4014-a83b-e3abbb8e2386')
PAM = uuid.UUID('1ffa800e-2076-43da-a7d1-5dc9d9358470')
COMPANY = uuid.UUID('1b8a1818-44d6-4d5f-9d22-e5e17b23c081')
ACTION = 'uat.owner_identity.consolidated.20261025'
REASON = 'Owner requested option 2: retain only pam.admin and one superadmin credential owner'
ARCHIVE = 'uat_owner_archive_20261025'
TABLES = ['users', 'platform_operators', 'refresh_tokens', 'platform_sessions',
          'staff_role_assignments', 'platform_operator_role_assignments',
          'saas_account_credentials', 'user_invitations', 'platform_operator_invitations']


async def pam_digest(db):
    values = []
    for table, column in [('users', 'id'), ('user_branches', 'user_id'),
            ('staff_role_assignments', 'user_id'), ('refresh_tokens', 'user_id'),
            ('saas_account_credentials', 'owner_user_id')]:
        rows = (await db.execute(text(
            f'SELECT to_jsonb(t)::text FROM {table} t WHERE {column}=:id ORDER BY id'
        ), {'id': PAM})).scalars().all()
        values.extend(rows)
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


async def rehearsal(db, owner, operator):
    """Exercise reset -> both login services -> permissions, then roll it all back."""
    nested = await db.begin_nested()
    raw = secrets.token_urlsafe(32)
    password = secrets.token_urlsafe(24)
    db.add(SaasAccountCredential(company_id=COMPANY, owner_user_id=OWNER,
        purpose='reset_password', token_hash=hash_account_credential(raw),
        expires_at=datetime.now(timezone.utc)+timedelta(minutes=5)))
    await db.flush()
    with patch.object(db, 'commit', AsyncMock(side_effect=db.flush)):
        await SaasMembershipService(db).reset_password(raw, password,
            ip_address=None, user_agent='owner-identity-rollback-rehearsal')
        try:
            await SaasMembershipService(db).reset_password(raw, password,
                ip_address=None, user_agent=None)
        except HTTPException as exc:
            assert exc.status_code in (400, 401, 410, 422)
        else:
            raise AssertionError('Setup token could be reused')
        user = await AuthService(db).authenticate_user(COMPANY, 'superadmin', password)
        assert user.id == OWNER
        token, _ = await PlatformAuthService(db).login('superadmin', password,
            mfa_code=None, ip_address=None, user_agent='owner-identity-rollback-rehearsal')
        assert token.operator.id == OPERATOR and '*' in token.operator.permissions
        roles, perms = await effective_platform_access(db, operator)
        assert 'platform_owner' in roles and '*' in perms
        checked = []
        for workspace in await _load_workspaces(db, COMPANY):
            result = await AuthService(db).get_user_permissions(owner, workspace.branch.id, None)
            assert result[0] == ['*']
            checked.append(workspace.spec.key)
        assert len(checked) >= 4
    await nested.rollback()
    db.expire_all()
    return checked


async def main():
    assert settings.environment == 'development' and settings.identity_database == 'platform_core'
    assert owner_link() == (OWNER, OPERATOR)
    assert not settings.uat_auth_bypass_enabled and not settings.qa_access_mode_enabled
    async with PlatformSessionLocal() as db:
        await db.execute(text("SELECT pg_advisory_xact_lock(25102026)"))
        owner = await db.get(User, OWNER)
        pam = await db.get(User, PAM)
        operator = await db.get(PlatformOperator, OPERATOR)
        assert owner.username == operator.username == 'superadmin'
        assert owner.company_id == pam.company_id == COMPANY
        assert pam.username == 'pam.admin' and pam.is_active and pam.deleted_at is None
        assert not operator.mfa_enabled
        others = list((await db.scalars(select(User).where(
            User.id.not_in([OWNER, PAM]), User.is_active.is_(True)))).all())
        other_operators = list((await db.scalars(select(PlatformOperator).where(
            PlatformOperator.id != OPERATOR, PlatformOperator.is_active.is_(True)))).all())
        summary = {'deactivate_users': len(others), 'deactivate_platform_operators': len(other_operators),
                   'preserve': ['pam.admin'], 'owner': 'superadmin'}
        if '--rehearse' in sys.argv:
            before_pam = await pam_digest(db)
            summary['checked_workspaces'] = await rehearsal(db, owner, operator)
            assert before_pam == await pam_digest(db)
            await db.rollback()
            print(json.dumps({**summary, 'rehearsal_rolled_back': True}))
            return
        if '--apply' not in sys.argv:
            print(json.dumps(summary))
            return
        assert os.environ.get('OWNER_BACKUP_VERIFIED') == 'owner-identity-20261025.8OTe8W'
        assert not await db.scalar(select(AuditLog.id).where(AuditLog.action == ACTION).limit(1))
        before_pam = await pam_digest(db)
        await db.execute(text(f'CREATE SCHEMA {ARCHIVE}'))
        for table in TABLES:
            await db.execute(text(f'CREATE TABLE {ARCHIVE}.{table} AS TABLE public.{table}'))
        now = datetime.now(timezone.utc)
        await db.execute(update(User).where(User.id.not_in([OWNER, PAM])).values(
            is_active=False, is_superuser=False, credential_version=User.credential_version+1,
            deactivated_at=now, deactivated_by=OWNER, deactivation_reason=REASON))
        # Existing identities are retained as inactive audit references, not erased.
        await db.execute(text('UPDATE staff_role_assignments SET revoked_at=:now, revoked_by=:owner, '
            'revocation_reason=:reason WHERE user_id NOT IN (:owner,:pam) AND revoked_at IS NULL'),
            {'now': now, 'owner': OWNER, 'pam': PAM, 'reason': REASON})
        await db.execute(update(PlatformOperator).where(PlatformOperator.id != OPERATOR).values(
            is_active=False, is_superuser=False, credential_version=PlatformOperator.credential_version+1))
        await db.execute(text('UPDATE platform_operator_role_assignments SET revoked_at=:now, '
            'revoked_by=:owner, revocation_reason=:reason WHERE operator_id != :owner AND revoked_at IS NULL'),
            {'now': now, 'owner': OPERATOR, 'reason': REASON})
        await db.execute(update(RefreshToken).where(RefreshToken.user_id != PAM,
            RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
        await db.execute(update(PlatformSession).where(PlatformSession.revoked_at.is_(None)).values(
            revoked_at=now, revocation_reason='owner-identity-consolidation'))
        await db.execute(update(SaasAccountCredential).where(SaasAccountCredential.owner_user_id != PAM,
            SaasAccountCredential.used_at.is_(None)).values(used_at=now))
        await db.execute(text('UPDATE user_invitations SET revoked_at=:now WHERE revoked_at IS NULL '
            'AND used_at IS NULL AND (created_user_id IS NULL OR created_user_id != :pam)'),
            {'now': now, 'pam': PAM})
        await db.execute(text('UPDATE platform_operator_invitations SET revoked_at=:now '
            'WHERE revoked_at IS NULL AND accepted_at IS NULL'), {'now': now})
        owner.is_active = True
        owner.is_superuser = True
        owner.deleted_at = None
        owner.credential_version += 1
        owner.hashed_password = hash_password(secrets.token_urlsafe(48))
        owner.password_changed_at = None
        operator.is_active = True
        operator.credential_version += 1
        operator.hashed_password = hash_password(secrets.token_urlsafe(48))
        operator.password_changed_at = None
        operator.failed_login_attempts = 0
        operator.locked_until = None
        await db.flush()
        checked = await rehearsal(db, owner, operator)
        assert before_pam == await pam_digest(db), 'Pam data changed'
        remaining = (await db.scalars(select(User.username).where(User.is_active.is_(True),
            User.deleted_at.is_(None)).order_by(User.username))).all()
        assert list(remaining) == ['pam.admin', 'superadmin']
        remaining_ops = (await db.scalars(select(PlatformOperator.username).where(
            PlatformOperator.is_active.is_(True)))).all()
        assert list(remaining_ops) == ['superadmin']
        raw = secrets.token_urlsafe(32)
        expiry = now + timedelta(hours=24)
        db.add(SaasAccountCredential(company_id=COMPANY, owner_user_id=OWNER,
            purpose='reset_password', token_hash=hash_account_credential(raw), expires_at=expiry))
        summary.update(checked_workspaces=checked, pam_unchanged=True,
            archive=ARCHIVE, expires_at=expiry.isoformat(), active_users=remaining,
            active_platform_profiles=remaining_ops, password_source='single tenant owner identity')
        db.add(AuditLog(company_id=COMPANY, user_id=OWNER, action=ACTION,
            resource='User', resource_id=str(OWNER), new_value=summary))
        # Persist private link before committing so a lost connection does not lose it.
        private = Path('/tmp/uat-owner-setup-20261025.json')
        fd = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as output:
            json.dump({**summary, 'setup_url': 'https://sketchbiz.foodchainservice.com/reset-password#token='+raw}, output)
        await db.commit()
        print(json.dumps(summary, ensure_ascii=False))


asyncio.run(main())
