# WP18 — Takeaway Store Operation Parity

วันที่ตรวจรับ: 2026-09-17

สถานะ: **implemented_local — ผ่าน automated gate; ยังไม่ deploy UAT/Production**

Baseline: `ccbbde4e6d3b9bb5dcc5839949bb60beffb60109`

## เป้าหมาย

ปิดช่องว่างงานประจำวันของสาขา Takeaway หลัง WP17 แยก Store/Central/Admin workspace แล้ว โดยให้
หน้าร้านขายต่อได้เมื่อเครือข่ายขาด ออกและพิมพ์ซ้ำใบเสร็จได้ ปิดกะจากยอดจริง สั่งและรับสินค้าจาก
ส่วนกลาง และตรวจสต๊อกร้านผ่าน Takeaway database โดยไม่อ่านหรือเขียน Restaurant operational tables

## สิ่งที่ส่งมอบ

### 1. Counter และ offline outbox

- เก็บ Takeaway workspace/menu/shift snapshot แยก scope ตาม Company, Brand, Branch และ User ใน Dexie
- ทุกบิล Counter ใช้ device UUID, offline sequence และ idempotency key ของ sale/payment ก่อนส่ง server
- รองรับสถานะ `pending`, `syncing`, `needs_review`, `synced`, retry และ lost acknowledgement
- Counter ทำงานแบบ `offline-first` จริง ไม่ถูก React Query พัก mutation เมื่อ browser รายงาน offline
- แสดงจำนวนรายการรอส่ง/ต้องตรวจ และส่งซ้ำอัตโนมัติเมื่อกลับมาออนไลน์
- ปิดกะไม่ได้ถ้ายังมีรายการขายในเครื่องที่ยังไม่ reconcile

### 2. Receipt และ reprint audit

- ใบเสร็จลูกค้าและสำเนาร้านใช้ receipt snapshot เดียวกับยอดบน server
- บิลออฟไลน์สร้างใบเสร็จในเครื่องด้วย subtotal, tax, discount และ total ก่อน sync
- เรียกบิลล่าสุดกลับมาพิมพ์ซ้ำได้
- Server เก็บ `print_count`, `last_printed_at`, `last_printed_copy` และ outbox event แบบ idempotent
- Web ใช้ print fallback; Bluetooth/Android printer ยังอยู่ใน WP20

### 3. กะขาย

- แสดงยอด paid/refunded, จำนวนบิล, ยอดแยกวิธีชำระ, เงินสดที่ควรมี, เงินสดที่นับได้ และผลต่าง
- หน้าเปิด/ปิดกะและประวัติกะแยกจาก Counter
- การคำนวณยึด shift และ signed branch scope จาก server

### 4. ใบสั่งสินค้าของสาขา

- สาขาสร้างใบสั่งประจำ, ขอสินค้าเพิ่ม และสินค้านอกแคตตาล็อกได้จาก Store workspace
- ใบสั่งประจำใช้ daily idempotency key; extra/unlisted ใช้ key ต่อคำขอ
- ระบบสร้างหรือใช้รอบสั่งของวันเดิมแบบ concurrency-safe และไม่สร้างเลขใบสั่งซ้ำ
- Store ดูรายการสินค้าและสถานะของใบสั่งเฉพาะสาขาตัวเอง
- Central เปลี่ยนสถานะถึง `shipped`; เฉพาะ Store permission เท่านั้นที่ยืนยัน `received`
- การรับครบตัดเข้า Store stock แบบ idempotent และสร้าง ERP outbox event

การรับบางส่วน, discrepancy, return และการแก้รายการ unlisted ที่ส่วนกลางเป็นงาน WP19

### 5. สต๊อกร้าน

- ดูยอดคงเหลือและคำเตือนยอดต่ำเฉพาะสาขา
- ดู movement history พร้อมเหตุผล
- ผู้มี `takeaway.stock.manage` บันทึกรับเข้า ปรับยอด และของเสียได้
- การปรับยอด/ของเสียบังคับเหตุผลที่ UI และ movement เก็บ note ใน Takeaway database

### 6. KDS, Pickup และ QR

- KDS/Pickup refresh อัตโนมัติทุก 3 วินาทีและเปิดเต็มจอได้
- KDS มีตัวกรองจุดผลิตและเสียงแจ้งเตือนรายการใหม่
- Pickup ค้นหาด้วยเลขคิว เลขออเดอร์ หรือชื่อลูกค้า
- QR ลูกค้าสั่งเอง, paid-first capture, pickup token/status และ transition เดิมยังทำงานผ่าน regression

## Database และ API contract

Migration head: `p6takeaway0005`

- `takeaway_receipts`: เพิ่ม print audit fields และ copy-type constraint
- `takeaway_central_orders`: เพิ่ม branch-scoped idempotency key และ backfill รายการเดิม
- `takeaway_stock_movements`: เพิ่ม note
- เพิ่ม shift summary, receipt fetch/print audit, Store Central Order create/receive และ stock movement history API
- เพิ่ม station filter ให้ Kitchen ticket API

Migration ถูกทดลอง upgrade กับ Takeaway database ในเครื่องแล้ว ไม่ได้รันบน UAT/Production

## Automated evidence

| Gate | ผล |
| --- | --- |
| Backend full regression | `367` tests ผ่าน, skipped `1` |
| Focused Takeaway policy/contract | `10` tests ผ่าน |
| Takeaway service smoke | ผ่าน sale/receipt/shift/QR/KDS/Pickup/order/stock/refund/transfer/credit/ERP |
| Frontend type-check | ผ่าน |
| Frontend production PWA build | ผ่าน, `4,220` modules |
| Takeaway browser test | `5/5` ผ่าน |

Browser test ครอบคลุม role workspace เดิม 3 กรณี และเพิ่ม:

1. Counter ตัดเครือข่ายหลังโหลดเมนูแล้วขายต่อ ออกใบเสร็จในเครื่อง และแสดง outbox รอส่ง
2. Branch เปิด shift summary, Store Central Order และ Store Stock workflow ได้ตาม permission

Build มีคำเตือน chunk ใหญ่เดิม แต่ไม่มี compile/build failure

## Boundary และผลกระทบระบบ

- ใช้ Takeaway database และ migration chain เท่านั้น
- ไม่ import ข้อมูล Chambo จริง
- ไม่เปลี่ยน feature flag หรือ deployment image
- ไม่แก้ `/Users/user/Projects/erp-pos-run`
- ไม่ deploy UAT หรือ Production
- Restaurant/Retail backend regression ผ่านหลังเพิ่ม WP18

## Definition of Done

- [x] Counter ขายออฟไลน์และ retry แบบ idempotent ได้
- [x] Receipt ลูกค้า/ร้านและ reprint audit ทำงาน
- [x] Shift summary/variance/history และ unsynced-close guard ทำงาน
- [x] Store สั่ง regular/extra/unlisted และรับของครบได้
- [x] Store stock balance/movement/reason/warning ทำงานตาม permission
- [x] KDS/Pickup operator UX และ QR regression ผ่าน
- [x] Migration, smoke, backend, type-check, build และ browser tests ผ่าน
- [x] ไม่มี UAT/Production deployment หรือ real-data mutation

งานถัดไป: **WP19 — Central Operation Parity** ได้แก่ recipe/replenishment, central item resolution,
production lifecycle, partial receive/discrepancy/return, stock/transfer/credit control tower,
operational reports และ ERP events ของ workflow ใหม่
