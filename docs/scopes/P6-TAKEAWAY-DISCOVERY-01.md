# P6-TAKEAWAY-DISCOVERY-01 — Chambo Discovery และ Takeaway Boundary Plan

วันที่จัดทำ: 2026-09-11

สถานะ: **discovery_complete — implementation เดินหน้าตาม owner dark-launch exception**

เอกสารนี้คงไว้เป็น baseline การสำรวจ ส่วนสถานะ implementation ปัจจุบันดูที่
`P6-TAKEAWAY-IMPLEMENTATION-06.md`; activation ยังรอ Restaurant Completion Gate

Source reference: `/Users/user/Projects/erp-pos-run` commit `15a1de1`

Target reference: `/Users/user/Projects/restaurant` commit `27c9c10`

เอกสารต่อเนื่อง:

- `P6-TAKEAWAY-CAPABILITY-MATRIX-02.md`
- `P6-TAKEAWAY-BOUNDARY-DRAFT-03.md`
- `P6-CHAMBO-DATA-CONTRACT-04.md`
- `P6-CHAMBO-DRY-RUN-05.md`

## เป้าหมาย

เตรียมแผนสร้าง Foodchainservice Takeaway POS จากความสามารถที่พิสูจน์แล้วใน Chambo
โดยอ่านโปรเจกต์เดิมแบบ read-only และไม่คัดลอกฐานข้อมูล production, secret, brand-specific
configuration หรือ Restaurant operational tables มาใช้ร่วมกัน

เอกสารนี้เป็นงานสำรวจและออกแบบเท่านั้น ไม่ได้เปิด Takeaway runtime, ไม่สร้างฐานข้อมูล
Takeaway และไม่ถือว่า Restaurant Phase 5 ผ่าน Completion Gate

## ขอบเขตระบบที่ต้องแยกให้ชัด

Foodchainservice มีสอง flow ที่ชื่อใกล้กันแต่เป็นคนละระบบ:

1. **Restaurant รับกลับ** — เป็นช่องทางขายของ Restaurant POS ที่ `/pos?channel=takeaway`
   ใช้ Restaurant order, stock, payment, kitchen และ report เดิม
2. **Takeaway POS SaaS** — เป็นระบบร้านจุดขายแบบ Chambo มีหน้าร้าน ปิดกะ สั่งสินค้า
   จากครัวกลาง ผลิต จัดส่ง รับของ และเครดิตแฟรนไชส์ โดยต้องใช้ Takeaway Database
   และ permission namespace ของตัวเอง

ห้ามให้ระบบที่ 2 เขียนหรืออ่าน Restaurant operational tables โดยตรง แม้ UI และขั้นตอน
บางส่วนจะคล้ายกัน

## สิ่งที่พบใน Chambo และควรนำแนวคิดมาใช้

### หน้าร้าน

- Route กลางตามแบรนด์ เช่น `/store/:brandSlug/orders`
- ขายแบบ paid-first, พิมพ์สลิปลูกค้าและสลิปร้าน
- รองรับ offline sync และ idempotency สำหรับออเดอร์หน้าร้าน
- ปิดกะได้หลายรอบในวันเดียวและเก็บผู้ปิดกะ
- รวมใบสั่งครัวกลางรายวัน กดซ้ำแล้วไม่สร้างเอกสารซ้ำ
- สั่งสินค้าเพิ่มนอกยอดปิดกะ และขอสินค้าที่ไม่มีใน catalog ได้
- ติดตามการจัดส่ง รับสินค้า และ stock ของสาขา

### ครัวกลาง

- รับและอนุมัติใบสั่งจากหลายสาขา
- รวมยอดผลิตตามสินค้าสำเร็จและวัตถุดิบ
- สูตรขาย สูตรผลิต สูตรซ้อน version, yield loss และ unit conversion
- production batch, stock area, stock movement และ transfer ไปสาขา
- ปรับจำนวนแพ็ก/ส่งจริงและให้สาขายืนยันจำนวนรับจริง
- dashboard และรายงานแยกแบรนด์/สาขา/พนักงาน/รอบขาย

### แฟรนไชส์

- credit account, reserve, capture, release, refund และ adjustment ledger
- เติมเครดิตด้วย QR/สลิปและอนุมัติจากส่วนกลาง
- แยกสาขาบริษัทกับสาขาแฟรนไชส์

## สิ่งที่ห้ามยกมาทั้งชุด

- Route และค่าเริ่มต้นที่ hardcode เป็น `chambo`
- โลโก้ ชื่อร้าน เมนู ราคา สูตร และข้อมูลยอดคงเหลือจริงของ Chambo
- Android default route, package/release setting และ production update channel ของ Chambo
- credential, token, upload, backup หรือ production database จาก `erp-pos-run`
- permission fallback กลุ่ม `fb.*` ที่ใช้ระหว่างการเปลี่ยนผ่าน
- router/model เดิมที่ผูกทุก domain ไว้ใน Restaurant database transaction เดียว
- migration chain เดิมทั้งชุด เพราะ Takeaway ต้องมี migration head และ recovery lifecycle ของตัวเอง

## สถาปัตยกรรมเป้าหมาย

```text
Foodchainservice Control Plane
  Company / Brand / Branch / Staff / Device / Entitlement
                    |
                    | signed business context + immutable references
                    v
Takeaway API/Service --------------------> Takeaway Database
  menu / counter / order / shift           operational source of truth
  queue / kitchen / pickup / payment
  central order / production / transfer
  stock / credit / receipt / outbox
                    |
                    | versioned events; no cross-database foreign keys
                    v
Shared ERP contracts
  accounting / consolidated reporting / audit / notification
```

Canonical workspace ใช้ route ที่จองไว้แล้ว:

- `/app/takeaway/brands`
- `/app/takeaway/:brandSlug`
- `/app/takeaway/:brandSlug/branches/:branchId/counter`
- `/app/takeaway/:brandSlug/branches/:branchId/kitchen`
- `/app/takeaway/:brandSlug/branches/:branchId/pickup`
- `/app/takeaway/:brandSlug/branches/:branchId/settings`

API ต้องอยู่ใน namespace Takeaway และถูก guard ด้วย `business_type=takeaway`, entitlement,
staff scope และ device binding ห้ามใช้ Restaurant router เป็นทางลัด

## หลักการ stock ครัวกลางหลายแบรนด์

วัตถุดิบเดียวกัน เช่น หมูชนิดเดียวกันสำหรับหมูแดดเดียวและหมูย่าง สามารถตัดจาก stock
กองกลางเดียวกันได้ โดยให้ stock ownership อยู่ระดับ Company + Stock Location + Item/Lot
แล้วเก็บ Brand, Production Batch และ Recipe Version เป็นมิติการใช้วัตถุดิบ ไม่สร้างยอดหมูซ้ำ
แยกคนละแบรนด์

เงื่อนไขสำคัญ:

- ทุก movement ต้องมี source document และ idempotency key
- reserve/issue/return/waste ต้องแยกตาม production batch และ brand ที่ใช้
- lot, expiry, unit conversion, yield และ cost allocation ต้องตรวจสอบย้อนหลังได้
- รายงาน ERP รวมยอดบริษัทได้ และกรองตาม `business_type`, brand, branch และ channel ได้

## แผนย้ายความสามารถจาก Chambo

ใช้การย้ายแบบ contract-first ไม่ copy database:

1. ทำ capability matrix เทียบ Chambo กับ Takeaway target และเลือกเฉพาะ flow ที่ต้องใช้
2. ออกแบบ schema/permission/event contract ใหม่ใน Takeaway bounded context
3. แยก shared package เฉพาะส่วนที่ไม่มี Restaurant model dependency เช่น money, unit,
   printer, QR, offline envelope และ idempotency helper
4. เขียน adapter/importer ที่ validate Company/Brand/Branch mapping และสร้าง dry-run report
5. export Chambo ผ่าน versioned data contract แล้ว import เข้า isolated Takeaway database
6. กระทบยอดจำนวน record, ยอดเงิน, stock, credit และเอกสารก่อนอนุญาต cutover
7. เก็บ Chambo เดิมเป็นระบบ rollback จนผ่าน owner sign-off และ retention window

ข้อมูลเริ่มต้นที่ควรย้ายเมื่อได้รับอนุมัติ:

- Brand/Branch mapping และ configuration ที่ไม่ใช่ secret
- menu/product/unit/recipe/version/yield configuration
- stock location/area และ opening balance ที่เจ้าของอนุมัติ
- credit opening balance พร้อม reconciliation document
- ผู้ใช้ผ่าน Control Plane assignment ใหม่ ไม่ย้าย password/session/token

ประวัติออเดอร์เก่าควรเก็บเป็น archive/import batch แบบ immutable และไม่ทำให้เลขเอกสารใหม่ชนกัน

## Work Packages หลัง Restaurant Completion Gate

### P6-TAKEAWAY-BOUNDARY-01

- Takeaway database URL/session factory/service health
- migration chain, backup, restore, checksum และ isolated restore drill
- business-context routing ที่ปฏิเสธ Restaurant/Retail context

### P6-TAKEAWAY-STORE-02

- menu, paid-first counter, receipt และ offline/idempotent order sync
- shift rounds, close shift และ staff attribution
- daily replenishment, extra/unlisted stock request และ store receiving

### P6-TAKEAWAY-CENTRAL-03

- central order approval, production aggregation/batch และ stock issue
- pack, ship, transfer, receive และ discrepancy workflow
- shared raw-material stock with brand/batch cost allocation

### P6-TAKEAWAY-CREDIT-04

- company-owned/franchise policy
- reserve/capture/release/refund/top-up/adjustment ledger
- audit, approval และ reconciliation

### P6-TAKEAWAY-QR-05

- counter queue และ QR รับกลับ
- customer ordering, kitchen job, pickup status และ checkout/payment reference
- printer/device pairing และ public-token security

### P6-TAKEAWAY-ERP-GATE-06

- accounting/reporting outbox contract และ replay/dead-letter handling
- tenant/brand/branch isolation, role/device security และ lost-ack tests
- QR → Order → Payment → Kitchen → Pickup → Receipt/Stock/Credit → ERP reconciliation
- Takeaway backup/restore และ Restaurant/Retail regression

## Gate ก่อนเริ่ม implement

ก่อนเปิด Work Package แรกต้องมีหลักฐานครบ:

- Restaurant physical iPad UAT ทั้ง dine-in และรับกลับ
- printer, offline/reconnect/lost-ack และ ERP reconciliation ผ่าน
- ปิด temporary UAT auto-login และ role test ตามผู้ใช้จริงผ่าน
- Platform Owner ลงนาม Restaurant Completion Gate
- สร้าง Phase 6 branch จาก Restaurant release commit ที่อนุมัติแล้ว

หากยังไม่ครบ อนุญาตเฉพาะ discovery, mapping, schema draft และ test-plan ที่ไม่เปิด runtime
และไม่เปลี่ยน production/UAT data

## Definition of Ready สำหรับ P6-TAKEAWAY-BOUNDARY-01

- [ ] Restaurant release commit และ owner sign-off ถูกระบุชัดเจน
- [ ] Chambo capability matrix และ data-owner approval ครบ
- [ ] Takeaway schema, permission และ event contract ผ่าน review
- [ ] migration/backup/restore/reconciliation plan ผ่าน review
- [ ] ไม่มี secret หรือ production dump อยู่ใน Git
- [ ] rollback owner, RPO, downtime และ acceptance evidence ถูกระบุ
