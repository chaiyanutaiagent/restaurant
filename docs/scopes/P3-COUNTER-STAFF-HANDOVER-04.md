# Scope ID: P3-COUNTER-STAFF-HANDOVER-04

สถานะ: **Automated/API verification complete — tablet visual confirmation pending**
Phase: **Phase 3 — Dedicated Counter, Kitchen และ Device Pairing**
วันที่เริ่ม: 1 สิงหาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

Device pairing ต้องเป็นขั้นตอนติดตั้งครั้งเดียว ไม่ใช่ตัวตนของผู้รับผิดชอบเงินในแต่ละกะ
แม้ POS มี `CashierShift.user_id` อยู่แล้ว แต่ dedicated Counter ยังไม่แสดง Employee ID ชัดเจน,
ไม่มีทางลัดที่ปลอดภัยสำหรับส่งเครื่องให้คนถัดไป และการเปิด/ปิดกะยังไม่มี audit ที่ผูก Counter device

## In Scope

- คง device pairing ข้ามการปิด/เปิดแอป และแยกจาก staff session
- แสดงชื่อและ Employee ID ของผู้รับผิดชอบใน Counter และ POS header
- ยืนยันผู้เปิดกะโดยใช้ staff session ปัจจุบัน ไม่กรอก ID ซ้ำ
- เพิ่ม `เปลี่ยนกะ` ที่บังคับปิดยอด, logout staff และคง device pairing ไว้
- ป้องกันเปลี่ยนกะขณะ offline หรือมีสินค้าในตะกร้าที่ยังไม่พักบิล
- แยก shift cache ตาม user และ Branch เพื่อไม่ให้คนถัดไปรับกะ cached ของคนก่อน
- บันทึก `restaurant.staff_shift.open` และ `pos.shift.close` พร้อม user, Branch, Counter device,
  ยอดเงิน, IP และ user agent ใน operational audit
- ปฏิเสธ Counter device ที่ Company/Branch ไม่ตรงกับ staff context

## Operator Flow

1. Manager pair เครื่องครั้งเดียวตอนติดตั้ง, rotate หรือหลัง revoke เท่านั้น
2. พนักงานลงชื่อบน Counter แล้วระบบแสดงชื่อกับ Employee ID
3. กดเปิดหน้าขาย; menu bootstrap เปิดกะและบันทึกผู้เปิด, เวลา, Branch, location และ device อัตโนมัติ
4. เมื่อเปลี่ยนคน เลือก `เปลี่ยนกะ / พนักงาน`, นับเงินและยืนยันปิดกะ
5. ระบบ logout เฉพาะพนักงานและกลับหน้า Counter ให้คนถัดไปลงชื่อ โดยไม่ Pair เครื่องใหม่

## Database / Ownership

- ไม่มี migration ใหม่
- `cashier_shifts.user_id` ยังคงเป็น canonical owner ของกะ
- evidence ผู้เปิด/ปิดและ device เก็บใน Restaurant operational `audit_logs`
- device credential ยังอยู่ Identity-owned registry และ user/device tokens ยังแยกกัน
- default runtime คง identity `legacy`, Restaurant service `legacy`, projector disabled

## Out of Scope

- cashier PIN แบบใหม่หรือ biometric login; ใช้ staff credential เดิมเพื่อลด credential surface
- โอนกะที่ยังเปิดจาก user หนึ่งไปอีก user หนึ่งโดยไม่ปิดยอด
- manager force-close กะแทนพนักงาน, inactivity auto-lock, MDM และ production activation

## Acceptance Criteria

- [x] การเปิดแอป/refresh ไม่บังคับ Pair ซ้ำเมื่อ device credential ยัง valid
- [x] Counter แสดง Employee ID และผู้เปิดกะโดยไม่ให้กรอก ID ซ้ำ
- [x] `เปลี่ยนกะ` ปิดกะและ logout staff แต่ไม่ล้าง device session
- [x] offline และตะกร้าที่ยังไม่พักบิลไม่สามารถส่งมอบกะได้
- [x] shift cache ของ user/Branch คนก่อนถูกปฏิเสธ
- [x] open/close audit มี staff user ID และ Counter device ID/code
- [x] handover ที่ไม่มี Counter device token ถูกปฏิเสธด้วย HTTP 403
- [x] Counter device คนละ Branch ถูกปฏิเสธด้วย HTTP 403
- [x] backend regression 155 tests และ frontend type/build ผ่าน
- [x] live database fingerprints ไม่เปลี่ยน
- [ ] ยืนยัน layout และการกด flow จริงบน tablet
- [x] worktree commit โดยไม่ push

## Rollback

1. revert source commit ของ Scope นี้
2. POS shift API เดิมยังใช้ได้โดยไม่มี device header และไม่ต้อง downgrade schema
3. device pairing, workspace และ offline authorization Scope 01–03 ไม่ได้รับผลกระทบ

## Execution Record

- Starting commit: `cf56305`
- UAT runtime: isolated legacy/Platform clones, current frontend/backend, projector disabled
- Dedicated Counter API UAT บน final backend build: menu bootstrap เปิด shift
  `8b4f6169-34a8-43ee-a0c4-dbeee87ff6f5` และ handover ปิดสำเร็จ
- Audit UAT: `restaurant.staff_shift.open` และ `pos.shift.close` มี user
  `d2607c04-6c48-4d34-8548-e532f06f8dbf`, device code `C-D39DXTWA5D`, IP
  `192.168.65.1` และ user agent `Codex-P3-UAT/1.0`
- Missing-device handover UAT: HTTP `403`
- Cross-Branch guard UAT: device `C-LCP76MSN5S` กับ staff คนละ Branch ได้ HTTP `403`
- Backend regression: 155 tests ผ่าน
- Frontend: TypeScript type-check และ production build ผ่าน; PWA artifacts สร้างสำเร็จ
- Live fingerprints ไม่เปลี่ยน: legacy `6b7c8d9e0f12:1:4:7:120`,
  Platform `p1platform0003:1:1:7:9`, Restaurant `p1restaurant0003:1:4:23:23`
- Evidence artifact:
  `/private/tmp/restaurant-p3-artifacts/p3-counter-staff-handover-04-20260801T042612Z/manifest.txt`
- Tablet visual confirmation: pending refresh/interaction บน Chrome ที่ผู้ใช้เปิดไว้
