# WP32 — Central Kitchen and Distribution Staged Activation

วันที่: `2026-09-18`
สถานะ: **engineering_ready_dark_launch — opening stock and stock-owner sign-off pending**

## Automated evidence

| Gate | ผล |
| --- | --- |
| Kitchen/production/distribution focused tests | `22/22` ผ่าน |
| Central Kitchen browser | `1/1` ผ่าน |
| Distribution browser | `1/1` ผ่าน |
| Multi-brand raw material | canonical Company ingredient ใช้ร่วมกัน; output/cost/report แยก Brand |
| Stock authority | lot/kitchen ledger + existing Transfer/StockMovement; ไม่สร้าง stock source ซ้ำ |
| Replay/concurrency | idempotency, reversal และ competing reservation contract ผ่าน |
| Distribution lifecycle | demand → plan → dispatch → receive/reject/return/cancel พร้อม reconciliation |

Production ยังไม่มี `COMPANY_KITCHEN_WRITES_ENABLED=true` หรือ
`COMPANY_DISTRIBUTION_WRITES_ENABLED=true`; write path จึงปิดตาม safe default

## Staged activation gate

- [ ] stock owner อนุมัติ canonical ingredient/UOM/supplier alias mapping
- [ ] นับ opening lot, quantity, unit cost, expiry และ location โดยผู้รับผิดชอบสองคน
- [ ] เลือกวัตถุดิบและ Brand จำนวนน้อยสำหรับ wave แรก
- [ ] ทดลอง issue/produce/receive/transfer/reject/return บนอุปกรณ์จริง
- [ ] เปรียบเทียบ physical count กับ ledger และยืนยัน tolerance
- [ ] backup, rollback owner และ monitoring window พร้อมก่อนเปิด write flags ทีละส่วน

## Decision

เปิดดูข้อมูลและเตรียม mapping ได้ แต่ยังห้ามเปิด write flags ใน Production จน opening-lot และ stock-owner gate ผ่าน
