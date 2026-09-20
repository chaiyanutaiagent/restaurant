# WP46 — Provider Refund + Tax/Credit Note Scope

วันที่: `2026-09-20`
สถานะ: **Implemented locally; UAT deployment pending — Local/UAT only**

## Outcome

เปลี่ยน Refund เดิมที่สร้าง Payment ติดลบและคืนสต๊อกทันที ให้เป็น Server-authoritative workflow ที่อ้าง
Sale/Payment/Receipt/Tax snapshot เดิม คุมยอดคงเหลือคืนได้ รองรับ split tender และไม่ถือ approval หรือ
ledger ติดลบว่าเป็นหลักฐาน provider success

## Work packages

1. immutable refund quote + remaining refundable reservation
2. maker-checker approval ที่ bind quote/hash/version/reason
3. cash confirmation และ deterministic sandbox provider state machine
4. append-only attempt/event/audit พร้อม inquiry/retry/reconciliation
5. finalize ledger/stock/loyalty แบบ exactly-once หลังทุก payment leg ยืนยัน
6. synthetic non-fiscal UAT Credit Note หลัง refund success เท่านั้น
7. close-shift/reporting แยก Sale, Cash refund, Provider refund, Void และ pending/unknown
8. touch UI + Desktop/iPad states และ automated/physical UAT evidence

## Hard boundaries

- real provider, live refund, real eTax และ Production flags ถูกปิด
- Void ก่อน settlement แยกจาก Refund หลัง capture/settlement
- unknown/failed ไม่สร้าง negative Payment, Stock return, loyalty reversal หรือ Credit Note
- stock disposition ต้อง explicit; `none` เป็น default และ Waste อยู่คนละ workflow
- Exchange orchestration, Retail cutover และ Takeaway/Central Kitchen Production writes ไม่อยู่ใน scope

## Phase gate

UAT ผ่านได้เมื่อ migration rehearsal, duplicate/out-of-order/lost-ack/concurrency/scope/approval/tax
idempotency tests, full regression, API smoke, Desktop/iPad visual UAT, backup/checksum และ rollback drillครบ
แต่ Production ยังต้องมี provider contract/credential/security review, accountant sign-off และ physical payment UAT
