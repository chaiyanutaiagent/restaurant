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

## Canonical Starter Role Presets

Current policy version: `2026-08-01.4` (`P3-DEVICE-PAIRING-01` adds scoped device management to
Company Owner, Brand Manager, and Branch Manager; the Phase 2 gate was verified at `2026-08-01.3`.)

The backend owns the preset definitions and exposes resolved permission IDs through
`GET /api/v1/system/role-presets`. The Roles UI consumes that contract and must not keep a separate
permission-code list.

| Preset | Default scope | Allowed scopes | Branch-request compatible | Boundary |
|---|---|---|---|---|
| Company Owner | Company | Company | No | Explicit full tenant permission catalog, including device management; no wildcard |
| Brand Manager | Brand | Brand | No | Brand standards, menu, recipe, stock, production, reports, and scoped devices |
| Branch Manager | Branch | Branch | Yes | Branch operations, staff requests, and Branch devices; no central admin/approval permissions |
| Cashier | Branch | Branch, Station | Yes | Sale, standard discount, approval requests for void/refund, cashier shift, product/stock view |
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

## Manager Approval Sessions

Approval-sensitive operations use separate direct and request permissions. `pos.sale.void.request`,
`pos.refund.request` and `inventory.stock.adjust.request` allow a Branch-scoped employee to initiate
only the corresponding workflow; they do not grant the direct manager operation. A standard POS
discount continues to use `pos.discount.apply`, while an amount above the Branch Cashier ceiling
requires `pos.discount.override` evidence.

An approver must be a different active User in the same Company, hold the direct permission in the
requester's current Branch/Station context and have a Manager PIN. The identity service validates the
PIN and issues a signed two-minute grant bound to Company, Branch, requester, action and a normalized
request fingerprint. The operational transaction consumes the grant once in
`approval_grant_usages`; payload changes, cross-context use and replay are rejected.

Manager PIN hashes and lockout state are identity-owned. Operation audit rows record requester,
approver, approval mode, reason, grant ID and request hash without storing the PIN or approval token.

## Device Identity

`device_registrations` is Identity-owned in legacy and Platform; it is not copied into the Restaurant
operational database. Company Owner, Brand Manager, and Branch Manager presets may view and manage
devices, while Cashier and Kitchen Staff presets do not receive device-administration permissions.

Registration binds a device to a server-resolved Restaurant Branch. Kitchen devices additionally
require a canonical Station from Restaurant Branch settings. A one-time six-digit PIN and equivalent
QR payload expire after ten minutes, are stored only as a hash, lock after repeated failures, and are
consumed under a row lock. Pairing returns a device token, not a User token.

Every device-authenticated request reloads the live registry and verifies Company, Brand, Branch,
device type, Station, credential version, active Brand context, and configured Kitchen Station.
Pairing also issues a high-entropy persistent refresh credential. Identity stores only its keyed SHA-256
hash; Android stores the credential with AES-GCM and an Android Keystore key. Browser deployments use
persistent origin storage as a fallback because web pages cannot access a native secure store or a stable
MAC address. The refresh credential renews expiring access tokens without repeating Pair. Pairing-code
rotation and revoke clear the refresh hash and increment the credential version, so both old access and
refresh credentials fail immediately. The dependency updates `last_seen_at`; lifecycle actions write audit
evidence without persisting a PIN, access token or refresh token.

## Migration Rule

Keep existing role names working. Add presets as a starting point for new roles; do not rewrite
existing company roles or `user_branches` automatically unless explicitly requested.
