# P6-TAKEAWAY-CAPABILITY-MATRIX-02 — Chambo to Foodchainservice Takeaway

วันที่จัดทำ: 2026-09-11

สถานะ: **implemented_dark_launch — รอ field UAT และ activation gate**

Source baseline: `/Users/user/Projects/erp-pos-run` commit `15a1de1`

Target baseline: `/Users/user/Projects/restaurant` commit `27c9c10`

## วัตถุประสงค์

จำแนกความสามารถของ Chambo ว่าส่วนใดควรนำแนวคิดหรือ component มาใช้ ส่วนใดต้องปรับให้
เป็น SaaS หลาย Company/Brand/Branch ส่วนใดต้องเขียนใหม่เพื่อรักษา database boundary และ
ส่วนใดไม่อยู่ใน Takeaway Phase 6

เอกสารนี้ไม่อนุญาตให้ copy database, production configuration, secret หรือไฟล์แบรนด์จาก
`erp-pos-run` และไม่เปลี่ยน UAT/production runtime

## คำจำกัดความการตัดสินใจ

- **Reuse library** — ใช้เฉพาะ utility/component ที่ไม่อ้าง Restaurant/Chambo model โดยตรง
- **Adapt workflow** — ใช้กฎธุรกิจที่พิสูจน์แล้ว แต่เขียนผ่าน Takeaway API และ Takeaway Database
- **Rebuild boundary** — ออกแบบ model/router/migration ใหม่ ห้าม copy การผูก Restaurant session
- **Exclude** — ไม่ใช่ Takeaway Phase 6 หรือเป็นข้อมูลเฉพาะแบรนด์
- **Defer** — มีประโยชน์ภายหลัง แต่ไม่อยู่ใน release แรก

## Capability Matrix

| กลุ่ม | ความสามารถจาก Chambo | สถานะใน Restaurant target | การตัดสินใจ Phase 6 | เป้าหมาย Takeaway | หลักฐานทดสอบขั้นต่ำ |
| --- | --- | --- | --- | --- | --- |
| Control Plane | Company/Brand/Branch และ `BrandBranch` | มี canonical business context และ Platform ownership แล้ว | Reuse contract | ใช้ ID จาก Control Plane เป็น immutable reference | สร้างแบรนด์/สาขา Takeaway โดยไม่แก้ SQL |
| Control Plane | Storefront mode/theme ตามแบรนด์ | Restaurant มี brand navigation/theme บางส่วน | Adapt workflow | config-driven template ไม่ hardcode Chambo | สองแบรนด์แสดงชื่อ/สี/เมนูไม่ปนกัน |
| Identity | พนักงานหน้าร้านและผู้ทำรายการ | Restaurant มี staff scope/device foundation | Reuse contract + rebuild permission | ใช้ `takeaway.*` และ snapshot ผู้ทำรายการ | ข้าม Company/Brand/Branch ถูกปฏิเสธ |
| Device | Android Chambo และ Bluetooth printer | Restaurant มี browser/tablet/printer adapter | Reuse adapter; Defer native app | web/PWA + paired device ใน release แรก | revoke/re-pair/restart และพิมพ์จริงผ่าน |
| Store POS | Paid-first order | Restaurant มีรับกลับ แต่เป็น Restaurant domain | Adapt workflow | Takeaway order/payment transaction ของตัวเอง | retry ไม่สร้าง order/payment ซ้ำ |
| Store POS | Offline order sync/client order ID | Restaurant มี offline outbox/lost-ack test | Reuse library + Adapt workflow | Takeaway offline envelope และ idempotency | offline 100 รายการ + reconnect + lost-ack |
| Store POS | สลิปลูกค้า/สลิปร้าน | Restaurant มี receipt/printer component | Reuse adapter + Adapt document | receipt snapshot อยู่ Takeaway DB | ยอด/เงินรับ/เงินทอนตรงและพิมพ์ซ้ำได้ |
| Store POS | QR รับกลับ | Restaurant มี per-order QR/public token | Reuse token pattern + Adapt workflow | counter เปิด queue/QR บน Takeaway API | QR → order → payment ไม่เปิดเผย internal UUID |
| Customer | ลูกค้าสั่งผ่าน QR | Restaurant มี public menu/order/status | Adapt workflow | public token อายุจำกัดและผูก branch/queue | token หมดอายุ/revoke/cross-branch test ผ่าน |
| Kitchen | Kitchen job/status | Chambo ร้านเล็กเคยตัด KDS ออกจาก flow หลัก | Rebuild optional station flow | เปิด/ปิด KDS ได้ตาม template | ร้านไม่มี KDS ขายได้; ร้านมี KDS แยก station ได้ |
| Pickup | จอเรียกคิว/ส่งมอบ | Chambo ร้านเล็กไม่บังคับใช้ | Adapt workflow | queue number, ready, handed_over | สถานะเดินหน้าเท่านั้นและ retry ปลอดภัย |
| Menu | เมนูสินค้าแยกแบรนด์ | Restaurant มี Product/Brand แต่เป็น Restaurant DB | Rebuild boundary | Takeaway menu/category/item/version | ปิดเมนูแบรนด์หนึ่งไม่กระทบอีกแบรนด์ |
| Recipe | สูตรขาย/สูตรผลิต/สูตรซ้อน | Restaurant target มี generic recipe foundation | Adapt workflow | Takeaway recipe version/yield/UOM | loop validation และต้นทุนต่อหน่วยผ่าน |
| Shift | ปิดกะหลายรอบในวันเดียว | Restaurant มี WAP shift closure | Adapt workflow | Takeaway shift round และ cashier snapshot | ยอดหลังปิดรอบแรกไปอยู่รอบถัดไป |
| Replenishment | ใบสั่งครัวกลางรวมรายวัน | Restaurant มี CentralOrder ใน Restaurant DB | Adapt workflow | regular order หนึ่งใบ/วัน/สาขา/แบรนด์ | กดซ้ำคืนใบเดิม ไม่สร้างซ้ำ |
| Replenishment | สั่งสินค้าเพิ่มหลังส่งใบรายวัน | Chambo ล่าสุดรองรับ extra central order | Adapt workflow | `order_kind=extra` และเหตุผล/ผู้อนุมัติ | ใบเพิ่มไม่แก้ snapshot ใบรายวันเดิม |
| Replenishment | ขอสินค้าที่ไม่มีใน catalog | Chambo ล่าสุดรองรับ unlisted request | Adapt workflow | unresolved line → central map/reject | mapping มี audit และไม่สร้าง SKU ซ้ำโดยเงียบ |
| Central | ดู/อนุมัติ/แพ็ก/จัดส่งออเดอร์สาขา | Restaurant มี generic central pages | Reuse UI pattern + Adapt workflow | Takeaway central workspace/API | transition ผิดลำดับถูกปฏิเสธ |
| Production | รวมยอดสินค้าสำเร็จและวัตถุดิบ | Restaurant มี production summary | Adapt workflow | aggregate ตามวันส่ง/แบรนด์/สูตร version | ยอดรวมย้อนกลับถึง order line ได้ |
| Production | Production batch/start/complete/cancel | Chambo มี batch foundation | Adapt workflow | batch issue/output/waste/yield | complete ซ้ำไม่ตัด stock ซ้ำ |
| Stock | Raw/ready/store stock areas | Restaurant มี stock location/balance/movement | Rebuild boundary + Adapt workflow | Takeaway stock ledger ใน Takeaway DB | ทุก movement มี source/idempotency/actor |
| Stock | วัตถุดิบกองกลางใช้หลายแบรนด์ | มีได้ใน Restaurant domain แต่ห้าม share table | Adapt workflow | ownership ระดับ Company+Location+Item/Lot; brand เป็น usage dimension | รวมยอดถูกและรายงานแยก brand/batch ได้ |
| Stock | Transfer และสาขารับของ | Restaurant มี stock transfer | Adapt workflow | ship/receive discrepancy และ immutable snapshots | ส่งไม่ครบ/รับไม่ตรงมี audit และ reconciliation |
| Stock | Stock cutover/reset tools | Chambo มีเครื่องมือเฉพาะ rollout | Rebuild boundary | dry-run/import batch/approval/rollback | preview ไม่มี mutation; execute ทำซ้ำไม่ได้ |
| Credit | Franchise credit ledger | Restaurant target มี generic credit pages ใน Restaurant DB | Adapt workflow | Takeaway append-only credit ledger | reserve/capture/release/refund สมดุล |
| Credit | QR/slip top-up และอนุมัติ | Chambo มี store/central flow | Adapt workflow | media validation + reviewer audit | approve ซ้ำไม่เพิ่มยอดซ้ำ |
| Reports | ยอดขาย/กะ/สาขา/พนักงาน | Restaurant มีรายงาน operational | Rebuild query + reuse presentation | Takeaway report จาก Takeaway DB | รวมเท่ากับ source documents |
| ERP | Accounting/reporting handoff | Restaurant มี versioned outbox pattern | Reuse contract pattern | `takeaway.*.v1` event จาก transaction เดียวกับ source | replay ไม่ลงบัญชี/รายงานซ้ำ |
| Onboarding | Seed Chambo menu/recipe | มี script เฉพาะ Chambo ใน source | Exclude script; Adapt data contract | template/import API ที่ validate ได้ | onboard แบรนด์ใหม่โดยไม่แก้ source code |
| Historical data | ออเดอร์/กะ/stock/credit เดิม | อยู่ใน Chambo production domain | Rebuild importer | immutable archive + approved opening balances | count/hash/amount reconciliation ผ่าน |
| Restaurant tables | DiningTable/DiningSession/DiningOrder | ใช้งานใน Restaurant Phase 5 | Exclude | Takeaway ไม่มี table/dining session | Takeaway DB ไม่มี Restaurant table/FK |
| Delivery | รถส่ง/marketplace/aggregator | ไม่มี complete domain | Exclude | อยู่นอก Phase 6 | ไม่มี route หรือ entitlement เปิดโดยบังเอิญ |

## Source Modules ที่ใช้เป็น Reference เท่านั้น

### ใช้อ่านกฎธุรกิจ

- `backend/app/models/restaurant.py`
- `backend/app/schemas/restaurant.py`
- `backend/app/routers/restaurant.py`
- `backend/app/services/recipe_service.py`
- `backend/app/services/replenishment_service.py`
- `frontend/src/lib/wapApi.ts`
- `frontend/src/lib/chamboOffline.ts`
- `frontend/src/pages/restaurant/WapOrderPage.tsx`
- `frontend/src/pages/restaurant/WapShiftClosePage.tsx`
- `frontend/src/pages/restaurant/ChamboStoreOrdersPage.tsx`
- `frontend/src/pages/restaurant/ChamboCentralOrdersPage.tsx`
- `frontend/src/pages/restaurant/ChamboCentralProductionPage.tsx`
- `frontend/src/pages/restaurant/ChamboCentralStockPage.tsx`
- `frontend/src/pages/restaurant/ChamboStoreCreditsPage.tsx`
- `frontend/src/pages/restaurant/ChamboCentralCreditsPage.tsx`

### ใช้อ่าน test cases

- `backend/tests/test_store_pos_flow.py`
- `backend/tests/test_wap_offline.py`
- `backend/tests/test_store_inventory.py`
- `backend/tests/test_stock_cutover.py`
- `backend/tests/smoke_store_pos_flow.py`
- `backend/tests/smoke_store_inventory_api.py`

ไฟล์เหล่านี้ไม่ใช่รายการอนุญาตให้ copy และ path ทั้งหมดอ้างถึง
`/Users/user/Projects/erp-pos-run` ซึ่งต้องคง unchanged

## Data Migration Classification

| ข้อมูล | วิธีนำเข้า | เงื่อนไข |
| --- | --- | --- |
| Company/Brand/Branch | map ไป Control Plane canonical ID | ห้ามสร้าง ownership ซ้ำใน Takeaway DB |
| Staff | สร้าง assignment ใหม่ผ่าน Control Plane | ไม่ย้าย password, session, token หรือ PIN hash |
| Device | pair ใหม่ | ไม่ย้าย device credential เดิม |
| Menu/Category/Product/Unit | versioned master-data import | validate code, UOM, price และ brand ownership |
| Recipe/Ingredient/Yield | versioned recipe import | reject loop, missing UOM และ inactive ingredient |
| Stock location/area | config import | owner อนุมัติ physical-location mapping |
| Opening stock | signed opening-balance batch | lot/UOM/cost/count reconciliation ต้องผ่าน |
| Credit balance | signed opening-credit batch | ยอด account เท่ากับ ledger proof |
| Open order/transfer | ไม่ย้ายใน release แรก | drain/close บน Chambo ก่อน cutover |
| Historical sale/shift/order | immutable archive batch | ไม่กระทบ running document number |
| Receipt image/brand artwork | import เฉพาะไฟล์ที่ได้รับอนุญาต | scan file type/size และไม่ย้าย secret |

## ข้อตกลงรอบ Dark Launch และสิ่งที่ต้องตัดสินใจก่อน Activation

1. release แรกใช้ web/PWA และ paired device; native Android เลื่อนไปหลัง field UAT
2. รองรับ `regular`, `extra`, `correction` โดยเก็บเหตุผลและไม่แก้ snapshot เดิม
3. paid-first เป็นค่าเริ่มต้น; KDS/Pickup เปิดตาม workspace/permission ของสาขา
4. opening stock/credit date, real Chambo snapshot และผู้ลงนามกระทบยอดต้องอนุมัติก่อน import จริง
5. กองวัตถุดิบร่วมรองรับหลายแบรนด์ภายใน Company ของ Takeaway เท่านั้น หากแชร์ข้าม
   Restaurant/Retail ต้องออกแบบ Inventory Service แยกและห้าม SQL join ข้ามฐาน
6. physical tablet/printer/network/offline field UAT และ production owner sign-off ยัง pending

## Definition of Done ของ Capability Matrix

- [x] ครอบคลุม store, central, production, stock, credit, QR, ERP และ migration
- [x] แยก Restaurant รับกลับออกจาก Takeaway POS SaaS
- [x] รวม Chambo extra/unlisted order รุ่นล่าสุด
- [x] ระบุ reuse/adapt/rebuild/exclude/defer ต่อ capability
- [x] ระบุ test evidence ขั้นต่ำ
- [x] ไม่แก้ source repository และไม่เปิด runtime

Implementation evidence: `P6-TAKEAWAY-IMPLEMENTATION-06.md`
