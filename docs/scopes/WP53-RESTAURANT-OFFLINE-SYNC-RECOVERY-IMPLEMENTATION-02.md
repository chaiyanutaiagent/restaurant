# WP53 — Restaurant Offline and Sync Recovery UX

Date: 2026-09-22  
Scope: **Local/UAT only**  
Production: **NO-GO / unchanged**

## Outcome

Restaurant POS now has an operator-facing Sync Center at `/pos/offline-sync`, while the existing
Counter and branded Store routes continue to use the same screen. The screen reads the real encrypted
Dexie outbox and cached offline authorization; it does not use hard-coded queue data.

## Implemented

- Product, Branch, Counter, Shift, Cashier and Network context.
- Online/offline impact banner reflecting the current cash-only offline contract.
- Separate pending, syncing, review and reconciled summaries with last successful sync.
- Responsive queue list and detail panel for desktop and tablet.
- Local label, amount, payment, item, print, retry, timestamp and safe Support reference detail.
- Explicit handling for `pending_sync`, `syncing`, `server_acknowledged`, `unknown`, `needs_review`,
  `rejected`, `quarantined` and `reconciled`.
- Unknown-operation inquiry before replay and retry with the original identity.
- No operator action that discards a paid outbox record.
- Restaurant Takeaway POS badges link to the Sync Center and count every unresolved state.

## Existing contracts reused

- `restaurantPendingOrders` remains scoped by Company, Branch, Brand and User.
- Encrypted payload and local order remain the source of local detail.
- Server acknowledgement and reconciliation remain authoritative.
- Idempotency key, client operation ID, request hash and sequence number are unchanged.
- Logout, handover and shift-close safety rules remain unchanged.

## Explicit boundaries

- No schema or Backend contract change.
- No Production deployment or Production feature flag.
- No real PromptPay/provider, tax document, Retail source or Takeaway/Central Kitchen transaction.
- Browser UAT does not constitute physical network-loss, restart, printer or cash-drawer acceptance;
  those remain WP54 gates.

