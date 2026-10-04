# WP45 — Restaurant Cancellation Approval + Waste/Audit Scope

วันที่: `2026-09-20`
สถานะ: **In progress — Local/UAT only**
ขอบเขต: **Restaurant order cancellation before checkout**

## 1. Objective

เปลี่ยนการยกเลิกออเดอร์/รายการอาหารจากการแก้ status และต่อข้อความเหตุผล เป็น Server-authoritative
transaction ที่มี policy, approval, KDS cancellation acknowledgment, recipe waste/stock reference และ append-only audit
ครบใน transaction เดียว โดยไม่ hard delete ข้อมูลต้นทาง

## 2. Cancellation policy

| สถานะก่อนยกเลิก | Approval | Waste | ผลลัพธ์ |
| --- | --- | --- | --- |
| `pending` | ไม่ต้องใช้ Manager | ไม่สร้าง Waste | ยกเลิกรายการและส่ง cancellation event ไป KDS |
| `cooking` | Manager maker-checker | ตัด Waste เต็มตามสูตร | ยกเลิกและรอ KDS acknowledge |
| `done` | Manager maker-checker | ตัด Waste เต็มตามสูตร | ยกเลิกและรอ KDS acknowledge |
| `served` | ปฏิเสธแบบ fail closed | ไม่เปลี่ยน Stock | ต้องใช้ Comp/Refund ใน WP46 แทน |

การยกเลิกทั้งออเดอร์ใช้ policy สูงสุดของรายการที่ยัง active และปฏิเสธหากมีรายการ `served` แม้แต่หนึ่งรายการ

## 3. Permissions and maker-checker

- `fb.order.cancel` — ยกเลิกก่อนครัวเริ่มทำ
- `fb.order.cancel.request` — ขออนุมัติยกเลิกหลังครัวเริ่มทำ
- `fb.order.cancel.approve` — อนุมัติการยกเลิกหลังครัวเริ่มทำ
- `fb.order.cancel.reopen.request` — ขอเปิดรายการที่ยกเลิกกลับเป็นออเดอร์ใหม่
- `fb.order.cancel.reopen` — อนุมัติ reopen

Approval actions คือ `fb.order.cancel_after_kitchen` และ `fb.order.cancel.reopen`; ทั้งสอง action บังคับ token
จากผู้อนุมัติคนละคนกับ requester แม้ requester จะมีสิทธิ์ approve เอง

## 4. Server contracts

- Preview และ execute ใช้ target (`item`/`order`), reason code, note, expected order/item version และ idempotency key
- `other` ต้องมี note; reason code อื่นรับ note เพิ่มเติมได้
- Server คำนวณ stage, bill impact, waste impact, approval requirement และ policy snapshot เอง
- Company/Brand/Branch, paired device/station, session และ target ต้องอยู่ใน scope เดียวกัน
- stale version, duplicate key คนละ payload, permission mismatch, offline และ missing recipe/stock contract ต้อง fail closed
- Cancellation ก่อน checkout ห้ามสร้าง Sale return, Payment refund, provider refund, Tax document หรือ Credit Note

## 5. Persistence and audit

- cancellation receipt, waste lines และ audit event เป็น append-only ที่ระดับ database
- เก็บ requester/approver, reason, before state, branch/station/device, KDS ticket, timestamp,
  approval policy snapshot, stock movement references และ bill impact
- KDS cancellation event มีสถานะ `pending_ack`/`acknowledged`, optimistic version และ idempotent acknowledgment
- retry ต้องไม่สร้าง Waste, StockMovement, KDS event หรือ Audit ซ้ำ
- Reopen สร้างออเดอร์ใหม่ผ่าน server-authoritative pricing; ไม่แก้ cancellation เดิมและไม่ย้อน Waste ที่เกิดจริง

## 6. Waste/stock policy

- `cooking`/`done` ใช้ full recipe quantity ของรายการที่ยกเลิก
- ต้องมี BrandBranch, STORE-STOCK location, active recipe, ingredients, inventory role และ stock balance ครบ
- ใช้ movement type `waste` และ reference ไป cancellation โดยตรง
- ห้ามติดลบ; หาก contract หรือ stock ไม่พอ transaction ทั้งหมดต้อง rollback

## 7. Touch UI and accessibility

- Reason เป็นปุ่มขนาดใหญ่ พร้อมช่อง note เมื่อเลือก `other`
- Preview แสดงสถานะครัว, ผลกระทบบิล, Waste และความต้องการ Manager ก่อนยืนยัน
- Manager approval ใช้ component เดิมและ one-time token
- KDS แสดง cancellation card แยกจาก active ticket พร้อมปุ่มรับทราบขนาดใหญ่
- รองรับ desktop/iPad, keyboard, screen reader และ Loading/Empty/Error/Offline/Stale/Permission denied

## 8. Verification and release boundary

- migration blank/head, upgrade/downgrade/upgrade rehearsal
- policy, permission, maker-checker, idempotency, concurrency, waste/stock, KDS acknowledgment,
  reopen และ no-sale/refund/tax side-effect tests
- backend regression, frontend type-check/build, API smoke และ visual UAT desktop/tablet
- deploy เฉพาะ UAT พร้อม backup/checksum/rollback drill และตรวจ Production identity ไม่เปลี่ยน

## 9. Explicitly excluded

- WP46 provider refund, comp, Sale return, Payment refund, e-Tax และ Credit Note
- Production deploy/migration/restart/feature activation
- Retail data-source cutover
- Takeaway/Central Kitchen Production transaction writes
