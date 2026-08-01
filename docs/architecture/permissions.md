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

Policy version: `2026-08-01.2`

The backend owns the preset definitions and exposes resolved permission IDs through
`GET /api/v1/system/role-presets`. The Roles UI consumes that contract and must not keep a separate
permission-code list.

| Preset | Default scope | Allowed scopes | Branch-request compatible | Boundary |
|---|---|---|---|---|
| Company Owner | Company | Company | No | Explicit full tenant permission catalog; no wildcard |
| Brand Manager | Brand | Brand | No | Brand standards, menu, recipe, stock, production, and reports |
| Branch Manager | Branch | Branch | Yes | Branch operations and staff requests; no central admin/approval permissions |
| Cashier | Branch | Branch, Station | Yes | Sale, standard discount, cashier shift, product/stock view |
| Kitchen Staff | Station | Station | Yes | `fb.menu.view` and `fb.kitchen.ticket.manage` only |

The endpoint marks a preset unavailable and returns `missing_permission_codes` when the seeded
permission catalog drifts. Clients must not silently create a partial preset.

`is_branch_assignable` remains a compatibility bridge for the existing branch user-access flow.
Company/Brand/Station assignment persistence and enforcement are implemented by
`P2-SCOPE-ASSIGNMENTS-02`.

## Scoped Role Assignments

`staff_role_assignments` stores an immutable assignment target plus grant/revoke history. A Role
declares its `allowed_scope_types`; the API rejects an assignment when the requested scope is not
allowed by that Role. Branch and Station targets accept only a Branch ID from the client. The server
loads the canonical Company/Brand/Business context, derives the Brand ID, and validates Station keys
against the active Restaurant `branch_settings` connection.

Authorization evaluates active assignments only when issuing or refreshing a token:

- Company applies to every active Branch belonging to the token Company.
- Brand applies only to active Branches mapped to that Brand.
- Branch applies only to its canonical Branch.
- Station applies only to its Branch and normalized Station key.
- Multiple roles are unioned only when each assignment applies to the current context.

Access tokens carry server-owned `station_key`, applicable assignment IDs, and scope types. Refresh
tokens preserve Branch/Station context but re-evaluate active assignments, so a revoked assignment is
removed on refresh or the next Branch switch. Existing `user_branches` permissions remain a
compatibility path and are unioned with applicable scoped assignments; no automatic backfill occurs.

Assignment create/revoke operations require a reason and write actor, target, and before/after values
to the identity audit log. Kitchen ticket access accepts the granular
`fb.kitchen.ticket.manage` permission, locks reads and mutations to the token Station, and does not
grant the legacy `fb.kitchen.manage` permission used by central production.

Additional roadmap roles such as Company Admin, Area Manager, Service Staff, Kitchen Manager,
Warehouse Staff, Purchasing, Accountant, HR, and Auditor remain deferred until their assignment and
limit contracts are implemented.

## Migration Rule

Keep existing role names working. Add presets as a starting point for new roles; do not rewrite
existing company roles or `user_branches` automatically unless explicitly requested.
