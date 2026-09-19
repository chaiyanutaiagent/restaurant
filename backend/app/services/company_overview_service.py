from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import TokenData
from app.models.branch import Branch
from app.models.device import DeviceRegistration
from app.models.purchase import PurchaseOrder
from app.models.restaurant import DiningSession, KitchenTicket
from app.models.shared_kitchen import CompanyProductionDemand, CompanyProductionOrder
from app.models.tax_operations import TaxReconciliationIssue
from app.models.transfer import TransferOrder
from app.models.user import User, UserBranch
from app.schemas.company_foundation import (
    CompanyOverviewMetricRead,
    CompanyOverviewRead,
    CompanyOverviewSectionRead,
)
from app.schemas.module_access import CompanyModuleAccessRead
from app.services.company_action_center_service import CompanyActionCenterService
from app.services.company_context_service import CompanyContextService, scoped_branch_ids
from app.services.company_operational_status_service import CompanyOperationalStatusService


class CompanyOverviewService:
    def __init__(self, identity_db: AsyncSession, operational_db: AsyncSession):
        self.identity_db = identity_db
        self.operational_db = operational_db

    async def read(self, current: TokenData) -> CompanyOverviewRead:
        now = datetime.now(timezone.utc)
        context_service = CompanyContextService(self.identity_db, self.operational_db)
        context = await context_service.read_context(current)
        access = await context_service.effective_access(current)
        work_items = await CompanyActionCenterService(
            self.identity_db,
            self.operational_db,
        ).list_items(current)
        branch_ids = await scoped_branch_ids(current, self.operational_db)
        operational = await CompanyOperationalStatusService(
            self.identity_db,
            self.operational_db,
        ).read(current.company_id, branch_ids=branch_ids)

        counts = await self._counts(current, branch_ids=branch_ids)
        device_attention = sum(
            operational.summary[state]
            for state in ("offline", "degraded", "pending_sync", "stale", "error")
        )
        sections = [
            self._section(
                module,
                counts=counts,
                device_attention=device_attention,
                permissions=current.permissions,
                now=now,
            )
            for module in access.modules
        ]
        return CompanyOverviewRead(
            context=context,
            task_summary={
                "total": work_items.total,
                "unread": work_items.unread,
                "blocker": sum(1 for item in work_items.items if item.severity == "blocker"),
                "error": sum(1 for item in work_items.items if item.severity == "error"),
                "warning": sum(1 for item in work_items.items if item.severity == "warning"),
            },
            sections=sections,
            generated_at=now,
        )

    async def _counts(
        self,
        current: TokenData,
        *,
        branch_ids: list[uuid.UUID] | None,
    ) -> dict[str, int]:
        company_id = current.company_id
        branch_condition = True if branch_ids is None else Branch.id.in_(branch_ids)
        po_branch = True if branch_ids is None else PurchaseOrder.branch_id.in_(branch_ids)
        transfer_branch = True if branch_ids is None else TransferOrder.from_branch_id.in_(branch_ids)
        tax_branch = True if branch_ids is None else TaxReconciliationIssue.branch_id.in_(branch_ids)
        dining_branch = True if branch_ids is None else DiningSession.branch_id.in_(branch_ids)
        ticket_branch = True if branch_ids is None else KitchenTicket.branch_id.in_(branch_ids)
        device_branch = True if branch_ids is None else DeviceRegistration.branch_id.in_(branch_ids)

        user_count_statement = select(func.count(func.distinct(User.id))).where(
            User.company_id == company_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
        if branch_ids is not None:
            user_count_statement = user_count_statement.join(
                UserBranch,
                UserBranch.user_id == User.id,
            ).where(
                UserBranch.branch_id.in_(branch_ids),
                UserBranch.deleted_at.is_(None),
            )

        values = {
            "branches": await self.identity_db.scalar(
                select(func.count(Branch.id)).where(
                    Branch.company_id == company_id,
                    Branch.deleted_at.is_(None),
                    Branch.is_active.is_(True),
                    branch_condition,
                )
            ),
            "users": await self.identity_db.scalar(user_count_statement),
            "devices": await self.identity_db.scalar(
                select(func.count(DeviceRegistration.id)).where(
                    DeviceRegistration.company_id == company_id,
                    DeviceRegistration.revoked_at.is_(None),
                    device_branch,
                )
            ),
            "purchase_pending": await self.operational_db.scalar(
                select(func.count(PurchaseOrder.id)).where(
                    PurchaseOrder.company_id == company_id,
                    PurchaseOrder.status == "pending_approval",
                    PurchaseOrder.deleted_at.is_(None),
                    po_branch,
                )
            ),
            "transfer_pending": await self.operational_db.scalar(
                select(func.count(TransferOrder.id)).where(
                    TransferOrder.company_id == company_id,
                    TransferOrder.status == "pending_approval",
                    transfer_branch,
                )
            ),
            "tax_open": await self.operational_db.scalar(
                select(func.count(TaxReconciliationIssue.id)).where(
                    TaxReconciliationIssue.company_id == company_id,
                    TaxReconciliationIssue.status == "open",
                    tax_branch,
                )
            ),
            "restaurant_sessions": await self.operational_db.scalar(
                select(func.count(DiningSession.id)).where(
                    DiningSession.company_id == company_id,
                    DiningSession.status == "open",
                    dining_branch,
                )
            ),
            "kitchen_tickets": await self.operational_db.scalar(
                select(func.count(KitchenTicket.id)).where(
                    KitchenTicket.company_id == company_id,
                    KitchenTicket.status.in_(["pending", "cooking", "ready"]),
                    ticket_branch,
                )
            ),
            "production_demands": await self.operational_db.scalar(
                select(func.count(CompanyProductionDemand.id)).where(
                    CompanyProductionDemand.company_id == company_id,
                    CompanyProductionDemand.status == "submitted",
                )
            ),
            "production_orders": await self.operational_db.scalar(
                select(func.count(CompanyProductionOrder.id)).where(
                    CompanyProductionOrder.company_id == company_id,
                    CompanyProductionOrder.status.in_(["planned", "in_progress"]),
                )
            ),
        }
        return {key: int(value or 0) for key, value in values.items()}

    @staticmethod
    def _section(
        module: CompanyModuleAccessRead,
        *,
        counts: dict[str, int],
        device_attention: int,
        permissions: list[str],
        now: datetime,
    ) -> CompanyOverviewSectionRead:
        metrics: list[CompanyOverviewMetricRead]
        permission_set = set(permissions)

        def has(*codes: str) -> bool:
            return "*" in permission_set or bool(permission_set.intersection(codes))

        titles = {
            "erp": "ERP Overview",
            "central_kitchen": "Central Kitchen Overview",
            "restaurant_pos": "Restaurant POS Overview",
            "takeaway_pos": "Takeaway Readiness Overview",
            "retail_pos": "Retail POS Overview",
            "hotel_pms": "Hotel PMS",
        }
        if module.module_key == "erp":
            metrics = []
            if has("system.branch.view"):
                metrics.append(CompanyOverviewMetricRead(key="branches", label="สาขาที่เปิดใช้งาน", value=counts["branches"]))
            if has("system.user.view"):
                metrics.append(CompanyOverviewMetricRead(key="users", label="พนักงานที่เปิดใช้งาน", value=counts["users"]))
            if has("inventory.purchase.view", "inventory.purchase.approve"):
                metrics.append(CompanyOverviewMetricRead(key="purchase_pending", label="ใบสั่งซื้อรออนุมัติ", value=counts["purchase_pending"], severity="warning", deep_link="/purchase/orders"))
            if has("inventory.transfer.view", "inventory.transfer.approve"):
                metrics.append(CompanyOverviewMetricRead(key="transfer_pending", label="โอนสินค้ารออนุมัติ", value=counts["transfer_pending"], severity="warning", deep_link="/transfer/orders"))
            if has("accounting.tax.view", "accounting.report.view"):
                metrics.append(CompanyOverviewMetricRead(key="tax_open", label="ประเด็นภาษีที่ยังเปิด", value=counts["tax_open"], severity="error", deep_link="/tax-center"))
        elif module.module_key == "restaurant_pos":
            metrics = []
            if has("fb.order.create", "fb.table.manage", "fb.report.view"):
                metrics.append(CompanyOverviewMetricRead(key="open_sessions", label="โต๊ะ/บิลที่กำลังเปิด", value=counts["restaurant_sessions"], deep_link="/restaurant/tables"))
            if has("fb.kitchen.ticket.manage", "fb.kitchen.manage"):
                metrics.append(CompanyOverviewMetricRead(key="kitchen_tickets", label="งานครัวที่กำลังดำเนินการ", value=counts["kitchen_tickets"], deep_link="/restaurant/kitchen"))
            if has("system.device.view"):
                metrics.append(CompanyOverviewMetricRead(key="device_attention", label="อุปกรณ์ที่ต้องตรวจ", value=device_attention, severity="warning", deep_link="/devices"))
        elif module.module_key == "central_kitchen":
            metrics = []
            if has("company.kitchen.view", "company.kitchen.manage", "brand.central.production.view", "brand.central.production.manage"):
                metrics.extend([
                    CompanyOverviewMetricRead(key="demands", label="ความต้องการผลิตที่รอแปลง", value=counts["production_demands"], deep_link="/company-kitchen"),
                    CompanyOverviewMetricRead(key="production", label="ใบผลิตที่กำลังดำเนินการ", value=counts["production_orders"], deep_link="/company-kitchen"),
                ])
        elif module.module_key == "retail_pos":
            metrics = [
                CompanyOverviewMetricRead(key="data_source", label="แหล่งข้อมูลปัจจุบัน", value=module.data_source),
            ]
            if has("system.device.view", "pos.sale.view", "pos.sale.create"):
                metrics.append(CompanyOverviewMetricRead(key="device_attention", label="อุปกรณ์ที่ต้องตรวจ", value=device_attention, severity="warning", deep_link="/devices" if has("system.device.view") else None))
        elif module.module_key == "takeaway_pos":
            metrics = [
                CompanyOverviewMetricRead(key="data_source", label="แหล่งข้อมูลปัจจุบัน", value=module.data_source),
                CompanyOverviewMetricRead(key="runtime_ready", label="Runtime พร้อมใช้งาน", value="yes" if module.runtime_ready else "no", severity="warning" if not module.runtime_ready else "info"),
            ]
        else:
            metrics = [
                CompanyOverviewMetricRead(key="readiness", label="สถานะ", value=module.readiness)
            ]

        if not metrics:
            metrics = [
                CompanyOverviewMetricRead(
                    key="access",
                    label="สิทธิ์ในบริบทนี้",
                    value="available" if module.effective_access else "not_available",
                )
            ]

        if not module.effective_access or module.readiness in {"planned", "dark_launch"}:
            state = "disabled"
        elif module.module_key in {"restaurant_pos", "retail_pos", "takeaway_pos"} and device_attention:
            state = "degraded"
        else:
            state = "online"
        return CompanyOverviewSectionRead(
            module_key=module.module_key,
            title=titles[module.module_key],
            readiness=module.readiness,
            data_source=module.data_source,
            status=state,
            metrics=metrics,
            updated_at=module.updated_at or now,
        )
