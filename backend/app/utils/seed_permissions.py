from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Permission

PERMISSIONS: list[dict[str, str]] = [
    {
        "code": "system.company.view",
        "name": "View Company",
        "module": "system",
        "description": "View company settings and profile information.",
    },
    {
        "code": "system.company.edit",
        "name": "Edit Company",
        "module": "system",
        "description": "Edit company settings and profile information.",
    },
    {
        "code": "system.branch.view",
        "name": "View Branches",
        "module": "system",
        "description": "View branch details and configuration.",
    },
    {
        "code": "system.branch.create",
        "name": "Create Branch",
        "module": "system",
        "description": "Create new company branches.",
    },
    {
        "code": "system.branch.edit",
        "name": "Edit Branch",
        "module": "system",
        "description": "Edit existing branch details.",
    },
    {
        "code": "system.user.view",
        "name": "View Users",
        "module": "system",
        "description": "View users and access assignments.",
    },
    {
        "code": "system.user.create",
        "name": "Create User",
        "module": "system",
        "description": "Create new user accounts.",
    },
    {
        "code": "system.user.edit",
        "name": "Edit User",
        "module": "system",
        "description": "Edit existing user accounts.",
    },
    {
        "code": "system.user.delete",
        "name": "Delete User",
        "module": "system",
        "description": "Soft delete user accounts.",
    },
    {
        "code": "system.user.request",
        "name": "Request Branch User",
        "module": "system",
        "description": "Submit and view user access requests for the current branch.",
    },
    {
        "code": "system.user.approve",
        "name": "Approve Branch Users",
        "module": "system",
        "description": "Review and approve user access requests across the company.",
    },
    {
        "code": "system.role.view",
        "name": "View Roles",
        "module": "system",
        "description": "View role definitions and permissions.",
    },
    {
        "code": "system.role.create",
        "name": "Create Role",
        "module": "system",
        "description": "Create new company roles.",
    },
    {
        "code": "system.role.edit",
        "name": "Edit Role",
        "module": "system",
        "description": "Edit existing role definitions.",
    },
    {
        "code": "system.role.delete",
        "name": "Delete Role",
        "module": "system",
        "description": "Delete or archive roles.",
    },
    {
        "code": "pos.sale.view",
        "name": "View POS Sales",
        "module": "pos",
        "description": "View POS transactions and sales history.",
    },
    {
        "code": "pos.sale.create",
        "name": "Create POS Sale",
        "module": "pos",
        "description": "Create new POS sales transactions.",
    },
    {
        "code": "pos.sale.void",
        "name": "Void POS Sale",
        "module": "pos",
        "description": "Void or cancel POS sales transactions.",
    },
    {
        "code": "pos.sale.void.request",
        "name": "Request POS Sale Void",
        "module": "pos",
        "description": "Request manager approval to void POS sales transactions.",
    },
    {
        "code": "pos.discount.apply",
        "name": "Apply Discount",
        "module": "pos",
        "description": "Apply standard discounts at POS.",
    },
    {
        "code": "pos.discount.override",
        "name": "Override Discount",
        "module": "pos",
        "description": "Override discount limits at POS.",
    },
    {
        "code": "pos.refund.create",
        "name": "Create Refund",
        "module": "pos",
        "description": "Process POS refunds.",
    },
    {
        "code": "pos.refund.request",
        "name": "Request Refund",
        "module": "pos",
        "description": "Request manager approval to process POS refunds.",
    },
    {
        "code": "pos.cashier.open_shift",
        "name": "Open Cashier Shift",
        "module": "pos",
        "description": "Open cashier shifts.",
    },
    {
        "code": "pos.cashier.close_shift",
        "name": "Close Cashier Shift",
        "module": "pos",
        "description": "Close cashier shifts.",
    },
    {
        "code": "pos.report.view",
        "name": "View POS Reports",
        "module": "pos",
        "description": "View POS operational reports.",
    },
    {
        "code": "inventory.product.view",
        "name": "View Products",
        "module": "inventory",
        "description": "View product master data.",
    },
    {
        "code": "inventory.product.create",
        "name": "Create Product",
        "module": "inventory",
        "description": "Create new products.",
    },
    {
        "code": "inventory.product.edit",
        "name": "Edit Product",
        "module": "inventory",
        "description": "Edit existing products.",
    },
    {
        "code": "inventory.product.delete",
        "name": "Delete Product",
        "module": "inventory",
        "description": "Delete or archive products.",
    },
    {
        "code": "inventory.stock.view",
        "name": "View Stock",
        "module": "inventory",
        "description": "View stock balances and movements.",
    },
    {
        "code": "inventory.stock.adjust",
        "name": "Adjust Stock",
        "module": "inventory",
        "description": "Adjust stock quantities.",
    },
    {
        "code": "inventory.stock.adjust.request",
        "name": "Request Stock Adjustment",
        "module": "inventory",
        "description": "Adjust stock within policy limits or request manager approval.",
    },
    {
        "code": "inventory.purchase.view",
        "name": "View Purchases",
        "module": "inventory",
        "description": "View purchase documents and status.",
    },
    {
        "code": "inventory.purchase.create",
        "name": "Create Purchase",
        "module": "inventory",
        "description": "Create purchase documents.",
    },
    {
        "code": "inventory.purchase.approve",
        "name": "Approve Purchase",
        "module": "inventory",
        "description": "Approve purchase documents.",
    },
    {
        "code": "inventory.transfer.view",
        "name": "View Transfers",
        "module": "inventory",
        "description": "View inventory transfer documents.",
    },
    {
        "code": "inventory.transfer.create",
        "name": "Create Transfer",
        "module": "inventory",
        "description": "Create inventory transfer documents.",
    },
    {
        "code": "inventory.transfer.approve",
        "name": "Approve Transfer",
        "module": "inventory",
        "description": "Approve inventory transfers.",
    },
    {
        "code": "accounting.report.view",
        "name": "View Accounting Reports",
        "module": "accounting",
        "description": "View accounting and finance reports.",
    },
    {
        "code": "accounting.invoice.view",
        "name": "View Invoices",
        "module": "accounting",
        "description": "View invoices.",
    },
    {
        "code": "accounting.invoice.create",
        "name": "Create Invoice",
        "module": "accounting",
        "description": "Create invoices.",
    },
    {
        "code": "accounting.payment.view",
        "name": "View Payments",
        "module": "accounting",
        "description": "View payment records.",
    },
    {
        "code": "accounting.payment.create",
        "name": "Create Payment",
        "module": "accounting",
        "description": "Create payment records.",
    },
    {
        "code": "accounting.etax.generate",
        "name": "Generate E-Tax",
        "module": "accounting",
        "description": "Generate Thai e-tax documents.",
    },
    {
        "code": "hr.employee.view",
        "name": "View Employees",
        "module": "hr",
        "description": "View employee records.",
    },
    {
        "code": "hr.employee.create",
        "name": "Create Employee",
        "module": "hr",
        "description": "Create employee records.",
    },
    {
        "code": "hr.employee.edit",
        "name": "Edit Employee",
        "module": "hr",
        "description": "Edit employee records.",
    },
    {
        "code": "hr.payroll.view",
        "name": "View Payroll",
        "module": "hr",
        "description": "View payroll records.",
    },
    {
        "code": "hr.payroll.process",
        "name": "Process Payroll",
        "module": "hr",
        "description": "Run payroll processing.",
    },
    {
        "code": "hr.attendance.view",
        "name": "View Attendance",
        "module": "hr",
        "description": "View attendance data.",
    },
    {
        "code": "hr.attendance.edit",
        "name": "Edit Attendance",
        "module": "hr",
        "description": "Edit attendance data.",
    },
    # F&B Module
    {
        "code": "fb.menu.view",
        "name": "View F&B Menu & Sessions",
        "module": "fb",
        "description": "View tables, sessions, orders, kitchen tickets.",
    },
    {
        "code": "fb.order.create",
        "name": "Place F&B Order",
        "module": "fb",
        "description": "Create dining orders and manage sessions.",
    },
    {
        "code": "fb.kitchen.manage",
        "name": "Manage Kitchen Display",
        "module": "fb",
        "description": "Update kitchen ticket status (cooking/done/served).",
    },
    {
        "code": "fb.kitchen.ticket.manage",
        "name": "Manage Kitchen Tickets",
        "module": "fb",
        "description": "View and update kitchen tickets within the assigned branch or station.",
    },
    {
        "code": "fb.table.manage",
        "name": "Manage Tables",
        "module": "fb",
        "description": "Create, update, open and close dining tables.",
    },
    {
        "code": "fb.recipe.manage",
        "name": "Manage Recipes",
        "module": "fb",
        "description": "Create and edit food/drink recipes and ingredients.",
    },
    {
        "code": "fb.report.view",
        "name": "View F&B Reports",
        "module": "fb",
        "description": "View ingredient usage and cost reports.",
    },
    {
        "code": "fb.settings.manage",
        "name": "Manage F&B Settings",
        "module": "fb",
        "description": "Configure F&B module settings, Line Notify, QR tokens.",
    },
    {
        "code": "brand.store.order.create",
        "name": "Create Brand Store Orders",
        "module": "brand",
        "description": "Create orders in brand storefront apps.",
    },
    {
        "code": "brand.store.shift.close",
        "name": "Close Brand Store Shifts",
        "module": "brand",
        "description": "Close shifts and create shift snapshots in brand storefront apps.",
    },
    {
        "code": "brand.store.replenishment.submit",
        "name": "Submit Store Replenishment",
        "module": "brand",
        "description": "Submit store replenishment requests to central operations.",
    },
    {
        "code": "brand.store.delivery.receive",
        "name": "Receive Store Deliveries",
        "module": "brand",
        "description": "Receive delivered goods from central operations.",
    },
    {
        "code": "brand.store.stock.view",
        "name": "View Brand Store Stock",
        "module": "brand",
        "description": "View stock for the user's active brand store branch only.",
    },
    {
        "code": "brand.store.stock.adjust",
        "name": "Adjust Brand Store Stock",
        "module": "brand",
        "description": "Record counts, waste, and adjustments for the user's active brand store branch.",
    },
    {
        "code": "brand.central.raw_stock.view",
        "name": "View Central Raw Stock",
        "module": "brand",
        "description": "View raw-material stock for brand central operations.",
    },
    {
        "code": "brand.central.raw_stock.manage",
        "name": "Manage Central Raw Stock",
        "module": "brand",
        "description": "Receive and adjust raw-material stock for brand central operations.",
    },
    {
        "code": "brand.central.ready_stock.view",
        "name": "View Central Ready Stock",
        "module": "brand",
        "description": "View finished stock that is ready to ship to brand stores.",
    },
    {
        "code": "brand.central.ready_stock.manage",
        "name": "Manage Central Ready Stock",
        "module": "brand",
        "description": "Manage finished stock that is ready to ship to brand stores.",
    },
    {
        "code": "brand.central.production.view",
        "name": "View Central Production",
        "module": "brand",
        "description": "View brand production demand and production batches.",
    },
    {
        "code": "brand.central.production.manage",
        "name": "Manage Central Production",
        "module": "brand",
        "description": "Plan, start, complete, and cancel brand production batches.",
    },
]


async def seed_default_permissions(db: AsyncSession) -> None:
    statement = insert(Permission).values(PERMISSIONS)
    statement = statement.on_conflict_do_nothing(index_elements=["code"])
    await db.execute(statement)
    await db.commit()
