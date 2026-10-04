# WP62 — Takeaway Operational UI Activation

Date: 2026-09-22
Environment: Local/UAT only
Production: HOLD / unchanged
State: Local Engineering Gate passed; UAT checkpoint pending

## Objective

Activate the existing Takeaway workspaces as a safe operational UI for product
and UX review without authorizing real Takeaway transactions, Chambo real data,
live payment/tax providers, Production activation or Owner/Canary sign-off.

## Delivered surfaces

- Takeaway dashboard and Store, Central and Admin navigation.
- Counter catalog/cart, shifts, Kitchen, pickup queue, branch stock and central
  ordering in Server-backed read mode.
- Central orders, production, shared stock, transfers, credits, recipes,
  replenishment, ERP reconciliation and reports in Server-backed read mode.
- Customer ordering menu remains visible for UX review but cannot create an
  order while the release gate is closed.
- Chambo import dry-run and Cutover preview remain available because they do
  not persist operational data. Cutover Execute remains disabled.

## Server-authoritative write contract

`TAKEAWAY_UAT_TRANSACTION_WRITES_ENABLED` defaults to `false` and is rejected
unless all of the following are true:

1. `ENVIRONMENT=development`.
2. `TAKEAWAY_FEATURE_ENABLED=true`.
3. `SAAS_PUBLIC_BASE_URL` is HTTPS and uses a `uat-*` hostname.

All Takeaway POST/PATCH/PUT/DELETE routes return `409 takeaway_write_hold`
while the gate is closed, except these explicitly non-mutating previews:

- `POST /api/v1/takeaway/imports/dry-run`
- `POST /api/v1/takeaway/cutover/preview`

The UI reads the same Server status contract, exposes `dark_launch` or
`uat_synthetic`, disables transaction controls and fails closed if the status
cannot be read. The browser cannot independently activate writes.

## State matrix

| Surface | Read | Write in default UAT | Notes |
|---|---:|---:|---|
| Dashboard/catalog/reports/history | Yes | No | Server-backed |
| Counter/shift/Kitchen/pickup | Yes | No | Controls visible but disabled |
| Store/central stock and ordering | Yes | No | No stock or order mutation |
| Production/transfers/credits/ERP ack | Yes | No | Dark-launch review only |
| Recipes/replenishment | Yes | No | Existing values remain visible |
| Customer public menu | Yes | No | Clear not-open-for-orders state |
| Import dry-run | Yes | Preview only | No persistence |
| Cutover preview | Yes | Preview only | Execute remains HOLD |

## Hard holds

- Real Takeaway transactions or real customer use.
- Chambo real-data import/cutover.
- Live payment, refund, tax or fiscal-provider behavior.
- Production deployment or feature activation.
- Physical printer/cash/PromptPay/network-loss acceptance.
- Owner/Canary approval.

## Acceptance evidence

- Takeaway backend focused regression: 40/40 passed.
- Takeaway browser workspace tests, including closed-gate controls: 6/6 passed.
- Frontend TypeScript and production build: passed.
- Immutable local backend/frontend image builds: passed.
- Git whitespace check: passed.
