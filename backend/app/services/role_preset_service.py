from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Permission
from app.schemas.role import RolePresetRead, RoleScope


ROLE_PRESET_POLICY_VERSION = "2026-09-11.2"

TAKEAWAY_OWNER_PERMISSIONS = (
    "takeaway.catalog.view",
    "takeaway.catalog.manage",
    "takeaway.sale.view",
    "takeaway.sale.create",
    "takeaway.sale.refund",
    "takeaway.shift.manage",
    "takeaway.kitchen.manage",
    "takeaway.pickup.manage",
    "takeaway.central_order.create",
    "takeaway.central_order.manage",
    "takeaway.production.manage",
    "takeaway.stock.view",
    "takeaway.stock.manage",
    "takeaway.transfer.manage",
    "takeaway.credit.manage",
    "takeaway.report.view",
    "takeaway.import.dry_run",
    "takeaway.import.apply",
    "takeaway.erp.export",
    "takeaway.erp.acknowledge",
)


@dataclass(frozen=True)
class RolePresetPolicy:
    key: str
    name: str
    description: str
    default_scope: RoleScope
    allowed_scopes: tuple[RoleScope, ...]
    is_branch_assignable: bool
    permission_codes: tuple[str, ...]


COMPANY_OWNER_PERMISSION_CODES = (
    "company.kitchen.view",
    "company.kitchen.manage",
    "system.company.view",
    "system.company.edit",
    "system.branch.view",
    "system.branch.create",
    "system.branch.edit",
    "system.device.view",
    "system.device.manage",
    "system.user.view",
    "system.user.create",
    "system.user.edit",
    "system.user.delete",
    "system.user.request",
    "system.user.approve",
    "system.role.view",
    "system.role.create",
    "system.role.edit",
    "system.role.delete",
    "pos.sale.view",
    "pos.sale.create",
    "pos.sale.void",
    "pos.sale.void.request",
    "pos.discount.apply",
    "pos.discount.override",
    "pos.refund.create",
    "pos.refund.request",
    "pos.cashier.open_shift",
    "pos.cashier.close_shift",
    "pos.report.view",
    "inventory.product.view",
    "inventory.product.create",
    "inventory.product.edit",
    "inventory.product.delete",
    "inventory.stock.view",
    "inventory.stock.adjust",
    "inventory.stock.adjust.request",
    "inventory.purchase.view",
    "inventory.purchase.create",
    "inventory.purchase.approve",
    "inventory.transfer.view",
    "inventory.transfer.create",
    "inventory.transfer.approve",
    "accounting.report.view",
    "accounting.invoice.view",
    "accounting.invoice.create",
    "accounting.payment.view",
    "accounting.payment.create",
    "accounting.etax.generate",
    "hr.employee.view",
    "hr.employee.create",
    "hr.employee.edit",
    "hr.payroll.view",
    "hr.payroll.process",
    "hr.attendance.view",
    "hr.attendance.edit",
    "fb.menu.view",
    "fb.order.create",
    "fb.kitchen.manage",
    "fb.kitchen.ticket.manage",
    "fb.table.manage",
    "fb.recipe.manage",
    "fb.report.view",
    "fb.settings.manage",
    "brand.store.order.create",
    "brand.store.shift.close",
    "brand.store.replenishment.submit",
    "brand.store.delivery.receive",
    "brand.store.stock.view",
    "brand.store.stock.adjust",
    "brand.central.raw_stock.view",
    "brand.central.raw_stock.manage",
    "brand.central.ready_stock.view",
    "brand.central.ready_stock.manage",
    "brand.central.production.view",
    "brand.central.production.manage",
) + TAKEAWAY_OWNER_PERMISSIONS


ROLE_PRESET_POLICIES = (
    RolePresetPolicy(
        key="company-owner",
        name="Company Owner",
        description="Company-wide administration, approval, finance, and operational visibility.",
        default_scope="company",
        allowed_scopes=("company",),
        is_branch_assignable=False,
        permission_codes=COMPANY_OWNER_PERMISSION_CODES,
    ),
    RolePresetPolicy(
        key="brand-manager",
        name="Brand Manager",
        description="Brand standards, menu, recipe, inventory, production, and consolidated reports.",
        default_scope="brand",
        allowed_scopes=("brand",),
        is_branch_assignable=False,
        permission_codes=(
            "system.company.view",
            "system.branch.view",
            "system.device.view",
            "system.device.manage",
            "system.user.view",
            "system.role.view",
            "pos.sale.view",
            "pos.report.view",
            "inventory.product.view",
            "inventory.product.create",
            "inventory.product.edit",
            "inventory.stock.view",
            "inventory.stock.adjust",
            "inventory.purchase.view",
            "inventory.purchase.create",
            "inventory.purchase.approve",
            "inventory.transfer.view",
            "inventory.transfer.create",
            "inventory.transfer.approve",
            "fb.menu.view",
            "fb.recipe.manage",
            "fb.report.view",
            "fb.settings.manage",
            "brand.store.stock.view",
            "brand.central.raw_stock.view",
            "brand.central.raw_stock.manage",
            "brand.central.ready_stock.view",
            "brand.central.ready_stock.manage",
            "brand.central.production.view",
            "brand.central.production.manage",
            "takeaway.catalog.view",
            "takeaway.catalog.manage",
            "takeaway.sale.view",
            "takeaway.central_order.manage",
            "takeaway.production.manage",
            "takeaway.stock.view",
            "takeaway.stock.manage",
            "takeaway.transfer.manage",
            "takeaway.credit.manage",
            "takeaway.report.view",
            "takeaway.import.dry_run",
            "takeaway.erp.export",
            "takeaway.erp.acknowledge",
        ),
    ),
    RolePresetPolicy(
        key="branch-manager",
        name="Branch Manager",
        description="Branch sales, shifts, staff requests, stock, and restaurant operations.",
        default_scope="branch",
        allowed_scopes=("branch",),
        is_branch_assignable=True,
        permission_codes=(
            "system.branch.view",
            "system.device.view",
            "system.device.manage",
            "system.user.view",
            "system.user.request",
            "system.role.view",
            "pos.sale.view",
            "pos.sale.create",
            "pos.sale.void",
            "pos.discount.apply",
            "pos.discount.override",
            "pos.refund.create",
            "pos.cashier.open_shift",
            "pos.cashier.close_shift",
            "pos.report.view",
            "inventory.product.view",
            "inventory.stock.view",
            "inventory.stock.adjust",
            "inventory.purchase.view",
            "inventory.purchase.create",
            "inventory.transfer.view",
            "inventory.transfer.create",
            "fb.menu.view",
            "fb.order.create",
            "fb.kitchen.ticket.manage",
            "fb.table.manage",
            "fb.recipe.manage",
            "fb.report.view",
            "fb.settings.manage",
            "brand.store.order.create",
            "brand.store.shift.close",
            "brand.store.replenishment.submit",
            "brand.store.delivery.receive",
            "brand.store.stock.view",
            "brand.store.stock.adjust",
            "takeaway.catalog.view",
            "takeaway.sale.view",
            "takeaway.sale.create",
            "takeaway.sale.refund",
            "takeaway.shift.manage",
            "takeaway.pickup.manage",
            "takeaway.central_order.create",
            "takeaway.stock.view",
            "takeaway.transfer.manage",
            "takeaway.report.view",
        ),
    ),
    RolePresetPolicy(
        key="cashier",
        name="Cashier",
        description="Branch counter sales, standard discounts, receipts, and cashier shifts.",
        default_scope="branch",
        allowed_scopes=("branch", "station"),
        is_branch_assignable=True,
        permission_codes=(
            "pos.sale.view",
            "pos.sale.create",
            "pos.sale.void.request",
            "pos.discount.apply",
            "pos.refund.request",
            "pos.cashier.open_shift",
            "pos.cashier.close_shift",
            "inventory.product.view",
            "inventory.stock.view",
            "takeaway.catalog.view",
            "takeaway.sale.view",
            "takeaway.sale.create",
            "takeaway.shift.manage",
            "takeaway.pickup.manage",
        ),
    ),
    RolePresetPolicy(
        key="kitchen-staff",
        name="Kitchen Staff",
        description="Kitchen display visibility and ticket status updates only.",
        default_scope="station",
        allowed_scopes=("station",),
        is_branch_assignable=True,
        permission_codes=(
            "fb.menu.view",
            "fb.kitchen.ticket.manage",
            "takeaway.kitchen.manage",
        ),
    ),
)


def missing_role_preset_permissions(available_codes: Iterable[str]) -> dict[str, tuple[str, ...]]:
    available = set(available_codes)
    return {
        policy.key: tuple(code for code in policy.permission_codes if code not in available)
        for policy in ROLE_PRESET_POLICIES
        if any(code not in available for code in policy.permission_codes)
    }


def build_role_preset_reads(permissions: Iterable[Permission]) -> list[RolePresetRead]:
    permission_by_code = {permission.code: permission for permission in permissions}
    rows: list[RolePresetRead] = []
    for policy in ROLE_PRESET_POLICIES:
        resolved = [
            permission_by_code[code]
            for code in policy.permission_codes
            if code in permission_by_code
        ]
        missing = [code for code in policy.permission_codes if code not in permission_by_code]
        rows.append(
            RolePresetRead(
                key=policy.key,
                name=policy.name,
                description=policy.description,
                default_scope=policy.default_scope,
                allowed_scopes=list(policy.allowed_scopes),
                is_branch_assignable=policy.is_branch_assignable,
                permission_ids=[permission.id for permission in resolved],
                permission_codes=list(policy.permission_codes),
                missing_permission_codes=missing,
                is_available=not missing,
                policy_version=ROLE_PRESET_POLICY_VERSION,
            )
        )
    return rows


class RolePresetService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_presets(self) -> list[RolePresetRead]:
        permissions = (
            await self.db.scalars(select(Permission).order_by(Permission.code.asc()))
        ).all()
        return build_role_preset_reads(permissions)
