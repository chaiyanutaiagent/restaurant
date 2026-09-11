# P5-POS-TAKEAWAY-MERGE-09

## สถานะ

`uat_deployed_browser_smoke_passed_full_isolated_rerun_pending` — รวมการขายรับกลับเข้า
หน้า `/pos` แล้ว, deploy เฉพาะ frontend UAT, CI และ browser smoke ที่ขนาด iPad ผ่าน;
full isolated readiness rerun ยัง pending เพราะ Docker registry timeout ขณะอ่าน metadata ของ
`nginx:1.25-alpine` สองครั้งก่อนเริ่มสร้างฐานทดสอบ

## ปัญหาที่แก้

พนักงานเคยต้องออกจากหน้า POS ไปใช้ `/restaurant/wap` เพื่อขายรับกลับ ทั้งที่หน้า POS มีเมนู,
ตะกร้า, ลูกค้า และการรับชำระอยู่แล้ว ทำให้มีหน้าขายซ้ำและเสี่ยงให้ขั้นตอนหน้าร้านต่างกัน

## In scope

- เพิ่ม `channel=takeaway` ในหน้า `/pos` โดยใช้ layout, หมวดเมนู, ตะกร้า, ลูกค้า และช่องทางชำระเดิม
- ใช้เมนูกลางของ Restaurant เป็นรายการและราคาสำหรับรับกลับ
- ใช้ order engine เดิมเพื่อออกเลขคิว, offline outbox, idempotent sync, stock/accounting handoff
- คงลำดับพิมพ์สลิปลูกค้าก่อนพิมพ์สลิปครัวและสร้างงานใน KDS
- เปลี่ยน `/restaurant/wap` เป็น redirect ไป `/pos?channel=takeaway`
- เก็บ `/restaurant/wap/legacy` เป็น fallback ที่ไม่แสดงในเมนูสำหรับผู้ใช้ที่มี `fb.order.create`
  แต่ไม่มี `pos.sale.create` และใช้เป็น rollback ระหว่าง UAT
- คง `/counter/orders`, `/store/:brandSlug/orders`, QR โต๊ะ และ QR รับกลับสำหรับลูกค้าไว้เหมือนเดิม
- แก้ยอดบนสลิปออฟไลน์ให้แยกยอดสินค้า, เงินรับ และเงินทอนถูกต้อง

## Out of scope

- ลบ API, schema หรือ component ของ WAP ที่ Counter และ Brand Store ยังใช้
- เปิด delivery domain
- Production deployment หรือ final domain switch
- เปลี่ยน permission model

## Acceptance criteria

- [x] frontend type-check และ production build ผ่าน
- [x] CI ของ commit ผ่าน
- [x] `/restaurant/wap` redirect ไป `/pos?channel=takeaway`
- [x] โหมดรับกลับแสดง 4 หมวดและ 16 เมนู UAT พร้อมราคากลาง
- [x] ปิดส่วนลด/แลกแต้ม/exchange ในโหมดรับกลับเพื่อให้ยอดเมนู, stock และ KDS ตรงกัน
- [x] ตะกร้าและการรับเงินแสดงยอดถูกต้อง และปุ่มรับเงินพร้อมเมื่อยอดครบ
- [x] browser smoke UAT ไม่มี console error และไม่มี horizontal overflow ที่ 1024×768
- [x] backend unit regression สำหรับ WAP offline และ operational handoff ผ่านบน UAT container
- [ ] full isolated QR-to-ERP/Playwright readiness gate rerun ผ่าน; blocked เฉพาะ Docker registry timeout ก่อนเริ่ม test
- [ ] physical Safari/iPad touch และ printer flow ผ่านครบ

## Rollback

1. เปลี่ยน `FRONTEND_IMAGE` ใน UAT กลับเป็น
   `restaurant-pos-frontend:uat-pos-categories-47c583a`
2. recreate เฉพาะ frontend service ของ Compose project `restaurant-pos-uat-drill`
3. หากต้องคืน source UAT ให้ใช้ backup
   `/home/behappyaiagent/restaurant-uat-deploy-backups/c952f8d`
4. ไม่มี database migration ใน scope นี้ และ `/restaurant/wap/legacy` ยังพร้อมใช้งานระหว่าง UAT
5. Production ไม่ถูกเปลี่ยน

## Evidence

```text
business_type: restaurant
database_change: none
backend_change: none
source_commit: c952f8d
source_validation: frontend_type_check_and_build_passed
ci_push_run: 34553526406 passed
ci_pull_request_run: 34553529191 passed
uat_frontend_image: restaurant-pos-frontend:uat-pos-takeaway-c952f8d
uat_previous_frontend_image: restaurant-pos-frontend:uat-pos-categories-47c583a
uat_backup: /home/behappyaiagent/restaurant-uat-deploy-backups/c952f8d
uat_asset: /assets/index-DGy85Syo.js
uat_health: passed
uat_route_redirect: /restaurant/wap -> /pos?channel=takeaway passed
uat_menu: 4 categories / 16 products passed
uat_cart_precheckout: 69.00 exact-payment button enabled passed
uat_browser_console_errors: 0
uat_document_horizontal_overflow_1024x768: 0
backend_unit_regression: test_wap_offline + test_operational_handoff passed
full_isolated_gate_attempts: 2 blocked before test by nginx:1.25-alpine registry metadata timeout
physical_safari_ipad_printer_flow: pending
production_activated: false
phase6_started: false
```
