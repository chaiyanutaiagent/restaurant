# WP6-SUPPLY-CHAIN-DISTRIBUTION-01 — Demand และกระจายสินค้าสำเร็จรูป

วันที่อนุมัติและเริ่มทำ: 2026-09-14

สถานะ: **completed_local — WP6-A ถึง WP6-D ผ่าน automated local gate; physical UAT พักตามคำสั่ง owner**

หมายเหตุ: WP6 นี้เป็น Work Package ของ Foodchainservice Platform หลัง WP5 และไม่ใช่ Phase 6 Takeaway เดิม

## เป้าหมาย

ให้ Restaurant POS, Takeaway POS และ Retail POS ส่งความต้องการสินค้าเข้าส่วนกลางในรูปแบบเดียวกัน
จากนั้นจัดสรรสินค้าสำเร็จรูปของแต่ละ Brand จาก READY ไปยังคลังสาขา พร้อมติดตามส่ง–รับ–ปฏิเสธ–คืน
และตรวจยอดแยก Module/Brand/Branch โดยไม่สร้าง stock ledger ซ้ำ

## WP6-A — Audit และ ownership

- [x] ตรวจ Restaurant replenishment/Central Order, Takeaway central/transfer, Retail stock/transfer และ WP5 READY
- [x] กำหนด operational POS เป็น owner ของ source document และ Company Distribution เป็น normalized orchestration
- [x] ยืนยัน `TransferOrder`/`StockMovement` เดิมเป็น stock authority เพียงชุดเดียว
- [x] ล็อก module/business type, tenant, Brand/Branch/Product/location และ database boundary

## WP6-B — Unified demand

- [x] normalized demand contract รองรับ `restaurant_pos`, `takeaway_pos`, `retail_pos`
- [x] เก็บ source type/id, needed date, quantity, unit และ idempotency fingerprint
- [x] ตรวจ Brand business type, active BrandBranch และ Brand READY product จาก server
- [x] รองรับจัดสรรบางส่วน/หลาย shipment โดยไม่เกิน demand

## WP6-C — Shipment lifecycle

- [x] plan สร้าง Transfer เดิมและจอง READY stock
- [x] dispatch ตัด READY; receive รับเข้าคลังสาขาแบบสะสม/ปิดรับได้
- [x] reject บันทึก short/discrepancy และไม่เพิ่ม stock ขาย
- [x] return หลังรับใช้ reverse Transfer จริงกลับ READY
- [x] cancel คืน reservation ก่อน dispatch; ทุก action มี idempotency/audit

## WP6-D — UI, reporting และ gates

- [x] Company Admin `/company-distribution` มี overview, demand, shipment และ reconciliation
- [x] report แยก Module/Brand/Branch พร้อม shipped/received/rejected/returned/in-transit/net-received
- [x] dedicated permissions และ branch-role restriction
- [x] write flag ปิดโดยค่าเริ่มต้นและแยกจาก WP5
- [x] unit/API/smoke/browser/migration rehearsal ถูกจัดเตรียม
- [x] automated full gate ผ่านและบันทึกผลใน `WP6-PHASE-GATE-02.md`
- [ ] physical Safari/iPad dispatch/receive/reject/return UAT (พักไว้)

## In scope / target database

- Company demand/shipment/event ใน Legacy ERP shared-service database
- reference Company/Brand/Branch/Product/Location และ existing Transfer/Stock ledger ในฐานเดียวกัน
- Takeaway ส่งผ่าน contract/outbox ในอนาคต ห้าม query Takeaway Database โดยตรง
- Company Admin API/UI/report/permission/dark-launch gate

## Out of scope

- ไม่เปิด WP5 หรือ WP6 write flag ใน UAT/Production
- ไม่ deploy/migrate UAT/Production และไม่ import Chambo จริง
- ไม่เปลี่ยน sale/payment/kitchen/QR flow ของ POS ทั้งสามระบบ
- ไม่สร้าง route optimization, driver fleet, supplier marketplace หรือ forecasting AI
- ไม่สร้าง Hotel PMS demand

## Acceptance criteria

- [x] demand สามระบบอยู่ในคิวเดียว แต่ Module/Brand/Branch ownership ไม่ปะปน
- [x] plan/dispatch/receive/return ใช้ Transfer/Stock ledger เดิม
- [x] replay ไม่จอง/ตัด/รับ/คืนซ้ำ และ competing reservation ตัดเกิน READY ไม่ได้
- [x] reject/return/in-transit ตรวจยอดได้อย่างชัดเจน
- [x] tenant และ company-only role isolation อยู่ใน contract/test
- [x] automated gate ผ่านทั้งหมด
- [x] ไม่มี UAT/Production activation

## Rollback

ปิด `COMPANY_DISTRIBUTION_WRITES_ENABLED`, export/reconcile linked Transfer/Event manifest,
ให้ POS/ERP/Transfer เดิมทำงานต่อโดยไม่พึ่ง WP6 และ downgrade `p14dist0016 → p13kitchen0015`
เฉพาะเมื่อยังไม่มีข้อมูลจริงหรือมี backup/restore ที่ตรวจแล้ว

รายละเอียด ownership อยู่ที่ `docs/architecture/company-supply-chain-distribution.md`
หลักฐานตรวจรับอยู่ที่ `docs/scopes/WP6-PHASE-GATE-02.md`
