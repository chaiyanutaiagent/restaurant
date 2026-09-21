# WP51 — Restaurant Hold Draft and Order Center Implementation

Date: 2026-09-21
Status: **LOCAL ENGINEERING PASS — AWAITING UAT**

## Implemented

### Server/API

- Reused the WP44 Server-backed Hold Draft lifecycle, idempotency, row lock, optimistic version, claim TTL and append-only audit contract without a new migration.
- Hold list/detail now includes display-safe owner, assignee, originating shift number and stock-location name while IDs remain available for audit and mutation contracts.
- Hold audit includes actor display beside the immutable actor ID.
- Order Center session summary now exposes session note, active order numbers, latest order number and updated time.
- Cancelled orders are excluded from Order Center totals and kitchen state counts.

### Restaurant POS Hold workspace

- Added a separate `พักบิลปัจจุบัน` confirmation workspace with Company context inherited from the active session, Counter, shift, location, operator, item quantity and estimated total.
- Added a two-pane Hold workspace with search, canonical filters, sort, selected detail, item list, owner/assignee, Counter, shift/location, age/expiry, version, customer/table/queue/note and Server audit history.
- Contract-backed actions: resume, release own claim, reassign with permission and reason, discard with reason, and reopen eligible history.
- Added a structured revalidation review for price/total/availability changes before explicit acceptance.
- Added a structured `409 draft_conflict` state showing the current Server status/version and a reload action. No merge or last-write-wins path exists.
- Preserved the safe replacement guard: hold current cart first, explicitly replace after destructive confirmation, or return.
- Offline mode remains Local shadow only and communicates that payment, stock, tax and KDS actions are unavailable until review/reconciliation.

### Order Center

- Renamed navigation and workspace to `ศูนย์ออเดอร์`.
- Added search by table, queue, customer, phone and order number; canonical status/source filters; and daily date selection.
- Added summary for ordering, bill requested, ready for handoff and closed.
- Added a two-pane list/detail workspace with source, latest order number, elapsed time, total, kitchen counts, customer/note, order lines and kitchen timeline.
- Only real contract actions are exposed: open detail/add order for open sessions, checkout, and quick-service handoff when ready. Closed/unsupported states are read-only or disabled with a reason.
- Added explicit permission denied, loading, empty, no-result, error, offline and stale states. Mutation actions fail closed while offline.
- Interactive controls meet the 44px touch baseline for desktop and iPad layouts.

## Local engineering evidence

- Backend regression: **PASS — 455 tests, 1 skipped**.
- WP51 focused contract tests: **PASS — 2 tests**.
- Existing WP44 concurrency/no-side-effect tests: **PASS — 4 tests**.
- Frontend TypeScript: **PASS**.
- Frontend production/PWA build: **PASS**.
- `git diff --check`: **PASS**.

## Unchanged safety boundaries

- Hold Draft does not create a Dining Order, KDS ticket, Stock movement, Sale, Payment or tax document.
- Order Center does not introduce a new lifecycle state or unsupported backend mutation.
- No Production deployment or flag change.
- No Takeaway/Central Kitchen transaction enablement, Retail source switch, live provider refund or real tax document.
