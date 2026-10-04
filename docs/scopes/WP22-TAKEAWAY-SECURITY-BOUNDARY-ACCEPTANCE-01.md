# WP22 — Takeaway Security / Boundary Acceptance

วันที่: 2026-09-17

สถานะ: **automated acceptance completed — physical device abuse test อยู่ WP24**

## ขอบเขตที่ตรวจ

- ทุก private mutation route มี authenticated user dependency และ permission เฉพาะงาน
- สิทธิ์ `takeaway.import.apply` อยู่ใน Company Owner preset เท่านั้น
- Company/Brand/Branch มาจาก signed context; service เดิมยัง fail closed เมื่อข้าม business/branch
- Takeaway router/service ไม่ import Restaurant/Retail operational model หรือ database dependency
- ตารางที่เสี่ยง replay มี database unique constraint สำหรับ client/idempotency/execution key
- URL หลักฐาน top-up รับเฉพาะ HTTPS ที่ไม่มี credential หรือ internal path ใต้ `/uploads/evidence/`
- Android printer ตรวจ Bluetooth MAC, Base64 และจำกัด payload 1 MiB
- tracked runtime source ผ่าน credential pattern scan และไม่มี legacy Android identity
- Signed migration bundle ตรวจ forbidden secret/PII, path escape, hash และ trusted key

## หลักฐานอัตโนมัติ

- `backend/tests/test_takeaway_security_acceptance.py`
- `backend/tests/test_takeaway_service.py`
- `backend/tests/test_device_pairing.py`
- `backend/tests/test_counter_shift_security.py`
- `scripts/check-takeaway-security-boundary.sh`

## สิ่งที่ยังไม่อ้างว่าผ่าน

- permission deny/retry และ Bluetooth abuse บนอุปกรณ์ Android จริง
- penetration test จากภายนอก UAT/Production
- owner review ของ trusted import public key และ production secret store

รายการเหล่านี้ติดตามใน WP24–WP26; ไม่มีการลดการควบคุมเพื่อให้ผลทดสอบผ่าน
