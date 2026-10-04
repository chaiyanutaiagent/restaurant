# WP52 — Restaurant Cancel, Discount, Refund and Receipt Center Implementation

Date: 2026-09-22
Status: **LOCAL/UAT PASS — PHASE GATE CLOSED**

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
- WP43–WP52 focused Python suite in an isolated Docker test image: **PASS — 60 tests**.
- Full backend regression: **PASS — 460 tests, 1 skipped**.
- Git whitespace validation: **PASS**.
- Local containers were rebuilt and passed health inspection.

## UAT result

- Immutable WP52 frontend and backend images are deployed to `restaurant-pos-uat-drill` only.
- WP43, WP45 and WP46 Server/API smokes pass on UAT.
- Formal `uat.branch-manager` browser UAT passes POS loading, Discount, paired-Counter Bill Center, safe Void routing, Cancellation/Waste approval, Refund quote/approval and receipt states.
- The first UAT smoke found and closed a legacy direct-offline-submit bypass; signed WP47 sync remains the only offline mutation path.
- Application-only rollback to WP51 completed in 13 seconds and restore to WP52 completed in 12 seconds.
- The browser-compatibility correction replaced unsupported `prompt`/`confirm` device actions with accessible in-app dialogs and added a direct one-time pairing route.
- The final frontend-only rollback/restore each completed in 1 second, with paired device and Staff session retained.

## UAT deployment

- Frontend `restaurant-pos-frontend:wp52-0d0e021` was built with `VITE_REFUND_UAT_SIMULATOR=true`; the Docker default remains `false`.
- Backend `restaurant-pos-backend:wp52-e4e3ad9` includes the direct-offline-submit correction and final smoke harness.
- Only `restaurant-pos-uat-drill` was updated with the existing WP43/WP45/WP46 UAT/Sandbox flags.
- Production identities and flags remained unchanged.

## Boundaries still closed

- Production deployment and flags.
- Live provider refunds and real tax/Credit Note issuance.
- Takeaway/Central Kitchen transaction activation.
- Retail data-source change.
- Atomic exchange and priced modifiers.

Scope and action matrix: [WP52-RESTAURANT-CANCEL-DISCOUNT-REFUND-RECEIPT-SCOPE-01.md](./WP52-RESTAURANT-CANCEL-DISCOUNT-REFUND-RECEIPT-SCOPE-01.md)

UAT plan: [WP52-UAT-PLAN-03.md](./WP52-UAT-PLAN-03.md)

UAT evidence: [WP52-UAT-EVIDENCE-04.md](./WP52-UAT-EVIDENCE-04.md)

Phase gate: [WP52-PHASE-GATE-05.md](./WP52-PHASE-GATE-05.md)
