# WP51 UAT Plan — Hold Draft and Order Center

Date: 2026-09-21
Target: `https://uat-pos.foodchainservice.com`
Environment: **UAT only**

## Preconditions

- Deploy an immutable WP51 backend/frontend candidate only to `restaurant-pos-uat-drill`.
- Confirm `/health`, `/ready`, migration heads and Production image/container identities before and after deployment.
- Use formal UAT users and a paired Counter; do not weaken Production authentication or permissions.
- Record the previous UAT backend/frontend image IDs for rollback.

## Hold Draft scenarios

1. Open a Staff shift and create a hold from a non-empty cart.
   - The cart clears only after Server success.
   - The draft appears across Counter scope with owner, Counter, shift, location, age/expiry, version and total.
   - No Sale, Payment, Stock movement, tax document or KDS ticket is created.
2. Search/filter/sort active, mine, Counter and history views; inspect item detail and audit timeline.
3. Resume an unchanged draft from an empty cart and confirm one winner, one version advance and sale cart restoration.
4. Resume while the current cart is non-empty and verify the three explicit choices; cancel must retain both cart and draft.
5. Trigger price/availability revalidation and verify the diff must be accepted before resume; rejection releases the claim.
6. Trigger two-device claim/version conflict and verify the loser sees current Server status/version and cannot merge or overwrite.
7. Release own claim; verify another operator cannot release it.
8. Reassign with and without `pos.draft.reassign`; require a valid same-branch active user and a reason.
9. Discard with permission/reason and reopen eligible history; converted history remains read-only.
10. Go offline and verify local-only labelling and fail-closed payment/stock/tax/KDS behavior; reconnect and review/reconcile.

## Order Center scenarios

1. Search by table, queue, customer and active order number; verify cancelled order numbers/totals are excluded.
2. Filter canonical session states and sources; inspect ordering, bill-requested, ready and closed summaries.
3. Open a session detail and verify order lines and canonical kitchen counts (`pending`, `cooking`, `done`, `served`).
4. Verify `สั่งเพิ่ม` is enabled only for open sessions and disabled after bill request/close.
5. Verify quick-service handoff appears only when all outstanding kitchen work is done and then routes to the real checkout flow.
6. Verify closed sessions are read-only and unsupported actions are absent/disabled with explanation.
7. Verify loading, empty, no-result, error, offline, stale and permission-denied states.

## Viewport/accessibility checks

- Desktop 1440×900 and iPad 1024×768.
- No page-level horizontal overflow.
- All visible interactive controls are at least 44×44 CSS pixels.
- Status uses icon/text in addition to color; keyboard focus and dialog close paths remain usable.

## Rollback and phase gate

- Roll back application images to the captured pre-WP51 UAT IDs and confirm health/readiness.
- Restore WP51 images and confirm the same checks.
- Close WP51 only after evidence records pass/fail for every scenario and verifies Production identities did not change.
- Update D20–D23 and D29 completion state only from recorded evidence; do not edit or commit `docs/ux-ui`.
