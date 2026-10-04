# WP36 — Canonical Company Context

วันที่: `2026-09-19`
สถานะ: **Implemented locally — Production unchanged**

## Outcome

- เพิ่ม contract กลาง `GET /api/v1/company/context` สำหรับ Company > Brand > Branch > Station/Device
- ยืนยัน context จาก signed token ที่ backend และตรวจ Company/Brand/Branch ownership ทุกครั้ง
- คืน environment แบบ `production | uat`, timezone, currency และ effective tax profile
- กำหนดว่าการสลับบริบทต้องออก token ใหม่ และ client context ไม่ใช่ข้อมูลที่เชื่อถือได้
- เพิ่ม `GET /api/v1/company/access` เพื่อคืน effective permissions, scopes, module access และ default route
- default route เลือกตาม permission และ signed business type; ถ้าไม่มีสิทธิ์ให้ fail closed ที่ `/403`
- การสลับสาขาล้าง query cache เดิมทั้งหมดก่อนโหลดข้อมูลบริบทใหม่

ไม่มี migration และไม่มีการเปลี่ยน route/flag ใน UAT หรือ Production

## Acceptance evidence

- Contract/schema และ route ถูกตรวจด้วย backend import/contract tests
- Frontend type-check และ production build ต้องผ่านก่อนปิด WP
- ทดสอบกรณีผู้ใช้มี permission ข้ามหลายผลิตภัณฑ์แล้วใช้ signed business context เป็นตัวตัดสิน route
