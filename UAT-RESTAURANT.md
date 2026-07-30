# UAT Test Cases - Restaurant / F&B

**Date:** 2026-06-02  
**Environment:** Local Docker stack at `http://localhost`

## Quick Setup

Run the local stack, then seed demo menu:

```bash
docker compose exec backend python -m app.utils.seed_fnb_demo
```

Smoke test:

```bash
bash scripts/fnb-smoke.sh
bash scripts/fnb-permission-smoke.sh
```

Run the automated smoke tests against a fresh database before recording UAT
results. Do not copy run IDs, company IDs, branch IDs, or credentials from the
source project.

## Test Result Legend

| Mark | Meaning |
|---|---|
| PASS | Passed |
| FAIL | Failed |
| PARTIAL | Passed with issue |
| SKIP | Skipped |

## TC-FB-01 Table Setup And QR

| # | Step | Expected Result | Actual | Status |
|---|---|---|---|---|
| 01.1 | Open `/restaurant/tables` | Table Map loads and shows table summary | | |
| 01.2 | Create a new table | Table appears with status `ว่าง` | | |
| 01.3 | Try QR on an available table | QR action is disabled until the table is opened | | |
| 01.4 | Open the table | A new session QR is created and print dialog opens automatically | | |
| 01.5 | Copy/open the current session QR | Customer menu loads without login | | |
| 01.6 | Close the table and open the old QR | Old QR reports expired/not found | | |
| 01.7 | Reopen the same table | New QR differs from the previous session QR | | |

## TC-FB-02 Dine-In Customer Ordering

| # | Step | Expected Result | Actual | Status |
|---|---|---|---|---|
| 02.1 | Open a table session from Table Map | Table becomes occupied and has queue/session | | |
| 02.2 | Open `/menu/:qr_token` | Branch, table, categories, and menu items show | | |
| 02.3 | Search menu and filter category | Menu list filters correctly | | |
| 02.4 | Add item with special request | Cart shows item, qty, note, and total | | |
| 02.5 | Submit order | Cart clears and order status appears | | |
| 02.6 | Refresh customer page | Order status remains visible | | |
| 02.7 | Add another order from same QR | Order is added to same session | | |
| 02.8 | Review order history | Every order round, item status, and estimated total are visible | | |
| 02.9 | Request bill when enabled | Table becomes bill requested and customer cannot order more | | |

## TC-FB-03 Quick Service Customer Ordering

| # | Step | Expected Result | Actual | Status |
|---|---|---|---|---|
| 03.1 | Open `/order/:qs_token` | Quick Service menu loads without login | | |
| 03.2 | Add item and optional customer name/phone | Cart captures item and customer info | | |
| 03.3 | Submit order | Queue number appears | | |
| 03.4 | Refresh customer page | Queue status remains visible | | |
| 03.5 | Start new order | Previous queue is cleared and menu returns | | |

## TC-FB-03A Customer Mobile Layout

| # | Step | Expected Result | Actual | Status |
|---|---|---|---|---|
| 03A.1 | Open dine-in customer page on 390px-wide mobile | Header, category tabs, menu cards, and cart bar do not overlap | | |
| 03A.2 | Open dine-in customer page on 320px-wide mobile | Menu image/buttons fit without horizontal scroll | | |
| 03A.3 | Open quick-service page on 390px-wide mobile | Queue panel and menu list fit without clipping | | |
| 03A.4 | Open quick-service page on 320px-wide mobile | Add/customize buttons wrap cleanly and remain tappable | | |
| 03A.5 | Open cart sheet on mobile with home indicator/safe area | Submit button remains visible above safe area | | |
| 03A.6 | Submit order and wait for status | Loading state appears while status is being fetched | | |

## TC-FB-04 Kitchen Display

| # | Step | Expected Result | Actual | Status |
|---|---|---|---|---|
| 04.1 | Open `/restaurant/kitchen` | Pending/cooking/done columns load | | |
| 04.2 | Place dine-in or quick-service order | Ticket appears in `รอทำ` | | |
| 04.3 | Use source filter `โต๊ะ` / `รับเอง` | Ticket list filters correctly | | |
| 04.4 | Click `เริ่มทำ` | Ticket moves to `กำลังทำ`; customer status updates | | |
| 04.5 | Click `เสร็จแล้ว` | Ticket moves to `เสร็จแล้ว`; customer sees ready/done | | |
| 04.6 | Item has special request | Request is visually prominent | | |

## TC-FB-05 Staff Session Detail

| # | Step | Expected Result | Actual | Status |
|---|---|---|---|---|
| 05.1 | Open active session detail | Customer/source/order context appears | | |
| 05.2 | Check status board | Items are grouped by pending/cooking/done/served | | |
| 05.3 | QR order is pending | QR-new warning/badge appears | | |
| 05.4 | Mark done item as served | Item moves to served status | | |
| 05.5 | Cancel item with reason | Item is cancelled and removed from totals | | |
| 05.6 | Add order by staff | New order goes to kitchen and appears in session | | |

## TC-FB-06 Table Map Staff Awareness

| # | Step | Expected Result | Actual | Status |
|---|---|---|---|---|
| 06.1 | Customer submits QR order | Table card shows `QR ใหม่` count | | |
| 06.2 | Kitchen starts cooking | Table card shows `ค้างครัว` count | | |
| 06.3 | Kitchen marks done | Table card shows `พร้อมเสิร์ฟ` count | | |
| 06.4 | Customer requests bill | Table status becomes `เรียกบิล` | | |

## TC-FB-07 Checkout

| # | Step | Expected Result | Actual | Status |
|---|---|---|---|---|
| 07.1 | Open checkout while items pending/cooking | Warning appears with links to session/kitchen | | |
| 07.2 | Open checkout while items done but not served | Ready-not-served warning appears | | |
| 07.3 | Pay by cash exact amount | Checkout succeeds and receipt appears | | |
| 07.4 | Pay by transfer/card with reference | Reference is saved in receipt/payment | | |
| 07.5 | After checkout | Session closes and table returns available | | |
| 07.6 | Quick Service order is ready on `/restaurant/orders` | Staff can click `รับเงิน` and close the queue without opening checkout detail | | |
| 07.7 | Quick Service payment uses transfer/card/PromptPay | Staff can choose payment method, enter reference, and close the queue | | |
| 07.8 | Print restaurant receipt | Print output shows only the thermal-style receipt with table/queue/source/items/payment/reference | | |

## TC-FB-08 Pickup Display

| # | Step | Expected Result | Actual | Status |
|---|---|---|---|---|
| 08.1 | Open `/restaurant/pickup` | Pickup display loads | | |
| 08.2 | Quick-service item marked done | Queue appears as ready | | |
| 08.3 | Multiple ready queues exist | First queue is most prominent and other queues remain visible | | |
| 08.4 | Item marked served | Queue disappears from ready list | | |
| 08.5 | Ready queue has multiple items | Display shows item count and ready time | | |
| 08.6 | Network/API error occurs | Display shows an error state instead of a blank screen | | |
| 08.7 | Staff enables sound on pickup display | New ready queue plays a chime, and sound can be toggled off | | |
| 08.8 | Ready queue waits more than 10 minutes | Queue is visually highlighted as long-waiting | | |

## TC-FB-09 Recipe And Ingredient Cost

| # | Step | Expected Result | Actual | Status |
|---|---|---|---|---|
| 09.1 | Open `/restaurant/recipes` | Recipe list and cost summary load | | |
| 09.2 | Create a recipe for a `menu_item` | Recipe saves and appears in the list | | |
| 09.3 | Select a recipe | Ingredients, cost per yield, selling price, and gross margin show | | |
| 09.4 | Click edit on an existing recipe | Form opens with existing yield, notes, and ingredient rows prefilled | | |
| 09.5 | Change ingredient quantity/unit and save | Recipe updates and recalculates cost/margin | | |
| 09.6 | Create a missing raw material from the recipe form | Raw material is created with `raw_material` type and appended to ingredient rows | | |
| 09.7 | Run demo seed | Demo raw materials and sample recipes are available for cost testing | | |
| 09.8 | Open `/restaurant/reports/ingredients` | Theoretical ingredient usage can be filtered and exported as CSV | | |

## TC-FB-10 Restaurant Permissions

| # | Step | Expected Result | Actual | Status |
|---|---|---|---|---|
| 10.1 | Run `bash scripts/fnb-permission-smoke.sh` | Smoke roles/users are seeded idempotently | Seeded four F&B smoke users | PASS |
| 10.2 | Login as cashier/service staff | Staff can view/create tables | API returned 200/201 | PASS |
| 10.3 | Cashier opens kitchen/recipe/settings APIs without permission | Access is blocked by permission guard/API | API returned 403 | PASS |
| 10.4 | Login as kitchen staff | Staff can view kitchen tickets | API returned 200 | PASS |
| 10.5 | Kitchen staff tries table/recipe/settings APIs | Access is blocked by permission guard/API | API returned 403 | PASS |
| 10.6 | Login as recipe/cost staff | Staff can create raw material and view ingredient report | API returned 201/200 | PASS |
| 10.7 | Recipe/cost staff tries kitchen/table APIs | Access is blocked by permission guard/API | API returned 403 | PASS |
| 10.8 | Login as manager staff | Staff can use kitchen, QS QR, and ingredient report APIs | API returned 200 | PASS |
| 10.9 | Check frontend route/sidebar permissions | Restaurant routes and F&B sidebar use `fb.*` permissions instead of POS permissions | Type-check/build passed after route/sidebar update | PASS |

## Notes

- Customer pages are public and require no login.
- Staff pages require logged-in staff with branch context.
- For mobile testing on same Wi-Fi, use the Mac LAN IP instead of `localhost`.
- Automated smoke covers API/business flow; still run visual manual checks for mobile layout, table map badges, checkout warning copy, and pickup display readability before production.
