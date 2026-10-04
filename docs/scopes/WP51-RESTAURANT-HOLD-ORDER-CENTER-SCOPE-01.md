# WP51 — Restaurant Hold Draft and Order Center UX

Date: 2026-09-21
Status: **IN PROGRESS — LOCAL/UAT ONLY**

## Objective

Turn the WP44 Server-backed Hold Draft contract into the day-to-day Restaurant POS workspace described by D20–D23 and D29, and make Order Center a searchable, touch-first operational view for desktop and iPad without inventing unsupported lifecycle actions.

## Hold Draft scope

- Server remains the source of truth for shared drafts, claim ownership, version, expiry and audit history.
- Show owner/assignee, originating Counter, shift, location, age/expiry, version, totals, customer/table/queue/note and lifecycle history.
- Search, filter and sort canonical states: `active`, `claimed`, `resumed`, `expired`, `converted`, `cancelled`.
- Support only contracted actions: claim/resume/release, reassign with permission and reason, discard with reason and reopen eligible historical drafts.
- Every mutation keeps idempotency and optimistic version. A `409` displays the winner/current Server state; the Client never merges or silently overwrites.
- Resume revalidates price, tax and availability. Material changes appear as a review diff before explicit acceptance.
- A non-empty cart is never silently replaced. The operator must hold the current cart first, explicitly replace it, or cancel.
- Offline holds are local shadows only. They cannot create payment, tax, stock or kitchen effects and must be reviewed/reconciled after reconnect.

## Order Center scope

- Search by table, queue, customer and order number; filter by canonical session status and source.
- Two-pane list/detail workspace on desktop and iPad, with order/item state, elapsed time, total and customer context.
- Expose only real backend actions: open detail/add order, checkout when bill is requested, and quick-service handoff when contract conditions are met.
- Unsupported transitions are read-only or disabled with a reason.
- Loading, empty, no-result, error, offline, stale and permission-denied states are explicit.
- Interactive controls meet the 44px touch baseline.

## Engineering and evidence gates

- Security, tenant/branch isolation, permission denial, idempotency, stale-version conflict and no-side-effect tests.
- Backend regression plus frontend TypeScript and production/PWA build.
- Browser UAT on desktop and iPad viewport, including conflict, diff review, offline and safe-replace flows.
- Rollback drill and documented UAT evidence before phase closure.
- D20–D23 and D29 may be marked complete only from recorded evidence. `docs/ux-ui` remains reference-only and is not edited or committed.

## Explicit exclusions

- No Production deployment or Production flags.
- No Takeaway/Central Kitchen transaction enablement.
- No Retail data-source change or cutover.
- No live payment-provider refund and no real tax document issuance.
