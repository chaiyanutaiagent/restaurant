# WP57 — Retail Hold/Resume, Cash Return/Void and Shift Operations

Date: 2026-09-22
Environment: Local and UAT only
Design coverage: Retail R06–R08
Production: unchanged and not authorized

## Scope decision

WP57 opens the existing Server-authoritative POS operations for the dedicated Retail boundary. The release remains an online Cash Pilot: Hold/Resume and cash Return are enabled, settled cash sales are routed to Return instead of Void, and Retail Shift Operations use the Retail operational database. Exchange, provider refund, real tax documents, Loyalty and offline sale remain fail-closed.

## R06 — Server-backed Hold/Resume

- Added Retail migrations for `pos_hold_drafts` and append-only `pos_hold_draft_audits`.
- Hold content stores the Server pricing context/snapshot and creates no Payment, stock, tax or order side effect.
- Claim/Resume uses expected version, claim expiry, idempotency key and request hash; conflicts never merge carts automatically.
- Every lookup and mutation is scoped by signed Company, Brand and Branch context.
- Retail offline Hold is disabled rather than writing a local shadow that could duplicate or drift from the Server.
- Desktop/tablet Retail navigation now exposes the existing Hold workspace, revalidation states and conflict recovery.

## R07 — Return, Exchange and Void

### Enabled: cash Return

- Added Retail refund quote, operation, item, payment-leg, tax-state and append-only audit tables.
- Return begins from the original Server receipt, recalculates quantity/VAT/discount allocation and locks the sale version.
- Only settled original cash Payments are accepted; non-cash/provider legs fail closed.
- Execution requires maker-checker approval. Requester and approver must differ, and a signed approval grant is single use.
- Confirmation writes a negative Payment linked to the original Payment and operation.
- `sellable` disposition returns eligible goods to stock with a `sale_return` movement; `none` records no stock increase.
- Sale/item refund totals, order status, shift totals, operation version and immutable audit evidence update atomically.
- Retail tax state is explicitly `not_required`; this is not a tax document or Credit Note.

### Fail-closed boundaries

- Exchange remains disabled until an atomic Return + replacement-sale contract exists.
- Provider inquiry/retry and live provider refund remain disabled.
- Tax retry and real Credit Note issuance remain disabled.
- Loyalty redemption/reversal is not available in the Retail Cash Pilot.
- Legacy refund endpoints remain disabled; only quote → approved operation → cash confirmation is accepted.
- Void rejects settled or unknown Payments and directs the operator to Return. It remains available only where the Server proves the Payment is still `authorized` or `pending`.

## R08 — Retail Shift Operations

- Open/current/summary/cash movement/close/handover remain Server-authoritative and branch scoped.
- Open, cash movement and close operations keep idempotency/request hashes and optimistic shift versions.
- Cash movement and large variance thresholds still require manager approval and record audit evidence.
- Retail uses the dedicated operational database and explicitly marks accounting journal state `not_applicable`; no cross-database journal write is attempted.
- Shift close blocks while Hold Drafts or Returns are pending, Payments are unresolved, or other Server blockers remain.
- Retail offline-operation counting is skipped because offline authorization remains disabled for this pilot.

## Schema and migration

Retail migration head advances:

1. `p11retail0005`
2. `p12retail0006` — Server-backed Hold/Resume
3. `p13retail0007` — cash-only Return contract

The migrations were rehearsed on an isolated PostgreSQL database using `upgrade head → downgrade p11retail0005 → upgrade head`. Final head was `p13retail0007`.

## Engineering gate

| Check | Result |
|---|---|
| Python compile for changed backend/migrations | PASS |
| WP56/WP57 focused tests | PASS — 19/19 |
| Frontend type-check | PASS |
| Frontend production/PWA build | PASS — 4,243 modules transformed |
| Retail migration upgrade/downgrade/upgrade | PASS — `p13retail0007` head |
| Full backend regression | PASS — 499 tests, 1 intentional skip |
| Production flags/data source | Unchanged |

## UAT acceptance plan

1. Deploy only the immutable UAT candidate and advance only the Retail UAT schema.
2. Re-enable a bounded Retail requester persona and a separate manager approver; never store credentials in source/evidence.
3. Verify signed Retail Company/Brand/Branch context before every operation.
4. Hold a priced cart, replay the same request, inspect Server audit, resume from another Counter context and verify stale-version conflict.
5. Complete one cash sale, quote a partial Return, verify maker-checker, confirm cash, stock disposition, negative Payment, tax `not_required` and audit evidence.
6. Verify Exchange, provider refund, tax retry, offline Hold/Return and settled-payment Void fail closed.
7. Verify cash movement, shift summary blockers, variance approval, close/handover and version/idempotency behavior.
8. Rehearse app-only rollback/restore, verify public health and compare Production identities before/after.
9. Disable UAT personas and revoke sessions/assignments after evidence capture.

WP57 remains **UAT pending / Production NO-GO** until these steps pass. Physical scanner/printer/cash-drawer/network acceptance remains part of WP58 and is not implied by browser testing.
