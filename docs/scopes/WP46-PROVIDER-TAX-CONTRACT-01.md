# WP46 — Provider Refund and Tax Contract

วันที่: `2026-09-20`
สถานะ: **UAT contract — no live credentials**

## Refund authority

Server quote อ่าน original Sale, positive Payment, negative refund ledger, item refund balance, tax snapshot,
currency/rounding, active shift และ in-flight reservation ภายใต้ lock Client เลือกได้เฉพาะ item/qty,
reason และ stock disposition ที่ policy รองรับ

ทุก mutation มี idempotency key + canonical hash; quote มี expiry/order row version และถูก consume ได้ครั้งเดียว
over-refund หรือ concurrent winner ที่สองต้อง fail closed

## Payment leg rules

- `cash` ใช้ `cash_due → succeeded` หลัง operator ยืนยันการจ่ายเงินสด
- provider/captured payment ใช้ `requested → processing → succeeded|failed|unknown`
- failed retry ได้ด้วย attempt ใหม่; unknown ต้อง inquiry ก่อนและห้าม blind retry
- split tender finalize เมื่อทุก leg สำเร็จเท่านั้น; partial provider success เข้า `needs_reconciliation`
- negative Payment คือ ledger หลัง success ไม่ใช่หลักฐาน provider success
- Void ใช้ได้เฉพาะก่อน settlement; settled/unknown ต้องเข้า Refund/inquiry

## Sandbox adapter

รองรับ deterministic scenario: `succeeded`, `failed`, `processing_then_succeeded`,
`unknown_then_succeeded`, `unknown_persistent` ไม่มี network หรือเงินจริง Webhook ต้องมี event id,
sequence, HMAC และตรวจ duplicate/out-of-order; inquiry เป็น authority สำหรับ unknown

## Approval

approval bind Company/Branch/requester/order/quote/quote hash/order version/amount/reason/scenario,
ใช้ครั้งเดียวและห้าม requester approve ตัวเอง Direct permission ไม่ข้าม maker-checker
approval success แปลเพียง “อนุญาตให้ขอคืน” ไม่ใช่ provider success

## Stock and loyalty

- default disposition `none`; refund อาหาร/บริการไม่คืน stock
- `sellable` ใช้ได้เฉพาะ simple/variant/raw material และ original location; exactly-once
- quarantine/damaged ใช้ cancellation/waste/stock workflow แยก และ fail closed หาก contract ไม่ชัด
- earned points reversal ทำหลัง refund success แบบ idempotent; redemption ที่ไม่มี reservation/restore contract
  เป็น Production blocker และ flow เสี่ยงต้อง fail closed

## Tax/Credit Note

เมื่อ refund ทุก leg สำเร็จและ original issued tax document มีอยู่ จึงสร้าง Credit Note ที่อ้าง original
และ refund operation มี item/qty/subtotal/discount/VAT/rounding เท่ากับ server quote พร้อม unique operation link
UAT document ต้อง `synthetic=true`, watermark `UAT NON-FISCAL`, ไม่ submit ภายนอก และ retry/reconcile ได้
failed/unknown refund ห้ามสร้าง Credit Note; tax failure ห้ามอ้าง workflow ว่าปิดสมบูรณ์

## Reporting

รายงาน/ปิดกะแยก gross sale, cash refund, provider refund, void, pending/unknown และ Credit Note status
กะที่มี requested/processing/unknown/cash_due/needs_reconciliation/tax_pending ปิดไม่ได้
