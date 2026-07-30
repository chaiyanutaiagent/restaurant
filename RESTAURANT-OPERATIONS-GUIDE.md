# Restaurant Operations Guide

Last updated: 2026-07-07

## Before Opening

1. Start the local stack and check health.

```bash
docker compose up -d
curl -s http://localhost/health
```

2. Login as staff with branch context.
3. Open `/restaurant/tables` and confirm tables and table status. Dine-in QR is
   created only after a table is opened.
4. For demo/testing only, seed sample menu, raw materials, and recipes.

```bash
docker compose exec backend python -m app.utils.seed_fnb_demo
```

## Dine-In Flow

1. Staff opens a table from `/restaurant/tables`.
2. The system creates a new one-session QR, opens the print dialog, and staff
   gives the printed QR to the customer.
3. Customer scans `/menu/:session_qr_token`, orders, checks all order rounds and
   live item statuses, and requests the bill when that service is enabled.
4. Kitchen works tickets from `/restaurant/kitchen`.
5. Staff marks ready items as served from Session Detail or Kitchen Display.
6. Customer requests bill from mobile, or staff opens checkout.
7. Staff takes payment, enters payment reference when needed, and prints receipt.
8. Closing or checking out the table invalidates that QR permanently. Reopening
   the same table creates a different QR.

## Quick Service Flow

1. Staff generates the Quick Service QR from restaurant settings.
2. Customer scans QR and orders from `/order/:qs_token`.
3. Kitchen marks tickets pending -> cooking -> done.
4. Pickup display `/restaurant/pickup` shows ready queues.
5. Staff closes ready queue from `/restaurant/orders` with `รับเงิน`.

## Restaurant Paid-First WAP Flow

Use `/restaurant/orders` for the dedicated `ระบบร้านอาหาร` branch-staff app.

1. Staff logs in with branch context and opens `/restaurant/orders`.
2. Staff taps menu items loaded from the active branch catalog.
3. Staff taps `สรุปออเดอร์` to review the order before payment.
4. Staff can adjust quantities from the review page.
5. Staff collects payment with either `รับเงินสด / ออกคิว` or `PromptPay จ่ายแล้ว / ออกคิว`.
6. After queue is issued, staff prints the customer slip first.
7. Staff then prints the kitchen slip, which sends the order to kitchen tickets.

Seed a generic F&B demo catalog in local/staging with:

```bash
docker compose exec backend python -m app.utils.seed_fnb_demo --company-id <company-id>
```

## Restaurant Shift Close And Daily Replenishment

Use `/store/restaurant/close-shift` for Restaurant branch close-shift and replenishment.

Rules:

- A branch can close multiple sales rounds in the same business day.
- Each closed round is stored with `round_no`.
- Sales after the latest closed round become the next round; staff do not need to wait for a new day.
- After closing a round, staff should log out before selling again so the next seller is recorded correctly.
- Replenishment to central kitchen is sent once per day, per branch, per brand.
- The replenishment tab combines purchase items from all closed rounds for the day.
- If today's central order already exists, pressing submit again returns the existing central order instead of creating a duplicate.

Recommended branch flow:

1. Sell from `/store/restaurant/orders`.
2. Open `/store/restaurant/close-shift`.
3. Confirm the current round sales total.
4. Close the current round.
5. Log out if another staff member will continue selling.
6. At the agreed time, review the replenishment tab.
7. Press `ส่งใบสั่งรวมวันนี้` once.
8. Track delivery and receive stock from `/store/restaurant/replenishment-orders`.

## Kitchen Rules

- Work oldest tickets first.
- Use source filter when the kitchen station separates dine-in and pickup.
- Keep status order: pending -> cooking -> done -> served.
- Special requests should be checked before marking done.

## Recipe And Cost

1. Open `/restaurant/recipes`.
2. Create raw materials from the recipe form when a material is missing.
3. Create or edit recipes for `menu_item` products.
4. Check cost per yield and gross margin.
5. Use `/restaurant/reports/ingredients` for theoretical usage and CSV export.

## End Of Day

1. Check `/restaurant/orders` for open sessions or unpaid queues.
2. Check table map for tables still occupied or bill requested.
3. Export ingredient usage when needed.
4. Run smoke test only in development or staging.

For the next Restaurant phase:

- Decide whether to allow admin-only correction orders after the daily central order has already been sent.
- Run a local backup/restore drill before wider pilot testing. See `docs/local-backup-restore.md`.
- Consider employee PIN or quick staff switch after close shift.

```bash
bash scripts/fnb-smoke.sh
bash scripts/fnb-permission-smoke.sh
```

## Permission Guide

- Manager: `fb.menu.view`, `fb.table.manage`, `fb.order.create`, `fb.kitchen.manage`, `fb.recipe.manage`, `fb.report.view`, `fb.settings.manage`
- Cashier/service staff: `fb.menu.view`, `fb.table.manage`, `fb.order.create`
- Kitchen staff: `fb.menu.view`, `fb.kitchen.manage`
- Recipe/cost staff: `fb.menu.view`, `fb.recipe.manage`, `fb.report.view`

## Permission Smoke Users

The local permission smoke creates these users with password `SmokePass123!` for UAT only:

- `fnb_smoke_cashier`
- `fnb_smoke_kitchen`
- `fnb_smoke_recipe`
- `fnb_smoke_manager`

Run the automated baseline before manual role UAT:

```bash
bash scripts/fnb-permission-smoke.sh
```
