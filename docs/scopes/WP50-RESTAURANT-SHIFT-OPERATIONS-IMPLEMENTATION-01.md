# WP50 Restaurant Shift Operations — Implementation Record

Date: 2026-09-21
Status: Implemented; Local/UAT Phase Gate closed

## Server and data

- Main migration: `wp50shift0024_add_shift_operations_contract.py`.
- Retail compatibility migration: `p9retail0003_add_shift_operations_contract.py`; it is additive and does not change the Retail service source or enable writes.
- `cashier_shifts` now stores shift type, version, open/close idempotency, Counter/actor/approver evidence, denomination count and immutable close snapshot.
- `pos_cash_movements` stores cash in/out, journal link, reason, requester/approver, Counter evidence, optimistic version and immutable request hash.
- Branch settings provide cash-movement and close-variance approval thresholds.
- Approval action catalogue adds `pos.cash_movement.approve` and `pos.shift.variance.approve`.
- Role policy version `2026-09-21.4` grants only the bounded Restaurant shift actions to the approved presets.

## API

| Route | Purpose |
|---|---|
| `POST /api/v1/pos/shifts/open` | Idempotent Server open shift |
| `GET /api/v1/pos/shifts/current` | Current operator shift |
| `GET /api/v1/pos/shifts/{id}/summary` | Authoritative close summary and blockers |
| `POST /api/v1/pos/shifts/{id}/cash-movements` | Versioned cash in/out with accounting and approval |
| `POST /api/v1/pos/shifts/{id}/close` | Exactly-once close |
| `POST /api/v1/pos/shifts/{id}/handover` | Exactly-once Staff handover |

The close service acquires a shift row lock, rebuilds the summary inside the transaction, verifies optimistic version and blockers, then stores the immutable snapshot. Sale, void, refund and Hold Draft paths participate in the same shift concurrency boundary.

## POS and Company Admin UI

- Replaced the legacy close dialog with a touch-first Shift Operations workspace.
- Added Server summary, blocker list, payment/journal state, cash movement form/history, denomination count, variance/reason and manager approval.
- Added touch-first open shift with location selection, shift type, opening float, online/Counter readiness and stable idempotency.
- Added branch threshold controls for cash movement and close variance.
- Close and handover clear Staff authentication but deliberately retain Counter pairing.

## Local evidence

| Check | Result |
|---|---|
| Python compile | PASS |
| Focused WP50 unit tests | PASS |
| Full backend regression | PASS — 453 tests, 1 skipped |
| WP50 API smoke | PASS — open, movement, approvals, close, replay, journal and audit |
| Main migration upgrade/downgrade/upgrade | PASS |
| Retail compatibility migration upgrade/downgrade/upgrade | PASS |
| Frontend TypeScript | PASS |
| Frontend production/PWA build | PASS; existing large-chunk advisory only |
| Diff whitespace validation | PASS |

## Safety notes

- Open/close requests use stable Client keys, but success is determined only by persisted Server state.
- Manager approval tokens are not stored as business evidence; normalized immutable evidence is stored instead.
- Exact retries are resolved before asking for a second approval token.
- Unknown payment or missing journal state is a close blocker, never an assumed success.
- Production, live provider, real tax, Retail cutover and Takeaway/Central writes remain unchanged.
