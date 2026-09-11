# Scope ID: P5-COMPLETION-NONDEVICE-04

สถานะ: **Non-device completion gate passed — physical/visual UAT และ owner sign-off pending**

Phase: **Phase 5 — Restaurant Completion Gate**

## Owner direction

เมื่อ 1 สิงหาคม 2026 owner ระบุว่าอุปกรณ์จริงยังไม่มาและให้เก็บการทดสอบบนอุปกรณ์ไว้ก่อน
Scope นี้จึงทำเฉพาะงานที่ตรวจได้โดยไม่ใช้อุปกรณ์จริง ไม่มีการอ้างว่า physical/visual UAT ผ่าน

## Outcome

- เพิ่ม Company Owner ใน Restaurant permission smoke ร่วมกับ Manager, Cashier, Kitchen และ recipe/cost
- ยืนยัน Company Owner ใช้ Restaurant API ตามสิทธิ์ได้ แต่เข้า Platform boundary ด้วย ordinary user token ไม่ได้
- เพิ่ม explicit `business_type=retail_pos` compatibility smoke ตั้งแต่ signed business context → POS shift
  → cash sale/payment → stock → accounting/outbox → daily report → close-shift reconciliation
- ยืนยัน idempotent retry ด้วย `client_order_id` เดิมไม่สร้าง sale, payment, stock movement,
  journal entry หรือ outbox ซ้ำ
- พบและแก้ stock access precedence ที่ทำให้ role ซึ่งมีทั้งสิทธิ์คลังกลางและหน้าร้าน เช่น Company Owner
  มองไม่เห็น store location ของ Retail Brand ที่ไม่มีคลังกลาง โดยยังจำกัด Company/Branch/Brand ตามเดิม
- เพิ่ม unit regression สำหรับ role ที่มีสิทธิ์ทั้ง store และ central stock

## Verification

ผล isolated clean-room gate วันที่ 1 สิงหาคม 2026:

- backend unit regression `189` tests ผ่าน
- Company Owner, Manager, Cashier, Kitchen และ recipe/cost permission smoke ผ่าน
- role preset policy และ approval regression ผ่าน
- Retail POS sale `107.00` ผ่าน; retry ไม่ซ้ำ, stock `10 → 9`, report `107.00`,
  close-shift difference `0`
- Retail token ถูกปฏิเสธจาก Restaurant API ด้วย `403` และ Platform API ด้วย `401`
- frontend type-check และ production build ผ่าน
- pre-Git repository safety และ shell syntax ผ่าน; `.env` local ถูก ignore และไม่ได้ stage

คำสั่ง gate:

```bash
P5_COMPLETION_ADMIN_PASSWORD='PASSWORD_AT_LEAST_16_CHARS' \
  scripts/rehearse-phase5-completion-nondevice.sh --yes
```

Gate ยอมเขียนเฉพาะ Compose project ที่ชื่อขึ้นต้นด้วย `restaurant-p5-completion`, ใช้ฐานข้อมูล/volume
แยกชั่วคราว และลบ stack กับ volume อัตโนมัติเมื่อจบ

## Remaining completion blockers

- [ ] Physical/visual UAT บนอุปกรณ์จริงเมื่อ hardware มาถึง
- [ ] Security owner ยอมรับ dependency exceptions ที่บันทึกใน `P5-UAT-SECURITY-03`
- [ ] Production checklist, operator handoff และ controlled owner sign-off
- [ ] Platform Owner อนุมัติ Restaurant completion

Phase 5 และ Restaurant Completion Gate ยังไม่ปิด และห้ามเริ่ม Phase 6 หรือ production activation
จนกว่ารายการที่เหลือจะผ่านและได้รับอนุมัติชัดเจน

## Evidence

- Final manifest: `/private/tmp/restaurant-p5-artifacts/p5-completion-nondevice-04-20260801T140550Z/manifest.txt`
- Full logs อยู่ใน directory เดียวกัน ได้แก่ backend regression, owner/role permission,
  role preset, approval, Retail POS compatibility, frontend และ repository safety

## Safety contract

- ไม่แตะ live database, production secret, DNS/TLS หรือ production deployment
- ไม่สร้าง Platform Owner บนฐาน live
- ไม่มี commit หรือ push จาก scope นี้
- `production_activated=false` และ `phase6_started=false` ถูกบันทึกใน manifest
