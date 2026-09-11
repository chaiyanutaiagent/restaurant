# P5-POS-TAKEAWAY-MERGE-09

## สถานะ

`uat_deployed_full_isolated_readiness_passed_physical_printer_pending` — รวมการขายรับกลับเข้า
หน้า `/pos` แล้ว, deploy UAT, CI, browser smoke ที่ขนาด iPad และ full isolated readiness gate ผ่าน;
คงเหลือ physical Safari/iPad touch และ printer flow ก่อน owner sign-off

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
- [x] full isolated QR-to-ERP/Playwright readiness gate ผ่าน
- [ ] physical Safari/iPad touch และ printer flow ผ่านครบ

## Rollback

1. เปลี่ยน `FRONTEND_IMAGE` ใน UAT กลับเป็น
   `restaurant-pos-frontend:uat-pos-takeaway-c952f8d`
2. เปลี่ยน `BACKEND_IMAGE` ใน UAT กลับเป็น
   `restaurant-pos-backend:uat-auth-bypass-20260910`
3. recreate เฉพาะ backend และ frontend service ของ Compose project `restaurant-pos-uat-drill`
4. หากต้องคืน source/env UAT ล่าสุด ให้ใช้ backup
   `/home/behappyaiagent/restaurant-uat-deploy-backups/41d49d3`
5. backup ก่อนรวมหน้าเดิมยังอยู่ที่
   `/home/behappyaiagent/restaurant-uat-deploy-backups/c952f8d`
6. ไม่มี database migration ใน scope นี้ และ `/restaurant/wap/legacy` ยังพร้อมใช้งานระหว่าง UAT
7. Production ไม่ถูกเปลี่ยน

## Evidence

```text
business_type: restaurant
database_change: none
backend_change: none
source_commit: c952f8d
hardening_commit: 41d49d3
source_validation: frontend_type_check_and_build_passed
ci_push_run: 34553526406 passed
ci_pull_request_run: 34553529191 passed
hardening_ci_push_run: 34556131431 passed
hardening_ci_pull_request_run: 34556134248 passed
uat_frontend_image: restaurant-pos-frontend:uat-p5-hardening-41d49d3
uat_backend_image: restaurant-pos-backend:uat-p5-hardening-41d49d3
uat_previous_frontend_image: restaurant-pos-frontend:uat-pos-takeaway-c952f8d
uat_previous_backend_image: restaurant-pos-backend:uat-auth-bypass-20260910
uat_backup: /home/behappyaiagent/restaurant-uat-deploy-backups/41d49d3
uat_asset: /assets/index-BWeGI9bh.js
uat_health: passed
uat_route_redirect: /restaurant/wap -> /pos?channel=takeaway passed
uat_menu: 4 categories / 16 products passed
uat_cart_precheckout: 69.00 exact-payment button enabled passed
uat_browser_console_errors: 0
uat_document_horizontal_overflow_1024x768: 0
backend_unit_regression: 232/232 passed
browser_regression: 14/14 passed
load_reconnect_idempotency: 100/100 orders passed
backend_dependency_audit: zero known vulnerabilities
frontend_production_dependency_audit: zero known vulnerabilities
backend_pdf_runtime: weasyprint 70.0 generated PDF passed
full_isolated_gate: passed
full_isolated_artifact: /private/tmp/restaurant-p5-artifacts/p5-production-readiness-05-20260911T024453Z/manifest.txt
physical_safari_ipad_printer_flow: pending
production_activated: false
phase6_started: false
```
