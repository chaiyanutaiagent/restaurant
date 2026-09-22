# WP63 — Central Kitchen and Supply Chain UI Activation

Date: 2026-09-22

Environment: Local and UAT only

Production: **NO-GO / unchanged**

## Objective

Activate the existing Company Kitchen and Distribution read models as one
coherent Desktop/Tablet operating experience without opening stock,
production, QC, shipment or recall mutations. The signed Company context and
existing Stock/Transfer ledgers remain authoritative.

## Delivered scope

- Server-generated release stage, freshness, hard holds and readiness checks
  on both Company Kitchen and Company Distribution dashboards.
- Router-level fail-closed guards for every non-read Kitchen and Distribution
  request, including future endpoints added under the same routers.
- Structured `company_kitchen_write_hold` and
  `company_distribution_write_hold` responses.
- Runtime safety validator: Company supply-chain writes can only be enabled on
  an HTTPS `uat-*` development host, and Distribution cannot open before
  Kitchen.
- Central Kitchen UI for canonical ingredients, Brand aliases, aggregate RAW
  stock, Demand, production queue, Brand-separated usage/cost and reports.
- Supply Chain UI for normalized three-POS Demand, shipment/in-transit,
  receive/reject/return history and Module/Brand/Branch reconciliation.
- Shared read-only release panel with Server freshness, readiness/HOLD cards,
  Offline/Stale state and explicit disabled-action explanation.
- Permission-denied/error/loading handling and guarded form submission so an
  Enter key or client event cannot claim a local success while writes are
  closed.
- Navigation between Central Kitchen and Distribution.
- Desktop 1440×900 and Tablet 1024×768 browser coverage.

## Server-authority contract

| Surface | Reads | Mutations |
|---|---|---|
| Company Kitchen | Dashboard and report allowed by signed permission | HTTP 409 while `COMPANY_KITCHEN_WRITES_ENABLED=false` |
| Company Distribution | Dashboard and report allowed by signed permission | HTTP 409 while `COMPANY_DISTRIBUTION_WRITES_ENABLED=false` |
| Production | Flags remain false | Enabling is rejected by runtime validation |
| UAT | Read-only by default | Kitchen may precede Distribution only after a separate owner gate |

The UI mirrors Server state; disabled controls are not the security boundary.

## Readiness/HOLD model

Kitchen exposes Company context, Kitchen/RAW configuration, canonical
ingredient and Brand alias visibility. Opening-lot physical count,
stock-owner sign-off, QC hold/release, recall traceability and physical-device
UAT remain HOLD.

Distribution exposes normalized demand and existing Transfer/Stock-ledger
reconciliation. Kitchen canary, READY stock reconciliation, QC release,
Branch receiver physical UAT and stock-owner sign-off remain HOLD.

Incomplete QC and Recall capabilities are shown as planned/HOLD only. WP63
does not create fake controls, local-only mutation or success confirmation.

## Acceptance evidence

- Backend Kitchen/API regression: 12/12 passed.
- Backend Distribution/API regression: 9/9 passed.
- WP63 runtime safety tests: 4/4 passed.
- Frontend TypeScript: passed.
- Kitchen browser: 2/2 passed at Desktop and Tablet.
- Distribution browser: 2/2 passed at Desktop and Tablet.
- Frontend production build: passed; existing large-chunk warning remains.
- Backend and Frontend immutable local Docker images built successfully:
  `restaurant-pos-backend:wp63-local` and
  `restaurant-pos-frontend:wp63-local`.
- Backend application import passed with 48 route groups.

## Explicit exclusions

- No opening-lot import or real physical count.
- No Kitchen receipt, issue, production, completion, reversal or cancellation.
- No Distribution demand, allocation, dispatch, receipt, reject, return or
  cancellation.
- No active QC, quarantine, release, CAPA, genealogy or recall-case workflow.
- No Chambo real-data cutover.
- No Production flag, Production deployment, live provider or real tax action.

## Next checkpoint

Commit and push the WP63 Local candidate. WP64 may then implement the Public
Customer Experience under the existing owner decision: catalog/session reads
may activate, but ecommerce checkout/order/payment writes remain closed unless
an explicit contract and owner gate authorize them. Combined Batch C UAT,
persona, visual, regression and rollback acceptance occurs after WP64.
