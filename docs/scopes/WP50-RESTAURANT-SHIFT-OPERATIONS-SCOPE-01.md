# WP50 — Restaurant Shift Operations

Date: 2026-09-21
Environment: Local and UAT only
Production: unchanged; Production deployment and feature activation are not authorized

## Objective

Implement an explicit, server-authoritative Staff shift lifecycle for Restaurant POS. A Staff shift is separate from Store sales-round closure and is always bound to Company, Branch, Staff user, cash location and the confirmed Counter when one is presented.

The primary journey is:

```text
Counter readiness → Open shift → Sell / Hold / Refund / Cash movement
→ Server close summary → Cash denomination count → Variance approval
→ Close or Staff handover → Logout while preserving Counter pairing
```

## Implemented contract

### Open shift

- Records shift type, opening float, operator, branch, stock/cash location, opening Counter evidence and a stable idempotency key.
- Rejects a second incompatible open shift and returns the original record for an exact retry.
- The POS client requires an online state and a confirmed Counter before enabling the touch-first open-shift action.

### Cash movement

- Records cash in/out, amount, reason code, operator note, requester, approver, Counter evidence, optimistic shift version and immutable request hash.
- Requires manager maker-checker approval at the branch-configured threshold.
- Posts the accounting journal before reporting success and records audit evidence.
- Rejects stale shift versions and idempotency reuse across another shift, branch or request.

### Server close summary

- Recomputes sales, void, refund, payment, change, cash movement and expected cash totals from persisted Server data.
- Reports pending Hold Draft, refund, offline operation, unresolved payment and missing-journal blockers.
- Persists denomination count, expected cash, closing cash, difference, reason, note, operator/approver, Counter evidence and an immutable close snapshot.
- Requires manager approval at the branch-configured variance threshold.
- Uses row locking, optimistic version and idempotency to prevent duplicate or concurrent close.
- Supports `close` and `handover`; handover clears the Staff session without deleting Counter pairing.

### Fail-closed rules

- Close/approval is unavailable offline. Cached summaries are read-only and must not claim a completed close.
- A shift cannot close while Hold Drafts, refunds, offline operations, unresolved payments or accounting journals remain pending/unknown.
- Reopen is not supported in WP50.
- Retail cash movement is explicitly disabled; the compatibility migration does not authorize Retail cutover.

## User experience and accessibility

- Desktop and iPad-landscape layouts follow the shared touch-first POS shell.
- Interactive targets are at least 44px, with visible labels, focus states and non-colour-only status text.
- Loading, Empty, Error, Offline, Stale/version conflict, Permission denied and Approval required states are explicit.

## Acceptance criteria

1. An exact open request returns one shift; no duplicate is created.
2. Cash in/out changes expected cash only after the journal and audit are committed.
3. Threshold cash movement and cash variance require a separate manager approval.
4. The client cannot substitute a locally calculated close total for the Server summary.
5. A stale version or concurrent mutation fails without partially closing the shift.
6. Every close blocker is visible and prevents the final action.
7. Exact close retry returns the original shift; a different retry is rejected.
8. Handover logs out the Staff session while retaining the paired Counter.
9. Local regression, migration round-trip, API smoke, UAT role/browser smoke and rollback checks pass before closing the gate.

## Explicit non-actions

- No Production deployment or Production flag change.
- No Retail data-source cutover or Retail transaction activation.
- No Takeaway/Central Kitchen transaction activation.
- No live payment/refund provider and no real tax-document issuance.
- No reopening of a closed shift.
- No edit or commit under `docs/ux-ui/`.

## Rollback

1. Stop the UAT WP50 application candidate.
2. Restore the previous WP49 frontend and WP48 backend images.
3. If no WP50 shift data exists, downgrade the main schema from `wp50shift0024` to `wp47offline0023`.
4. If WP50 shift data exists, keep the additive schema and roll back application images only; do not drop audit/financial evidence.
5. Re-run UAT health and confirm Production container identities remain unchanged.
