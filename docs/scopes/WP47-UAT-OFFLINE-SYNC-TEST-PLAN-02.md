# WP47 — UAT Offline/Sync Test Plan and Rollback Checklist

วันที่: `2026-09-20`
สถานะ: **Planned — execution deferred until feature implementation is approved**

## A. Environment preflight

- [ ] ยืนยัน `POS_OFFLINE_MODE_ENABLED=false` ก่อนเริ่มและหลังจบ design review
- [ ] ใช้ UAT Company/Branch/Device/Shift และข้อมูลสังเคราะห์เท่านั้น
- [ ] เก็บ database/Redis/uploads backup พร้อม checksum และ release/image identity
- [ ] บันทึกจำนวน Sale, Payment, StockMovement, TaxDocument, loyalty transaction และ outbox ก่อนทดสอบ
- [ ] ปิด Production credentials/provider/tax endpoints และยืนยัน Production identity ไม่เปลี่ยน

## B. Network scenarios

ทดสอบทั้ง Desktop และ iPad โดยตัดเน็ตจริง/disable Wi-Fi และจำลอง latency/packet loss:

1. offline ก่อน login/pair/open shift — ต้อง fail closed
2. offline หลังเปิดกะ ขณะเมนู cache ยังสด — สร้าง local hold ได้
3. offline ขณะ cache stale/expired — ดูได้แต่ต้องเตือน; ห้ามรับชำระ
4. network หลุดก่อนส่ง request — มีหนึ่ง local operation
5. network หลุดระหว่างส่ง — สถานะ `unknown`, inquiry ก่อน retry
6. Server commit แล้ว ack หาย — reconnect ต้อง link ผลเดิม
7. หลุด/ต่อสลับเร็ว 20 รอบ — queue/order/payment ไม่ซ้ำ
8. browser refresh/force quit/restart/device reboot — queue ยังอยู่และ sequence เดิม
9. token หมดอายุ/device revoke/shift close ระหว่าง offline — reconnect ถูก reject แบบมีเหตุผล
10. ปิด Kill Switch ระหว่าง sync — หยุดรายการใหม่แต่ inquiry/export ได้

## C. Data integrity and duplicate prevention

- [ ] replay operation เดิม 10 ครั้งได้ Sale/Payment/Stock/Outbox/Journal อย่างละชุด
- [ ] idempotency key เดิม payload ต่างถูก quarantine
- [ ] 100 local cash operations sync 2 batch และ lost-ack replay แล้ว row parity ตรง
- [ ] sequence ต่าง device ไม่ทำลาย Branch/Shift order และไม่ข้าม tenant
- [ ] price/tax/product/permission/shift conflict ไม่สร้าง side effect ใดจน review
- [ ] local hold conflict ไม่ auto-merge และไม่ last-write-wins
- [ ] receipt reprint ระบุ copy; ไม่ออก receipt/tax number ใหม่จาก client
- [ ] queue count, Server result และ reconciliation report ตรงกัน

## D. Payment/Refund/Tax fail-closed matrix

- [ ] offline cash intent เท่านั้นที่เข้า queue ได้เมื่อ policy ครบ
- [ ] QR/PromptPay/card/bank transfer provider action ถูก disable offline
- [ ] approval token/PIN ไม่ถูก persist ลง IndexedDB/log/export
- [ ] Refund, Void, post-kitchen Cancellation, Credit Note และ tax issue ถูก disable offline
- [ ] provider timeout/unknown ไม่เปลี่ยน Payment/Sale/Tax/Credit Note เป็น success
- [ ] close shift ถูก block เมื่อมี pending/syncing/unknown/needs_review

## E. Security and accessibility

- [ ] local data ไม่เก็บ secret/card/PIN/approval token/full provider payload
- [ ] logout/revoke/Company switch ไม่แสดงข้อมูลข้าม scope
- [ ] tampered envelope/hash/schema ถูกปฏิเสธและ audit
- [ ] offline banner อ่านด้วย screen reader, focus order ถูกต้อง, touch target ≥44 px
- [ ] error ไม่อาศัยสีอย่างเดียวและมี action ที่ชัดเจน

## F. Acceptance evidence

เก็บ screenshot/video ของทุก state, browser/device/OS version, network timestamps, operation IDs,
server row counts, reconciliation export, database queries, logs ที่ลบ secret แล้ว และผู้ลงนาม Operator,
Finance/Tax, Security และ Product Owner

## G. Rollback checklist

1. เปิด Kill Switch และหยุดรับ local operation ใหม่
2. freeze outbox; export encrypted queue + checksum โดยไม่ลบ record
3. แยก `server_acknowledged/reconciled` ออกจาก `pending/unknown/needs_review`
4. inquiry รายการ unknown ด้วย client operation ID; ห้าม blind replay
5. rollback application ไป immutable UAT release ก่อนหน้า
6. migration เป็น additive; downgrade เฉพาะเมื่อพิสูจน์ว่าไม่มี queue อ้าง schema ใหม่
7. restore database เฉพาะเมื่อ reconciliation ยืนยัน data corruption ไม่ใช่เพียง app defect
8. ตรวจ Sale/Payment/Stock/Tax/Loyalty/Journal/Shift parity และ Production identity
9. เก็บ incident/evidence/audit และให้ผู้รับผิดชอบอนุมัติก่อนล้าง queue

## H. Go/No-Go gate

No-Go หากมี duplicate financial row, overcharge/over-refund, stock/loyalty mismatch, lost queue,
cross-tenant exposure, approval bypass, tax number duplicate, unknown state ที่ไม่มี inquiry หรือ rollback
ไม่สามารถกู้ queue ได้ครบ
