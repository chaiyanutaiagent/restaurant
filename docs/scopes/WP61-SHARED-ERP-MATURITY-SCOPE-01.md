# WP61 — Shared ERP Operational and Finance Maturity

Status: LOCAL ENGINEERING GATE PASSED — UAT and combined Batch B gate pending
Environment: Local/UAT only
Production: HOLD

## Objective

Close the Shared ERP usability and control gaps across Company reporting,
inventory, purchasing, accounting and operational exceptions without enabling
real fiscal/provider behavior or weakening Company/Branch authority.

## Planned slices

1. Shared ERP home and readiness summary by Company/Brand/Branch.
2. Purchasing and inventory exception queues with owner, age and safe deep links.
3. Accounting close/readiness, tax-data visibility and evidence states.
4. Maker-checker and server-authoritative action consistency across ERP modules.
5. Shared report filters, empty/error/offline/stale/permission states and
   desktop/tablet responsiveness.
6. Batch B combined regression, authenticated UAT persona matrix and
   rollback/restore for WP59–WP61.

## Local checkpoint delivered

- Added a Server-authoritative, read-only Shared ERP readiness contract and
  Company/Branch-scoped workspace at `/company/erp`.
- Added purchasing, transfer, stock-count, payable and tax exception queues
  with source evidence, owner, age, due date, branch and safe deep links.
- Added current-period finance/tax close readiness while keeping accountant
  sign-off and real fiscal/provider actions visibly on HOLD.
- Enforced distinct maker/checker users for purchase approval, transfer
  approval, tax review/close and manual journal reversal before mutation.
- Added Loading, Empty, Error, Offline, Stale and Permission-denied states plus
  responsive desktop/tablet layout and filters.
- No schema migration or Production flag is introduced by WP61.

## Hard holds

- No real tax filing/document issuance.
- No live payment/refund/provider execution.
- No Retail source cutover.
- No Takeaway/Central Kitchen transaction activation.
- No Hotel PMS scope.
