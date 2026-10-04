# WP52 — Restaurant Cancel, Discount, Refund and Receipt Center UX

Date: 2026-09-21
Status: **IN PROGRESS — LOCAL/UAT/SANDBOX ONLY**

## Objective

Compose the WP43, WP45 and WP46 Server-authoritative contracts into one touch-first Restaurant workflow for desktop and iPad. The Client may explain, preview and request an action, but it may not calculate a final financial result, fabricate an approval, or represent an unsupported transition as successful.

## Contract authority

| Surface | Server authority | Client responsibility |
|---|---|---|
| Price and discount | WP43 pricing quote, policy limits, request hash, one-time approval and checkout revalidation | Capture intent, show a clear preview, display Server changes and request Manager approval when required |
| Restaurant cancellation | WP45 stage, bill impact, waste readiness, maker-checker, KDS event and append-only audit | Select a target/reason, show the Server preview and keep blocked/served states fail-closed |
| Void | Existing POS settlement-state guard and `pos.sale.void` approval | Offer Void only for `completed` sales whose positive payment legs are `authorized` or `pending` |
| Refund | WP46 quote, remaining balance, original-payment allocation, provider state, stock disposition and tax link | Select items/quantities, show the Server quote and drive only contracted recovery actions |
| Receipt center | Branch/shift-scoped SaleOrder list and receipt snapshot | Search/filter, show sale/payment/refund history and route to print, eligible Void or WP46 Refund |

## Permission and state matrix

| Action | Permission/readiness | Offline behavior | Unsupported/missing behavior |
|---|---|---|---|
| Apply bill discount | `pos.discount.apply` or `pos.discount.override`; branch discount enabled | Basic cart intent may remain local, but override approval and checkout are disabled until online | Structured reason for every non-override discount is not in the contract; do not pretend it is audited |
| Request price override | `pos.price.override.request` or direct permission | Disabled; Server quote and approval are required | Priced modifier remains unavailable until a dedicated contract exists |
| Approve risk action | Action-specific Manager permission; requester and approver must differ | Disabled; token is Server-issued, one-time and expires | PIN or approval evidence is never stored or synthesized by the Client |
| Cancel pending item/order | WP45 cancellation permissions and open Restaurant session | Disabled; stage/waste/version must be read from Server | Served/checked-out work routes to Comp/Refund guidance and cannot be cancelled |
| Cancel cooking/done item/order | WP45 request + maker-checker approval; waste contract ready | Disabled | Blocked when recipe/waste evidence is incomplete |
| Void sale | `pos.sale.void` or request permission, open shift, safe settlement state | Disabled | Settled/unknown payment routes to Refund; no fake reversal |
| Refund sale | `pos.refund.create` or request permission, open shift, WP46 Sandbox runtime | Disabled | Provider `unknown`/reconciliation remains blocked; no duplicate execution |
| Tax/Credit Note | WP46 synthetic UAT `NON-FISCAL` only | Disabled | Real tax issuance, e-Tax and live Credit Note remain disabled/read-only |
| Exchange | No signed atomic exchange contract | Disabled/read-only | Do not call the legacy refund endpoint or create a fake exchange credit |

## UX composition

- D24–D28 define the action hierarchy and exception language; WP43/WP45/WP46 remain authoritative.
- D32 becomes a two-pane Bill & Receipt Center for the current shift with search, status filters, receipt detail, payment/refund history and safe action gating.
- D13 is adapted only for the existing table/session and unpriced note flow. Priced modifiers are excluded.
- D15 is adapted for checkout, receipt, Void and Refund without claiming real tax-document readiness.
- D31 remains the existing KDS/Pickup flow; WP52 adds no new kitchen state transition.
- Loading, empty, no-result, error, offline, stale/conflict and permission-denied states are explicit.
- All primary touch controls meet the 44px minimum on desktop and iPad layouts.

## Removal of unsafe legacy paths

- The legacy full/partial refund endpoints return HTTP 410 and must not be reachable from the UI.
- Refund and partial refund use the WP46 quote/execute workspace only.
- Exchange remains visible only as unavailable guidance until an owner-approved contract exists.
- UAT provider simulation is visible only when an explicit frontend UAT/Sandbox flag is built into the candidate; Production cannot expose it.

## Engineering and evidence gates

- Focused tests cover action eligibility, permission denial, offline fail-closed behavior and safe settlement routing.
- Frontend TypeScript/build and backend regression must pass.
- Desktop 1440×900 and iPad 1024×768 UAT must cover discount, cancellation, approval, receipt search/detail, Void eligibility and Refund recovery states.
- UAT must use Sandbox/non-fiscal flags only. Production services and flags remain unchanged.
- Rollback and evidence are required before the WP52 phase gate can close.
- `docs/ux-ui` is reference-only and must not be edited or staged.

## Explicit exclusions

- No Production deployment or Production flag change.
- No live payment provider, real tax document or e-Tax issuance.
- No Takeaway/Central Kitchen transaction enablement.
- No Retail data-source change or cutover.
- No atomic exchange, priced modifier, split bill or table transfer contract.
