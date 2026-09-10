# P5-POS-TABLET-UX-07

## สถานะ

`implementation_validated_uat_deploy_pending` — ปรับ Restaurant POS สำหรับ Tablet เสร็จใน source และผ่าน frontend type-check/build แล้ว การ deploy และ browser smoke บน `uat-pos.foodchainservice.com` รอ `mainserver` กลับมาออนไลน์ ส่วน physical workflow และเครื่องพิมพ์ยังต้องทดสอบกับอุปกรณ์จริง

## ปัญหาที่แก้

หน้าขายเดิมใช้งานได้ แต่การจัดพื้นที่บน iPad ยังไม่แยกหมวดสินค้า สินค้า และตะกร้าให้ชัด ปุ่มไปยังงานโต๊ะ/QR/KDS กระจายอยู่หลายหน้า และข้อมูลความพร้อมของเครื่องขาย กล้อง การซิงก์ และการพิมพ์ยังไม่มีจุดตรวจเดียว

## In scope

- ปรับ Restaurant POS เป็น layout สามส่วนบน Tablet landscape: หมวดสินค้า → สินค้า → ตะกร้า
- เพิ่มแถบทางลัดไปยังเปิดโต๊ะและ QR, รับกลับ, พักบิล, ออเดอร์ QR, KDS และลูกค้า โดยคง route และ permission เดิม
- ขยาย touch target ของจำนวนสินค้า แยก `พักบิล` ออกจาก `ล้างรายการ` และเพิ่มคำเตือนก่อนออกจากหน้าขณะมีสินค้าในตะกร้า
- เพิ่มหน้าต่างสถานะอุปกรณ์ กล้อง เครือข่าย รอบซิงก์ และการพิมพ์ พร้อมตัวเลือกพิมพ์ใบเสร็จอัตโนมัติเฉพาะเครื่อง ซึ่งปิดเป็นค่าเริ่มต้น
- เพิ่มสรุปสถานะในหน้าอุปกรณ์ โดยระบุชัดว่า activity ล่าสุดไม่ใช่การตรวจไฟหรือสายเครื่องพิมพ์
- เพิ่ม Playwright assertion สำหรับ layout 1024×768, route สำคัญ และ horizontal overflow

## Out of scope

- schema/database migration, backend API หรือ permission ใหม่
- delivery order domain; ปุ่มเดลิเวอรีแสดงเป็น `รอเปิดใช้` และไม่พาไป logistics เพราะ Restaurant Phase 5 ยังไม่มี flow นี้
- เปลี่ยน table-session QR, customer ordering, KDS หรือ checkout business logic
- native printer driver หรือการอ้างว่าเว็บตรวจสถานะไฟ/กระดาษของเครื่องพิมพ์จริงได้
- Production deploy, final domain switch, Phase 6 Takeaway หรือ Retail Phase 7

## Acceptance criteria

- [x] ที่ viewport 1024×768 หมวดสินค้า สินค้า และตะกร้าเรียงสามส่วนและไม่มี horizontal overflow ใน automated assertion
- [x] หัวตะกร้า รายการ และแผงชำระเงินเรียงต่อกันโดยไม่ซ้อนทับเมื่อเนื้อหาสูงกว่าจอ Tablet
- [x] ทางลัดโต๊ะ/QR, รับกลับ, ออเดอร์ QR และ KDS ใช้ route/permission ที่มีอยู่
- [x] เดลิเวอรีไม่เปิด route ที่ให้ความหมายผิด
- [x] touch target หลักของตะกร้าไม่น้อยกว่า 44px และการล้างบิลต้องยืนยัน
- [x] auto-print เป็น per-device preference และปิดโดยค่าเริ่มต้น
- [x] frontend type-check/build ผ่านและไม่มี schema/backend change
- [x] refresh frontend dependency audit แล้ว; ผลใหม่ถูกบันทึกและ Production sign-off ยังคง pending
- [ ] browser smoke บน UAT hostname ผ่าน
- [ ] physical iPad flow และ printer checks ที่เกี่ยวข้องผ่าน

## Rollback

- revert ไฟล์ frontend และ Playwright ของ scope นี้ได้โดยไม่มี data rollback
- UAT frontend ต้องเก็บ image/tag เดิมไว้ก่อน recreate เพื่อ rollback ได้ทันที
- Production และฐานข้อมูลไม่อยู่ในขอบเขต จึงไม่มี production/data rollback

## Evidence

```text
business_type: restaurant
target_database_change: none
source_validation: frontend type-check/build passed
frontend_production_audit: 4_rows_3_high_1_low_security_review_pending
frontend_full_audit: 11_rows_7_high_3_moderate_1_low_security_review_pending
uat_deployment: pending_mainserver_online
physical_iPad_business_flow: pending
printer_uat: pending
production_activated: false
phase6_started: false
```
