# WP57 Phase Gate — Retail Hold, Cash Return and Shift Operations

Date: 2026-09-22  
Environment: Local and UAT only  
Production: NO-GO

## Decision

**Software gate: PASS. Physical gate: HOLD. Production gate: NO-GO.**

WP57 implementation, regression, authenticated UAT, test-persona containment and app-only rollback/restore have passed. Retail remains an online Cash Pilot with Server-backed Hold/Resume, cash Return and Server-authoritative Shift Operations.

## Accepted evidence

- Runtime source `bf36ecf`; final authenticated harness `885ce67`.
- Backend `wp57-bf36ecf`; frontend `wp57-bf36ecf`.
- Retail migration head `p13retail0007`; other boundary heads remained unchanged.
- Hold version/conflict/idempotency, cash Return maker-checker and exact-once stock/payment effects passed.
- Settled-payment Void, Exchange, provider/tax retry and offline Retail sale remained fail-closed.
- Retail cash movement stayed outside the shared journal and used explicit `not_applicable` evidence.
- Temporary personas were disabled in Platform, Retail and Legacy; active Platform refresh sessions were zero.
- Rollback to WP56 and restore to WP57 passed without schema downgrade.
- Production container identities remained unchanged.

## Remaining acceptance

WP58 must cover Retail Offline/Sync Recovery states and Counter Readiness. Physical tests on the target tablet/counter remain mandatory for scanner, printer, cash drawer, PromptPay/payment hardware where applicable, and stateful network loss/recovery. A browser/API pass is not physical-device acceptance.

WP58 may begin on Local/UAT. This decision does not authorize Production deployment, Retail source cutover, live provider transactions, real tax/Credit Note issuance, Exchange, offline Retail authorization, Takeaway/Central Kitchen transaction activation or Hotel PMS work.
