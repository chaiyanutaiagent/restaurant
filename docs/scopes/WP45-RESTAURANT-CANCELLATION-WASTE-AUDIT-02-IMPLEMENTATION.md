# WP45 — Restaurant Cancellation Approval + Waste/Audit Implementation

วันที่: `2026-09-20`
สถานะ: **Implemented; passed Local/UAT Engineering Gate**
ขอบเขต: **Restaurant POS/KDS; Local/UAT only**

## 1. Cancellation policy

| Kitchen state | Cancellation | Approval | Waste |
| --- | --- | --- | --- |
| `pending` | อนุญาต | ไม่ต้องขอ | ไม่สร้าง |
| `cooking` | อนุญาต | Manager คนละคนกับผู้ขอ | ตัดเต็มตามสูตร |
| `done` | อนุญาต | Manager คนละคนกับผู้ขอ | ตัดเต็มตามสูตร |
| `served` | ปฏิเสธ | - | ต้องไป Comp/Refund ใน WP46 |

- ใช้ reason code แบบมีโครงสร้าง และ `other` ต้องมีหมายเหตุ
- ยกเลิกหลัง checkout ไม่ได้; Server ส่งไปใช้ Refund/Credit Note flow แทน
- order ที่มีหลายรายการใช้สถานะครัวที่มีผลกระทบสูงสุดเป็น policy

## 2. Server contract

- `POST /api/v1/restaurant/cancellations/preview`
- `POST /api/v1/restaurant/cancellations`
- `GET /api/v1/restaurant/cancellations`
- `POST /api/v1/restaurant/cancellations/{id}/reopen`
- `GET /api/v1/restaurant/kitchen-cancellation-events`
- `POST /api/v1/restaurant/kitchen-cancellation-events/{id}/acknowledge`
- Device KDS ใช้ endpoint คู่กันใต้ `/api/v1/device-workspaces/kitchen/cancellations`
- endpoint cancel เดิมที่ไม่มี structured contract ปิดด้วย HTTP `410`

ทุก mutation ใช้ idempotency key, canonical request hash, optimistic row version และ database row lock
เพื่อให้ retry ปลอดภัยและ concurrent action มีผู้ชนะเพียงหนึ่งราย

## 3. Approval and permission

- แยก permission `cancel`, `request`, `approve`, `reopen.request` และ `reopen`
- `cooking`/`done` และ reopen บังคับ maker-checker; ผู้ขออนุมัติตัวเองไม่ได้
- approval token เป็น one-time operation grant และผูก exact payload
- Company/Brand/Branch, station และ paired device ถูกตรวจจาก Server ทุกครั้ง

## 4. Waste and stock integrity

- Waste ใช้สูตรเมนูจริงและตัดจาก STORE-STOCK ของสาขา
- ถ้าไม่มีสูตร, ไม่มี mapping, ไม่มี stock location, ไม่พบ balance หรือยอดไม่พอ จะ fail closed ทั้ง transaction
- Cancellation, Waste stock movement, KDS event, approval usage และ audit commit ใน transaction เดียว
- Pending cancellation และ reopen ไม่สร้าง Waste
- Reopen สร้าง order/ticket ใหม่และคำนวณราคาปัจจุบันใหม่ โดยไม่ย้อน Waste เดิม

## 5. Audit and KDS

- `restaurant_cancellations` เก็บ receipt, before-state, policy snapshot, bill impact, requester/approver/device และเหตุผล
- `restaurant_cancellation_waste` ผูก Waste แต่ละบรรทัดกับ StockMovement
- `restaurant_cancellation_audits` เก็บ cancel, KDS ack และ reopen แบบ append-only
- cancellation receipt, Waste และ audit มี database trigger ป้องกัน UPDATE/DELETE
- KDS ได้ cancellation event แยกตาม Company/Brand/Branch/Station และต้องกดรับทราบ

## 6. Touch UI

- Session แสดงปุ่มยกเลิกรายการ/ออเดอร์, reason chips, kitchen stage, bill impact, Waste และ approval requirement
- แสดง loading, offline, error, blocker และ permission failure โดยไม่ทำ optimistic cancellation
- มีประวัติการยกเลิกและ Reopen ผ่าน Manager approval
- KDS แสดงแถบเตือนสีแดงขนาดใหญ่และปุ่มรับทราบที่เหมาะกับ desktop/tablet

## 7. Local verification

- migration isolated database: blank → `wp44hold0020` → `wp45cancel0021` → downgrade → upgrade ผ่าน
- WP45 API smoke ผ่าน:
  - pending no-approval/no-Waste
  - cooking/done approval + full Waste
  - served fail closed
  - missing recipe และ stock shortage fail closed
  - KDS event/ack/replay และ Brand scope
  - idempotency, duplicate payload และ concurrent cancellation one-winner
  - reopen approval/replay/new pricing โดยไม่ย้อน Waste
  - append-only cancellation/Waste/audit trigger
  - ไม่มี Sale, Payment, Tax document หรือ Refund side effect
- backend regression `422/422` ผ่าน, skipped 1
- TypeScript type-check และ production/PWA build ผ่าน (`4,233` modules)
- Python compile และ Git whitespace gate ผ่าน
- frontend ไม่มี lint script; ใช้ type-check + production build เป็น static gate

## 8. Rollback design

1. เก็บ UAT backup ของ 5 databases, Redis และ uploads พร้อม checksum
2. บันทึก previous immutable UAT release/images และ Production container identity
3. deploy migration แบบ additive แล้ว recreate เฉพาะ UAT backend/frontend
4. ทดสอบ application-first rollback ไป WP44 บน schema WP45 ก่อนสลับกลับ
5. schema downgrade กลับ `wp44hold0020` พิสูจน์แล้วใน isolated rehearsal
6. restore data เฉพาะเมื่อ reconciliation พบ data corruption และต้องมีคำสั่งอนุมัติแยกต่างหาก

## 9. Explicit limitations

- ไม่ทำ provider refund, return stock, Tax/Credit Note หรือ real tax document; อยู่ใน WP46
- ไม่เปิด Production flags, Takeaway/Central Kitchen transactions หรือเปลี่ยน Retail data source
- Physical UAT printer, cash, PromptPay, paired Counter/iPad และ network loss ยังอยู่ใน WP47
- Production deployment ต้องมี owner approval และ gate แยกต่างหาก
