# WP58 Phase Gate — Retail Recovery, Readiness and Batch A

Date: 2026-09-22
Environment: Local and UAT only
Production: NO-GO

## Decision

**WP58 software gate: PASS. Batch A software gate: PASS. Physical gate: HOLD. Production gate: NO-GO.**

WP55–WP58 now provide the bounded Retail Cash Pilot software flow: signed Retail context, scan-first Catalog, persistent exception states, Server pricing, cash payment/receipt, Hold/Resume, cash Return, Shift Operations, recovery visibility and Counter Readiness. Retail offline sale remains deliberately unavailable.

## Accepted evidence

- Immutable source `527ba6d`; backend/frontend images `wp58-527ba6d`.
- Frontend type/build, focused 32-test Batch A suite and full 504-test backend regression passed.
- Authenticated Retail UAT journey passed and temporary identities/sessions/assignments were disabled or revoked.
- Recovery queue is context-isolated, legacy unscoped data is quarantined and item acknowledgement preserves the original client ID.
- Rollback to WP57 and restore to WP58 passed without schema downgrade.
- Final UAT health/routes passed; Production identities remained unchanged.

## Gate boundary

The software gate may close and WP59/Batch B may begin on Local/UAT. This decision does not authorize:

- scanner, printer, cash-drawer, payment-terminal or controlled-network physical sign-off;
- Retail offline payment, Exchange, live provider refund or payment;
- real Tax Invoice/Credit Note, Loyalty or Production Retail source cutover;
- any Production deploy/flag or Takeaway/Central Kitchen write activation.

Authenticated browser visual inspection of the new Retail recovery/readiness surfaces remains open because no credential/token was transmitted during this run. That limitation does not replace the physical gate and must be retained in follow-up QA evidence.
