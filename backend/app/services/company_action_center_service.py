from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import TokenData
from app.models.audit import AuditLog
from app.models.payment_gateway import NotificationLog
from app.models.purchase import PurchaseOrder
from app.models.tax_operations import TaxReconciliationIssue
from app.models.transfer import TransferOrder
from app.models.user import User
from app.models.user_access import UserAccessRequest
from app.schemas.company_foundation import (
    CompanyWorkItemActionRequest,
    CompanyWorkItemListRead,
    CompanyWorkItemRead,
)
from app.services.company_context_service import scoped_branch_ids


SEVERITY_ORDER = {"blocker": 0, "error": 1, "warning": 2, "info": 3}


def _has(current: TokenData, permission: str) -> bool:
    return "*" in current.permissions or permission in current.permissions


def _branch_filter(branch_ids: list[uuid.UUID] | None, column):
    if branch_ids is None:
        return True
    return column.in_(branch_ids)


class CompanyActionCenterService:
    """Read model over existing domain workflows; high-risk execution stays in source modules."""

    def __init__(self, identity_db: AsyncSession, operational_db: AsyncSession):
        self.identity_db = identity_db
        self.operational_db = operational_db

    async def list_items(self, current: TokenData) -> CompanyWorkItemListRead:
        items: list[CompanyWorkItemRead] = []
        branch_ids = await scoped_branch_ids(current, self.operational_db)
        if _has(current, "system.user.approve"):
            rows = (
                await self.identity_db.scalars(
                    select(UserAccessRequest)
                    .where(
                        UserAccessRequest.company_id == current.company_id,
                        UserAccessRequest.status == "pending",
                        _branch_filter(branch_ids, UserAccessRequest.branch_id),
                    )
                    .order_by(UserAccessRequest.requested_at.asc())
                    .limit(100)
                )
            ).all()
            items.extend(
                CompanyWorkItemRead(
                    id=f"user_access:{row.id}",
                    type="user_access_approval",
                    source_app="company_admin",
                    severity="warning",
                    title=f"อนุมัติสิทธิ์พนักงาน {row.first_name} {row.last_name}",
                    company_id=row.company_id,
                    brand_id=row.brand_id,
                    branch_id=row.branch_id,
                    status="open",
                    permission_required="system.user.approve",
                    available_actions=["assign", "acknowledge", "dismiss"],
                    deep_link="/users",
                    unread=True,
                    business_impact=70,
                    created_at=row.requested_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            )

        if _has(current, "inventory.purchase.approve"):
            rows = (
                await self.operational_db.scalars(
                    select(PurchaseOrder)
                    .where(
                        PurchaseOrder.company_id == current.company_id,
                        PurchaseOrder.status == "pending_approval",
                        PurchaseOrder.deleted_at.is_(None),
                        _branch_filter(branch_ids, PurchaseOrder.branch_id),
                    )
                    .order_by(PurchaseOrder.created_at.asc())
                    .limit(100)
                )
            ).all()
            items.extend(
                CompanyWorkItemRead(
                    id=f"purchase_order:{row.id}",
                    type="purchase_order_approval",
                    source_app="erp",
                    severity="warning",
                    title=f"อนุมัติใบสั่งซื้อ {row.po_number}",
                    company_id=row.company_id,
                    branch_id=row.branch_id,
                    status="open",
                    permission_required="inventory.purchase.approve",
                    available_actions=["assign", "acknowledge", "dismiss"],
                    deep_link=f"/purchase/orders/{row.id}",
                    unread=True,
                    business_impact=80,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            )

        if _has(current, "inventory.transfer.approve"):
            rows = (
                await self.operational_db.scalars(
                    select(TransferOrder)
                    .where(
                        TransferOrder.company_id == current.company_id,
                        TransferOrder.status == "pending_approval",
                        _branch_filter(branch_ids, TransferOrder.from_branch_id),
                    )
                    .order_by(TransferOrder.created_at.asc())
                    .limit(100)
                )
            ).all()
            items.extend(
                CompanyWorkItemRead(
                    id=f"transfer_order:{row.id}",
                    type="stock_transfer_approval",
                    source_app="erp",
                    severity="warning",
                    title=f"อนุมัติการโอนสินค้า {row.to_number}",
                    company_id=row.company_id,
                    branch_id=row.from_branch_id,
                    status="open",
                    permission_required="inventory.transfer.approve",
                    available_actions=["assign", "acknowledge", "dismiss"],
                    deep_link=f"/transfer/orders/{row.id}",
                    unread=True,
                    business_impact=75,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            )

        if _has(current, "accounting.tax.view"):
            rows = (
                await self.operational_db.scalars(
                    select(TaxReconciliationIssue)
                    .where(
                        TaxReconciliationIssue.company_id == current.company_id,
                        TaxReconciliationIssue.status == "open",
                        _branch_filter(branch_ids, TaxReconciliationIssue.branch_id),
                    )
                    .order_by(TaxReconciliationIssue.created_at.asc())
                    .limit(100)
                )
            ).all()
            items.extend(
                CompanyWorkItemRead(
                    id=f"tax_issue:{row.id}",
                    type="tax_reconciliation_issue",
                    source_app="erp",
                    severity=row.severity,
                    title=row.message,
                    company_id=row.company_id,
                    branch_id=row.branch_id,
                    status="open",
                    permission_required="accounting.tax.view",
                    available_actions=["assign", "acknowledge", "dismiss"],
                    deep_link="/tax-center",
                    unread=True,
                    business_impact=100 if row.severity == "blocker" else 85,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            )

        if branch_ids is None and (
            _has(current, "system.company.view") or _has(current, "system.company.edit")
        ):
            rows = (
                await self.operational_db.scalars(
                    select(NotificationLog)
                    .where(
                        NotificationLog.company_id == current.company_id,
                        NotificationLog.status.in_(("pending", "failed", "error")),
                    )
                    .order_by(NotificationLog.sent_at.asc())
                    .limit(100)
                )
            ).all()
            items.extend(
                CompanyWorkItemRead(
                    id=f"notification:{row.id}",
                    type="notification_delivery_issue",
                    source_app="integrations",
                    severity="error" if row.status in {"failed", "error"} else "warning",
                    title=row.subject or f"ส่งการแจ้งเตือน {row.event_type} ไม่สำเร็จ",
                    company_id=row.company_id,
                    status="open",
                    permission_required="system.company.view",
                    available_actions=["assign", "acknowledge", "dismiss"],
                    deep_link="/integrations",
                    unread=True,
                    business_impact=80 if row.status in {"failed", "error"} else 60,
                    created_at=row.sent_at,
                    updated_at=row.sent_at,
                )
                for row in rows
            )

        await self._apply_action_overlay(items, current)
        items = [item for item in items if item.status != "dismissed"]
        items.sort(
            key=lambda item: (
                SEVERITY_ORDER[item.severity],
                -item.business_impact,
                item.due_at or item.created_at,
                item.id,
            )
        )
        return CompanyWorkItemListRead(
            items=items,
            total=len(items),
            unread=sum(1 for item in items if item.unread),
            generated_at=datetime.now(timezone.utc),
        )

    async def record_action(
        self,
        current: TokenData,
        work_item_id: str,
        payload: CompanyWorkItemActionRequest,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> CompanyWorkItemRead:
        listing = await self.list_items(current)
        item = next((candidate for candidate in listing.items if candidate.id == work_item_id), None)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work item not found")
        if payload.action not in item.available_actions:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Action is not available for this work item",
            )
        if payload.action == "assign":
            if payload.owner_id is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="owner_id is required")
            owner = await self.identity_db.scalar(
                select(User).where(
                    User.id == payload.owner_id,
                    User.company_id == current.company_id,
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                )
            )
            if owner is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")

        self.identity_db.add(
            AuditLog(
                company_id=current.company_id,
                branch_id=item.branch_id,
                user_id=current.user_id,
                action=f"company.work_item.{payload.action}",
                resource="CompanyWorkItem",
                resource_id=item.id,
                old_value={"status": item.status, "owner_id": str(item.owner_id) if item.owner_id else None},
                new_value={
                    "action": payload.action,
                    "owner_id": str(payload.owner_id) if payload.owner_id else None,
                    "reason": payload.reason,
                },
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        await self.identity_db.commit()
        refreshed = await self.list_items(current)
        result = next((candidate for candidate in refreshed.items if candidate.id == work_item_id), None)
        if result is None and payload.action == "dismiss":
            return item.model_copy(update={"status": "dismissed", "unread": False})
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work item no longer available")
        return result

    async def _apply_action_overlay(
        self,
        items: list[CompanyWorkItemRead],
        current: TokenData,
    ) -> None:
        if not items:
            return
        ids = [item.id for item in items]
        audits = (
            await self.identity_db.scalars(
                select(AuditLog)
                .where(
                    AuditLog.company_id == current.company_id,
                    AuditLog.resource == "CompanyWorkItem",
                    AuditLog.resource_id.in_(ids),
                )
                .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            )
        ).all()
        by_id = {item.id: item for item in items}
        for audit in audits:
            item = by_id.get(audit.resource_id or "")
            if item is None:
                continue
            action = audit.action.rsplit(".", 1)[-1]
            values = audit.new_value or {}
            if action == "assign" and values.get("owner_id"):
                item.owner_id = uuid.UUID(values["owner_id"])
                item.updated_at = audit.created_at
            if audit.user_id != current.user_id:
                continue
            if action == "acknowledge":
                item.status = "acknowledged"
                item.unread = False
                item.updated_at = audit.created_at
            elif action == "dismiss":
                item.status = "dismissed"
                item.unread = False
                item.updated_at = audit.created_at
