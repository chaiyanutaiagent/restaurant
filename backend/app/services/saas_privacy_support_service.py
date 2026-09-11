from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.audit import AuditLog
from app.models.company import Company
from app.models.platform import PlatformTenantProfile, SaasTenantMembership
from app.models.saas_billing import SaasInvoice, SaasPlan, SaasSubscription
from app.models.saas_privacy_support import (
    SaasPrivacyRequest,
    SaasRetentionDecision,
    SaasSupportAccessGrant,
    SaasSupportMessage,
    SaasSupportTicket,
)
from app.schemas.saas_privacy_support import (
    PrivacyRequestCreate,
    PrivacyRequestRead,
    PrivacyRequestUpdate,
    RetentionDecisionCreate,
    RetentionDecisionRead,
    RetentionDecisionUpdate,
    SupportAccessDecision,
    SupportAccessGrantRead,
    SupportAccessRequest,
    SupportContextRead,
    SupportMessageCreate,
    SupportMessageRead,
    SupportTicketCreate,
    SupportTicketRead,
    SupportTicketUpdate,
)
from app.services.platform_service import PlatformTenantService


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SaasPrivacySupportService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID | None = None,
        operator_id: uuid.UUID | None = None,
        restaurant_db: AsyncSession | None = None,
    ):
        self.db = db
        self.user_id = user_id
        self.operator_id = operator_id
        self.restaurant_db = restaurant_db

    async def _owner_membership(self, company_id: uuid.UUID) -> SaasTenantMembership:
        if self.user_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant owner access is required")
        membership = await self.db.scalar(
            select(SaasTenantMembership).where(
                SaasTenantMembership.company_id == company_id,
                SaasTenantMembership.owner_user_id == self.user_id,
            )
        )
        if membership is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SaaS membership not found")
        return membership

    async def create_privacy_request(
        self,
        company_id: uuid.UUID,
        data: PrivacyRequestCreate,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> PrivacyRequestRead:
        membership = await self._owner_membership(company_id)
        row = SaasPrivacyRequest(
            company_id=company_id,
            requester_user_id=self.user_id,
            request_type=data.request_type,
            subject_email=membership.owner_email,
            description=data.description,
            status="submitted",
            identity_verification="authenticated_owner",
            target_at=_now() + timedelta(days=settings.saas_privacy_internal_target_days),
        )
        self.db.add(row)
        await self.db.flush()
        self._audit("saas.privacy.request.create", company_id, "SaasPrivacyRequest", row.id, None, {"request_type": row.request_type, "status": row.status}, "Authenticated owner submission", ip_address, user_agent)
        await self.db.commit()
        return PrivacyRequestRead.model_validate(row)

    async def list_privacy_requests(self, company_id: uuid.UUID) -> list[PrivacyRequestRead]:
        await self._owner_membership(company_id)
        rows = list(await self.db.scalars(select(SaasPrivacyRequest).where(SaasPrivacyRequest.company_id == company_id).order_by(SaasPrivacyRequest.created_at.desc())))
        return [PrivacyRequestRead.model_validate(row) for row in rows]

    async def platform_privacy_requests(self, limit: int = 200) -> list[PrivacyRequestRead]:
        rows = list(await self.db.scalars(select(SaasPrivacyRequest).order_by(SaasPrivacyRequest.created_at.desc()).limit(limit)))
        return [PrivacyRequestRead.model_validate(row) for row in rows]

    async def update_privacy_request(
        self,
        request_id: uuid.UUID,
        data: PrivacyRequestUpdate,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> PrivacyRequestRead:
        row = await self.db.scalar(select(SaasPrivacyRequest).where(SaasPrivacyRequest.id == request_id).with_for_update())
        if row is None:
            raise HTTPException(status_code=404, detail="Privacy request not found")
        allowed = {
            "submitted": {"identity_verified", "in_review", "rejected", "cancelled"},
            "identity_verified": {"in_review", "rejected", "cancelled"},
            "in_review": {"fulfilled", "rejected", "cancelled"},
        }
        if data.status == row.status:
            raise HTTPException(status_code=409, detail="Privacy request already has this status")
        if data.status not in allowed.get(row.status, set()):
            raise HTTPException(status_code=409, detail=f"Invalid privacy request transition from {row.status}")
        old = {"status": row.status}
        row.status = data.status
        row.response_summary = data.response_summary
        row.decision_reason = data.reason.strip()
        row.reviewed_by = self.operator_id
        row.completed_at = _now() if data.status in {"fulfilled", "rejected", "cancelled"} else None
        await self.db.flush()
        self._audit("platform.privacy.request.update", row.company_id, "SaasPrivacyRequest", row.id, old, {"status": row.status}, data.reason, ip_address, user_agent)
        await self.db.commit()
        await self.db.refresh(row)
        return PrivacyRequestRead.model_validate(row)

    async def create_retention_decision(
        self,
        request_id: uuid.UUID,
        data: RetentionDecisionCreate,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> RetentionDecisionRead:
        request = await self.db.get(SaasPrivacyRequest, request_id)
        if request is None:
            raise HTTPException(status_code=404, detail="Privacy request not found")
        if self.operator_id is None:
            raise HTTPException(status_code=403, detail="Platform Owner access is required")
        row = SaasRetentionDecision(
            company_id=request.company_id,
            privacy_request_id=request.id,
            data_category=data.data_category,
            action=data.action,
            rationale=data.rationale,
            retain_until=data.retain_until,
            status="proposed",
            proposed_by=self.operator_id,
        )
        self.db.add(row)
        await self.db.flush()
        self._audit("platform.privacy.retention.propose", row.company_id, "SaasRetentionDecision", row.id, None, {"data_category": row.data_category, "action": row.action, "status": row.status, "execution": "not_authorized"}, data.reason, ip_address, user_agent)
        await self.db.commit()
        return RetentionDecisionRead.model_validate(row)

    async def update_retention_decision(
        self,
        decision_id: uuid.UUID,
        data: RetentionDecisionUpdate,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> RetentionDecisionRead:
        row = await self.db.scalar(select(SaasRetentionDecision).where(SaasRetentionDecision.id == decision_id).with_for_update())
        if row is None:
            raise HTTPException(status_code=404, detail="Retention decision not found")
        if row.status != "proposed":
            raise HTTPException(status_code=409, detail="Retention decision is already final")
        row.status = data.status
        row.decision_reason = data.reason.strip()
        row.decided_by = self.operator_id
        row.decided_at = _now()
        self._audit("platform.privacy.retention.decide", row.company_id, "SaasRetentionDecision", row.id, {"status": "proposed"}, {"status": row.status, "execution": "not_authorized"}, data.reason, ip_address, user_agent)
        await self.db.commit()
        await self.db.refresh(row)
        return RetentionDecisionRead.model_validate(row)

    async def retention_decisions(self, request_id: uuid.UUID) -> list[RetentionDecisionRead]:
        rows = list(await self.db.scalars(select(SaasRetentionDecision).where(SaasRetentionDecision.privacy_request_id == request_id).order_by(SaasRetentionDecision.created_at)))
        return [RetentionDecisionRead.model_validate(row) for row in rows]

    async def create_ticket(
        self,
        company_id: uuid.UUID,
        data: SupportTicketCreate,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SupportTicketRead:
        await self._owner_membership(company_id)
        row = SaasSupportTicket(
            ticket_number=f"SUP-{_now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}",
            company_id=company_id,
            requester_user_id=self.user_id,
            category=data.category,
            priority=data.priority,
            status="open",
            subject=data.subject,
        )
        self.db.add(row)
        await self.db.flush()
        self.db.add(SaasSupportMessage(ticket_id=row.id, company_id=company_id, sender_type="tenant_owner", sender_user_id=self.user_id, sender_operator_id=None, body=data.initial_message))
        self._audit("saas.support.ticket.create", company_id, "SaasSupportTicket", row.id, None, {"ticket_number": row.ticket_number, "category": row.category, "priority": row.priority}, "Authenticated owner support request", ip_address, user_agent)
        await self.db.commit()
        return await self.ticket(row.id, company_id=company_id)

    async def tickets(self, company_id: uuid.UUID | None = None, limit: int = 200) -> list[SupportTicketRead]:
        if company_id is not None:
            await self._owner_membership(company_id)
        statement = select(SaasSupportTicket).order_by(SaasSupportTicket.created_at.desc()).limit(limit)
        if company_id is not None:
            statement = statement.where(SaasSupportTicket.company_id == company_id)
        rows = list(await self.db.scalars(statement))
        return [await self._ticket_read(row) for row in rows]

    async def ticket(self, ticket_id: uuid.UUID, *, company_id: uuid.UUID | None = None) -> SupportTicketRead:
        row = await self.db.get(SaasSupportTicket, ticket_id)
        if row is None or (company_id is not None and row.company_id != company_id):
            raise HTTPException(status_code=404, detail="Support ticket not found")
        if company_id is not None:
            await self._owner_membership(company_id)
        return await self._ticket_read(row)

    async def add_message(
        self,
        ticket_id: uuid.UUID,
        data: SupportMessageCreate,
        *,
        company_id: uuid.UUID | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SupportMessageRead:
        ticket = await self.db.get(SaasSupportTicket, ticket_id)
        if ticket is None or (company_id is not None and ticket.company_id != company_id):
            raise HTTPException(status_code=404, detail="Support ticket not found")
        if company_id is not None:
            await self._owner_membership(company_id)
        if ticket.status == "closed":
            raise HTTPException(status_code=409, detail="Closed support ticket cannot receive messages")
        sender_type = "tenant_owner" if company_id is not None else "platform_operator"
        row = SaasSupportMessage(
            ticket_id=ticket.id,
            company_id=ticket.company_id,
            sender_type=sender_type,
            sender_user_id=self.user_id if company_id is not None else None,
            sender_operator_id=self.operator_id if company_id is None else None,
            body=data.body,
        )
        self.db.add(row)
        await self.db.flush()
        self._audit(f"{'saas' if company_id is not None else 'platform'}.support.message.create", ticket.company_id, "SaasSupportMessage", row.id, None, {"ticket_id": str(ticket.id), "sender_type": sender_type}, "Support conversation", ip_address, user_agent)
        await self.db.commit()
        return SupportMessageRead.model_validate(row)

    async def update_ticket(
        self,
        ticket_id: uuid.UUID,
        data: SupportTicketUpdate,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SupportTicketRead:
        row = await self.db.scalar(select(SaasSupportTicket).where(SaasSupportTicket.id == ticket_id).with_for_update())
        if row is None:
            raise HTTPException(status_code=404, detail="Support ticket not found")
        old = {"status": row.status, "priority": row.priority}
        row.status = data.status
        row.priority = data.priority
        row.assigned_operator_id = self.operator_id
        row.closed_at = _now() if data.status == "closed" else None
        self._audit("platform.support.ticket.update", row.company_id, "SaasSupportTicket", row.id, old, {"status": row.status, "priority": row.priority}, data.reason, ip_address, user_agent)
        await self.db.commit()
        await self.db.refresh(row)
        return await self._ticket_read(row)

    async def request_access(
        self,
        ticket_id: uuid.UUID,
        data: SupportAccessRequest,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SupportAccessGrantRead:
        ticket = await self.db.get(SaasSupportTicket, ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Support ticket not found")
        if data.duration_minutes > settings.saas_support_access_max_minutes:
            raise HTTPException(status_code=422, detail="Support access duration exceeds configured maximum")
        existing = await self.db.scalar(
            select(SaasSupportAccessGrant).where(
                SaasSupportAccessGrant.ticket_id == ticket_id,
                SaasSupportAccessGrant.requested_by_operator_id == self.operator_id,
                SaasSupportAccessGrant.status.in_(["pending", "approved"]),
            ).order_by(SaasSupportAccessGrant.created_at.desc())
        )
        if existing is not None and (existing.status == "pending" or existing.expires_at is None or existing.expires_at > _now()):
            raise HTTPException(status_code=409, detail="An active support access request already exists")
        row = SaasSupportAccessGrant(
            ticket_id=ticket.id,
            company_id=ticket.company_id,
            requested_by_operator_id=self.operator_id,
            requested_scopes=data.requested_scopes,
            purpose=data.purpose.strip(),
            duration_minutes=data.duration_minutes,
            status="pending",
        )
        self.db.add(row)
        await self.db.flush()
        self._audit("platform.support.access.request", row.company_id, "SaasSupportAccessGrant", row.id, None, {"ticket_id": str(ticket.id), "requested_scopes": row.requested_scopes, "duration_minutes": row.duration_minutes}, data.reason, ip_address, user_agent)
        await self.db.commit()
        return SupportAccessGrantRead.model_validate(row)

    async def decide_access(
        self,
        company_id: uuid.UUID,
        grant_id: uuid.UUID,
        data: SupportAccessDecision,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SupportAccessGrantRead:
        await self._owner_membership(company_id)
        row = await self.db.scalar(select(SaasSupportAccessGrant).where(SaasSupportAccessGrant.id == grant_id, SaasSupportAccessGrant.company_id == company_id).with_for_update())
        if row is None:
            raise HTTPException(status_code=404, detail="Support access grant not found")
        if row.status != "pending":
            raise HTTPException(status_code=409, detail="Support access request is already decided")
        now = _now()
        row.status = data.decision
        row.decided_by_user_id = self.user_id
        row.decision_reason = data.reason.strip()
        row.decided_at = now
        row.expires_at = now + timedelta(minutes=row.duration_minutes) if data.decision == "approved" else None
        self._audit("saas.support.access.decide", company_id, "SaasSupportAccessGrant", row.id, {"status": "pending"}, {"status": row.status, "expires_at": row.expires_at.isoformat() if row.expires_at else None}, data.reason, ip_address, user_agent)
        await self.db.commit()
        await self.db.refresh(row)
        return SupportAccessGrantRead.model_validate(row)

    async def revoke_access(
        self,
        grant_id: uuid.UUID,
        reason: str,
        *,
        company_id: uuid.UUID | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SupportAccessGrantRead:
        if company_id is not None:
            await self._owner_membership(company_id)
        filters = [SaasSupportAccessGrant.id == grant_id]
        if company_id is not None:
            filters.append(SaasSupportAccessGrant.company_id == company_id)
        row = await self.db.scalar(select(SaasSupportAccessGrant).where(*filters).with_for_update())
        if row is None:
            raise HTTPException(status_code=404, detail="Support access grant not found")
        if row.status != "approved" or row.expires_at is None or row.expires_at <= _now():
            raise HTTPException(status_code=409, detail="Only active support access can be revoked")
        row.status = "revoked"
        row.revoked_at = _now()
        row.revoked_by_type = "tenant_owner" if company_id is not None else "platform_operator"
        row.revoke_reason = reason.strip()
        self._audit(f"{'saas' if company_id is not None else 'platform'}.support.access.revoke", row.company_id, "SaasSupportAccessGrant", row.id, {"status": "approved"}, {"status": "revoked", "revoked_by_type": row.revoked_by_type}, reason, ip_address, user_agent)
        await self.db.commit()
        await self.db.refresh(row)
        return SupportAccessGrantRead.model_validate(row)

    async def support_context(
        self,
        grant_id: uuid.UUID,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SupportContextRead:
        row = await self.db.scalar(select(SaasSupportAccessGrant).where(SaasSupportAccessGrant.id == grant_id).with_for_update())
        if row is None or row.requested_by_operator_id != self.operator_id:
            raise HTTPException(status_code=404, detail="Support access grant not found")
        now = _now()
        if row.status != "approved" or row.expires_at is None or row.expires_at <= now:
            raise HTTPException(status_code=403, detail="Approved, unexpired Tenant support access is required")
        company = await self.db.get(Company, row.company_id)
        if company is None:
            raise HTTPException(status_code=404, detail="Company not found")
        context: dict[str, object] = {}
        scopes = set(row.requested_scopes)
        if "account_state" in scopes:
            membership = await self.db.scalar(select(SaasTenantMembership).where(SaasTenantMembership.company_id == row.company_id))
            context["account_state"] = {"company_id": str(company.id), "company_name": company.name, "is_active": company.is_active, "membership_status": membership.status if membership else "legacy"}
        if "saas_controls" in scopes:
            profile = await self.db.scalar(select(PlatformTenantProfile).where(PlatformTenantProfile.company_id == row.company_id))
            context["saas_controls"] = {"plan_code": profile.plan_code if profile else "starter", "feature_flags": dict(profile.feature_flags) if profile else {}, "plan_limits": dict(profile.plan_limits) if profile else {}}
        if "billing_state" in scopes:
            subscription = await self.db.scalar(select(SaasSubscription).where(SaasSubscription.company_id == row.company_id))
            plan = await self.db.get(SaasPlan, subscription.plan_id) if subscription else None
            invoice_rows = (await self.db.execute(select(SaasInvoice.status, func.count(SaasInvoice.id)).where(SaasInvoice.company_id == row.company_id).group_by(SaasInvoice.status))).all()
            context["billing_state"] = {"plan_code": plan.code if plan else None, "subscription_status": subscription.status if subscription else None, "invoice_counts": {key: count for key, count in invoice_rows}, "collection_available": False}
        if "aggregate_usage" in scopes:
            if self.restaurant_db is None:
                raise HTTPException(status_code=503, detail="Aggregate usage service is unavailable")
            usage = await PlatformTenantService(self.db, restaurant_db=self.restaurant_db, operator_id=self.operator_id, emit_reference_events=False).current_usage(row.company_id)
            context["aggregate_usage"] = {"usage": usage.usage, "limit_state": {key: value.model_dump(mode="json") for key, value in usage.limit_state.items()}, "attention_codes": usage.attention_codes, "last_activity_at": usage.last_activity_at.isoformat() if usage.last_activity_at else None}
        row.last_accessed_at = now
        self._audit("platform.support.context.view", row.company_id, "SaasSupportAccessGrant", row.id, None, {"ticket_id": str(row.ticket_id), "scopes": sorted(scopes)}, "Tenant-approved support context view", ip_address, user_agent)
        await self.db.commit()
        return SupportContextRead(grant_id=row.id, company_id=row.company_id, ticket_id=row.ticket_id, expires_at=row.expires_at, scopes=sorted(scopes), context=context)

    async def _ticket_read(self, row: SaasSupportTicket) -> SupportTicketRead:
        messages = list(await self.db.scalars(select(SaasSupportMessage).where(SaasSupportMessage.ticket_id == row.id).order_by(SaasSupportMessage.created_at)))
        grants = list(await self.db.scalars(select(SaasSupportAccessGrant).where(SaasSupportAccessGrant.ticket_id == row.id).order_by(SaasSupportAccessGrant.created_at.desc())))
        base = SupportTicketRead.model_validate(row)
        base.messages = [SupportMessageRead.model_validate(message) for message in messages]
        base.access_grants = [SupportAccessGrantRead.model_validate(grant) for grant in grants]
        return base

    def _audit(
        self,
        action: str,
        company_id: uuid.UUID,
        resource: str,
        resource_id: uuid.UUID,
        old_value: dict | None,
        new_value: dict,
        reason: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        self.db.add(AuditLog(company_id=company_id, user_id=self.user_id or self.operator_id, action=action, resource=resource, resource_id=str(resource_id), old_value=old_value, new_value={**new_value, "reason": reason}, ip_address=ip_address, user_agent=user_agent))
