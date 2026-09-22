# WP61 Local Checkpoint — Shared ERP Maturity

Date: 2026-09-22

Decision: LOCAL ENGINEERING GATE PASS; UAT and combined Batch B gate pending

Production: NO-GO / unchanged

## Delivered

- Server-authoritative `GET /api/v1/company/erp/readiness` read model scoped by
  the signed Company/Brand/Branch context and explicit ERP permissions.
- Responsive Shared ERP workspace with readiness areas, exception filters,
  owner/age/due/evidence/deep-link details, finance close readiness, freshness
  and Loading/Empty/Error/Offline/Stale/Permission-denied states.
- Distinct maker/checker enforcement for PO approval, transfer approval, tax
  review/close and manual journal reversal. The checks execute before stock,
  period or journal mutation.
- Real tax documents/e-Tax, live payment/refund provider, accountant sign-off,
  Retail source cutover and Takeaway/Central Kitchen Production writes remain
  explicit read-only HOLD controls.

## Local evidence

- Focused Company/ERP/Tax regression: 59/59 pass.
- Full backend regression and compile: 534/534 pass.
- WP61 authority/UX contract tests: 8/8 pass.
- Backend application import and Shared ERP route registration: pass (48 route
  groups loaded).
- Frontend TypeScript: pass.
- Frontend production build and Docker backend/frontend image build: pass.
- Git diff whitespace gate: pass.

The existing developer database is behind the WP60 tenant migration and is not
used as WP61 runtime evidence. WP61 adds no migration. UAT already has the WP60
schema head and is the next authorized runtime checkpoint.

## Next gate

1. Commit and push the WP61 Local candidate to the restaurant repository.
2. Capture a fresh UAT backup and immutable rollback identities.
3. Deploy only UAT, keep all Production and real-provider flags disabled.
4. Run the authenticated Tenant persona matrix and WP59–WP61 Combined Batch B
   regression, visual/device states, migration status and rollback/restore.
5. Record a Batch B Phase Gate before starting Batch C.
