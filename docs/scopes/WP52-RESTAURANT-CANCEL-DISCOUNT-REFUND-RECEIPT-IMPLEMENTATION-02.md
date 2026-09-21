# WP52 — Restaurant Cancel, Discount, Refund and Receipt Center Implementation

Date: 2026-09-21
Status: **LOCAL ENGINEERING GATE PASS — UAT PENDING**

## Delivered composition

- Added a two-pane Bill & Receipt Center for up to 100 current-shift sales with search, status filter, freshness indicator, receipt detail, payment/refund summary and touch-safe actions.
- Void is enabled only when the sale is `completed` and every positive payment leg is `authorized` or `pending`; settled/unknown payments visibly route to Refund.
- Refund uses the WP46 quote/execute workspace only. Legacy full/partial refund Client methods and UI, whose endpoints return HTTP 410, were removed.
- Atomic exchange remains disabled with an explicit missing-contract explanation.
- Bill discount now opens a dedicated amount/percent workspace with Cashier and hard branch limits, Manager/offline guidance and a Server-authority statement.
- Structured reason is intentionally absent for ordinary discounts because the current contract does not persist it. Approval reasons remain audited for overrides.
- Restaurant cancellation now uses the reactive online state, 44px touch controls and the WP45 Server preview for kitchen stage, bill impact, affected items, waste lines, blockers and maker-checker.
- Manager approval now shows an action/reason summary before username/PIN and retains the one-time, two-minute Server token flow.
- The Refund Sandbox simulator is guarded by `VITE_REFUND_UAT_SIMULATOR=true`; Docker images default it to `false`.

## Authority retained

- WP43 calculates and locks price, discount, tax and approval hashes on the Server.
- WP45 controls cancellation stage, bill impact, waste readiness, KDS event and append-only audit.
- WP46 controls refund quote, remaining balance, original-payment allocation, provider state, stock disposition and synthetic UAT tax link.
- The Client neither invents approval evidence nor reports a transaction as successful before the Server responds.

## Local gate evidence

- Frontend TypeScript: **PASS**.
- Frontend production/PWA build with the Sandbox simulator defaulted off: **PASS**.
- WP43–WP52 focused Python suite in an isolated Docker test image: **PASS — 59 tests**.
- Git whitespace validation: **PASS**.
- Local containers were rebuilt for visual inspection; formal visual UAT remains pending because the local browser reached the login gate and no credential was transmitted.

## UAT candidate plan

- Build immutable backend/frontend images from the WP52 feature commit.
- Build the UAT frontend with `VITE_REFUND_UAT_SIMULATOR=true`; retain the Production default `false`.
- Deploy only to `restaurant-pos-uat-drill` with the existing WP43/WP45/WP46 UAT/Sandbox flags.
- Verify Desktop 1440×900 and iPad 1024×768, including no overflow and 44px controls.
- Exercise Bill Center search/filter/detail, safe Void gating, discount threshold/approval, cancellation stage/Waste preview, Refund quote/provider recovery and synthetic `NON-FISCAL` tax state.
- Re-run API smokes, confirm Production identities unchanged and rehearse app-image rollback before closing the phase gate.

## Boundaries still closed

- Production deployment and flags.
- Live provider refunds and real tax/Credit Note issuance.
- Takeaway/Central Kitchen transaction activation.
- Retail data-source change.
- Atomic exchange and priced modifiers.

Scope and action matrix: [WP52-RESTAURANT-CANCEL-DISCOUNT-REFUND-RECEIPT-SCOPE-01.md](./WP52-RESTAURANT-CANCEL-DISCOUNT-REFUND-RECEIPT-SCOPE-01.md)
