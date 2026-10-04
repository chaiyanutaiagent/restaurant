# WP58 — Retail Offline Recovery and Counter Readiness

Date: 2026-09-22
Environment: Local and UAT only
Production: unchanged and not authorized

## Objective

WP58 completes the Retail Cash Pilot software surface for recovery visibility and Counter readiness without authorizing Retail offline sales. It closes the WP55–WP58 software implementation sequence while preserving physical-device and Production gates.

## Included

- Retail-specific Sync/Recovery Center with `pending`, `syncing`, `needs_review`, and `synced` states.
- Exact Company/Branch/User/business-type isolation for every local pending-sale lookup.
- Legacy local rows without signed context are quarantined and are never auto-sent.
- Per-item Server acknowledgement mapping keeps the original `client_order_id`; missing acknowledgement becomes `needs_review`.
- Browser online events never send a pending sale without an authenticated signed context.
- Retail Counter Readiness extends the existing evidence service with automatic policy/boundary checks and a Retail physical checklist.
- Retail POS links to Recovery and Counter Readiness from its operating shell.
- Existing Restaurant offline and readiness behavior remains available and isolated.

## Explicitly not authorized

- Retail offline payment or offline order finalization.
- Blind automatic retry, changing a client order ID, or deleting unresolved financial evidence.
- Non-cash provider payment, Exchange, live refund, real Tax Invoice or Credit Note.
- Retail Production data-source cutover or any Production flag/deployment.
- Takeaway or Central Kitchen write activation.

## Gate model

| Gate | Expected result |
|---|---|
| Static/type/build and regression | Must pass before UAT candidate |
| Authenticated Retail context and isolation | Must pass |
| Recovery state/item acknowledgement | Must pass in software UAT |
| App rollback/restore and Production identity | Must pass without schema downgrade or Production change |
| Scanner, printer, cash drawer and controlled network | `UNVERIFIED / HOLD` until real device evidence is attached |
| Production | `NO-GO` |

The Batch A software gate may close while the physical gate remains `HOLD`. A browser/API result must never be reported as physical acceptance.
