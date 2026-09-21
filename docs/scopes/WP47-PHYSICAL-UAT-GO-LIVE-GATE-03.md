# WP47 — Physical UAT and Go-live Gate

Date: 2026-09-21
Scope: Restaurant POS UAT only
Production status: **NO-GO — unchanged**

## Gate A — Engineering readiness

Implemented:

- Server-authoritative pricing, VAT, stock, shift and permission validation before an offline-originated sale becomes canonical.
- UAT-only offline kill switch with explicit Company and Branch allow-lists plus paired Counter binding.
- Cash/THB only while offline. PromptPay, provider payments, refunds, cancellations, approvals, tax documents and shift close remain online-only.
- AES-GCM local Outbox with a non-extractable Web Crypto key, authenticated encryption, schema version, operation ID, idempotency key, request hash and per-device/per-shift sequence.
- Server lifecycle: `pending_sync → syncing → server_acknowledged → reconciled`; exceptional states: `needs_review`, `rejected`, `quarantined`, `unknown`.
- Inquiry-before-replay for unknown outcome, bounded exponential backoff, exactly-once client identity and server receipts.
- Server export/inquiry remains available when the offline processing kill switch is disabled.
- Seven-day default retention for reconciled local/server evidence; no UI delete action for active or exceptional records.
- Physical UAT evidence API/UI with automatic and manual checks, secret filtering, defect severity and maker-checker sign-off.
- Production validator rejects both Offline processing and Physical UAT evidence flags.

Automated evidence completed locally:

- Frontend TypeScript check: pass.
- Frontend production build: pass.
- Backend unit regression: 438 passed, 1 skipped.
- WP47 focused tests: 10 passed.
- WAP offline regression: 9 passed.
- Blank database migration `upgrade → downgrade → upgrade`: pass.

UAT evidence attached to application commit `b329d2c` with smoke harness commit `e2b8101`:

- Verified pre-deploy backup for five databases, Redis metadata and uploads.
- UAT deployment and migration to `wp47offline0023 (head)` completed.
- Public API readiness and HTTPS response-policy checks passed.
- Automated smoke passed with 100 offline cash orders, 10 lost-ack replays and 20 network transitions.
- Canonical parity passed for Sale, Payment, Session, Journal, Outbox and Stock movements; total THB 16,900.00.
- Offline PromptPay and cross-tenant attempts were rejected/quarantined without creating Sales.
- App-only rollback to WP46 and restoration to WP47 passed in 10 and 11 seconds respectively.
- Production container identities remained unchanged.
- Browser smoke at 1024×768 passed without document-level horizontal overflow or console errors. An unpaired browser was correctly redirected to Device Pairing before accessing the Sync Center.

Gate A status: **PASS WITH UAT DATA-CLEANUP FINDINGS**.

Open data/security findings before Business/Security sign-off:

- Remove duplicated categories and prevent raw material, Retail and approval-test products from appearing in the Restaurant POS menu selector.
- Disable temporary `UAT_AUTH_BYPASS_ENABLED=true` before formal permission/security UAT.

## Gate B — Physical UAT

The following must be executed on the real paired Counter/iPad. They are deliberately not auto-passed:

- Tablet orientation, touch targets, keyboard, kiosk/restart/cache behaviour.
- Product barcode and Table QR scanning.
- Customer receipt and kitchen slip content, width, feed and cut.
- Printer paper-out/disconnect/reconnect/reprint with no duplicate sale.
- Cash drawer, or Manager-approved N/A with reason.
- PromptPay Sandbox/UAT reference and reconciliation while online.
- Dine-in and Takeaway end-to-end flows.
- Offline cash, reconnect, lost acknowledgement inquiry/replay and controlled network transitions.
- Sale/Payment/Stock/Journal/Event/Tax/Loyalty row parity.
- Kill switch, export, rollback and recovery evidence.
- Separate submitter, Technical checker and Business checker accounts.

Gate B status: **READY FOR PHYSICAL UAT; not yet passed.**

## Gate C — Production decision

Decision: **NO-GO**.

Production deployment and Production feature flags are not authorized. These blockers remain mandatory:

1. Physical UAT Gate B is completed with real evidence and independent sign-off.
2. Loyalty redeemed-points posting is proven atomic with Sale/Payment/Stock/Journal during reconnect and replay.
3. Live payment/refund provider security, webhook verification, reconciliation and SLA are approved.
4. Accountant/Tax Owner approves fiscal Tax Invoice/Credit Note behaviour and evidence.
5. Security Owner approves encrypted-storage threat model, device revocation and incident recovery.
6. Load, monitoring, alerting and the support runbook pass on the UAT release candidate. The app-only rollback rehearsal is already complete.

Until every blocker is closed, keep:

```text
POS_OFFLINE_MODE_ENABLED=false
PHYSICAL_UAT_EVIDENCE_ENABLED=false
```

in Production.
