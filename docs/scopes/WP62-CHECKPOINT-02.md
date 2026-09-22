# WP62 Local Checkpoint — Takeaway Operational UI

Date: 2026-09-22

Decision: **LOCAL ENGINEERING GATE PASS / UAT PENDING**

Production decision: **NO-GO / unchanged**

## Result

Takeaway operational screens are available for Desktop/Tablet product and UX
review. Existing records, catalog, queues, stock, recipes, reports and
reconciliation remain visible according to permissions. Every operational
mutation is protected by one Server-authoritative release gate and the UI
mirrors that state without claiming a successful transaction.

Import dry-run and Cutover preview are the only POST exceptions because they
do not persist operational state. Cutover Execute, public ordering, Counter
sales, shift changes, Kitchen/pickup transitions, stock, production, transfer,
credit, recipe and ERP acknowledgement writes remain closed by default.

## Local evidence

- Backend Takeaway tests: 40/40 passed.
- Browser Takeaway workspace tests: 6/6 passed.
- Frontend TypeScript: passed.
- Frontend production build: passed.
- Backend image: `restaurant-pos-backend:wp62-local`.
- Frontend image: `restaurant-pos-frontend:wp62-local`.
- Diff whitespace gate: passed.

## UAT checkpoint

1. Commit and push the focused WP62 candidate.
2. Capture current UAT images and database backup/checksums.
3. Deploy immutable WP62 images to UAT with
   `TAKEAWAY_UAT_TRANSACTION_WRITES_ENABLED=false`.
4. Verify status contract, representative read routes, `409` on a safe
   synthetic mutation attempt, preview exceptions and public-menu hold state.
5. Verify rollback to the recorded WP61 images and restore WP62.

WP63 may begin after this focused UAT checkpoint unless a hard isolation,
permission, migration, rollback or Server-authority blocker is found. Full
persona/visual/regression/rollback acceptance remains the combined Batch C
gate after WP64.
