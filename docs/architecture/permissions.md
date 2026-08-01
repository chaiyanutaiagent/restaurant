# Permission And Role Presets

Restaurant POS uses permission codes as the enforcement layer. Roles are company-scoped bundles of permissions.

## Permission Domains

- `system.*` - ERP core administration
- `inventory.*` - Product, stock, purchase, and transfer operations
- `accounting.*` - Accounting, payments, invoices, and e-tax
- `pos.*` - POS sales, shifts, refunds, discounts, and reports
- `fb.*` - Restaurant/F&B operations
- `brand.*` - Brand storefront apps, replenishment, and delivery receive
- `hr.*` - HR, attendance, and payroll

## Phase 2 Canonical Starter Role Presets

Policy version: `2026-08-01`

The backend owns the preset definitions and exposes resolved permission IDs through
`GET /api/v1/system/role-presets`. The Roles UI consumes that contract and must not keep a separate
permission-code list.

| Preset | Default scope | Allowed scopes | Branch-request compatible | Boundary |
|---|---|---|---|---|
| Company Owner | Company | Company | No | Explicit full tenant permission catalog; no wildcard |
| Brand Manager | Brand | Brand | No | Brand standards, menu, recipe, stock, production, and reports |
| Branch Manager | Branch | Branch | Yes | Branch operations and staff requests; no central admin/approval permissions |
| Cashier | Branch | Branch, Station | Yes | Sale, standard discount, cashier shift, product/stock view |
| Kitchen Staff | Station | Station | Yes | `fb.menu.view` and `fb.kitchen.manage` only |

The endpoint marks a preset unavailable and returns `missing_permission_codes` when the seeded
permission catalog drifts. Clients must not silently create a partial preset.

`is_branch_assignable` remains a compatibility bridge for the existing branch user-access flow.
Company/Brand/Station assignment persistence and enforcement are separate Phase 2 scopes.

Additional roadmap roles such as Company Admin, Area Manager, Service Staff, Kitchen Manager,
Warehouse Staff, Purchasing, Accountant, HR, and Auditor remain deferred until their assignment and
limit contracts are implemented.

## Migration Rule

Keep existing role names working. Add presets as a starting point for new roles; do not rewrite existing company roles automatically unless explicitly requested.
