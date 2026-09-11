# P5-POS-WORKSPACE-THEME-08

## สถานะ

`implementation_validated_uat_deploy_pending` — รวมภาษาภาพของหน้าปฏิบัติการ POS ใน source แล้ว และผ่าน frontend type-check/build; รอ deploy และ browser smoke บน UAT ก่อนส่งให้ทดสอบบน Safari/iPad

## ปัญหาที่แก้

หน้าขายหลักใช้ Tablet POS theme ใหม่ แต่เมื่อเปิดหน้าโต๊ะ, รับกลับ, ออเดอร์ QR, รายละเอียด/รวมบิล หรือลูกค้า ระบบกลับไปใช้ AppShell และ Sidebar ของ ERP ทำให้พนักงานรู้สึกว่าออกจากพื้นที่ขาย ส่วน KDS ไม่มีทางลัดกลับไปพื้นที่งาน POS ชุดเดียวกัน

## In scope

- ใช้หัวหน้าสถานะสาขา, จุดขาย, พนักงาน และ online/offline แบบเดียวกับหน้าขายบนหน้าปฏิบัติการ POS
- ใช้แถบทางลัดเดียวกันสำหรับขายหน้าร้าน, เปิดโต๊ะ/QR, รับกลับ, ออเดอร์ QR, KDS และลูกค้า โดยเคารพ permission เดิม
- คง delivery เป็น disabled พร้อมข้อความ `รอเปิดใช้`
- ใช้พื้นหลัง, การ์ด, radius, shadow และ touch target ชุดเดียวกันบนหน้าโต๊ะ, รับกลับ, ออเดอร์ และลูกค้า
- คง KDS เป็น dark workspace สำหรับครัว แต่เพิ่มแถบทางลัดร่วมเฉพาะ route พนักงาน; device-only KDS `/kitchen` ไม่เปลี่ยน
- ปิด horizontal overflow ของพื้นที่สินค้า POS ที่ Safari แสดง scrollbar จาก overflow ต่างแกน
- เพิ่ม Playwright assertions สำหรับ operational shell, active navigation และ horizontal overflow ที่ 1024×768

## Out of scope

- เปลี่ยน API, schema, permission หรือ business flow
- เปลี่ยน customer-facing QR menu หรือ device-only counter/kitchen/pickup workspace
- เปิด delivery domain
- Production deploy, final domain หรือ Phase 6

## Acceptance criteria

- [x] frontend type-check/build ผ่าน
- [x] หน้าขายใช้ navigation component ร่วมโดยไม่เปลี่ยนการเตือนเมื่อมีสินค้าในตะกร้า
- [x] หน้าโต๊ะ, รับกลับ, ออเดอร์ QR, session และลูกค้าใช้ POS operational shell แทน ERP Sidebar
- [x] KDS ของพนักงานมี navigation ร่วม แต่ device-only KDS ไม่เปลี่ยน
- [x] active workspace และ permission visibility ทำงานจาก route/permission เดิม
- [x] delivery ยัง disabled
- [x] product grids ซ่อน horizontal overflow และยังเลื่อนแนวตั้งได้
- [ ] browser smoke บน UAT ที่ 1024×768 ผ่านทุก operational route
- [ ] physical Safari/iPad visual and touch check ผ่าน

## Rollback

- revert frontend และ Playwright files ใน scope นี้ได้โดยไม่มี data rollback
- UAT ต้องเก็บ frontend image ก่อนหน้าไว้สำหรับ recreate
- ไม่มี database หรือ Production rollback เพราะอยู่นอกขอบเขต

## Evidence

```text
business_type: restaurant
database_change: none
backend_change: none
source_validation: frontend_type_check_and_build_passed
uat_deployment: pending
uat_browser_smoke: pending
physical_safari_ipad_check: pending
production_activated: false
phase6_started: false
```
