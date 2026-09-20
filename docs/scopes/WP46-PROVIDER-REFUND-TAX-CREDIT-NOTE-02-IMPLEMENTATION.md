# WP46 — Provider Refund + Tax/Credit Note Implementation

วันที่: `2026-09-20`
สถานะ: **Implemented; Local/UAT Engineering Gate passed**
ขอบเขต: **Restaurant POS; Local/UAT sandbox only**

## 1. Server-authoritative refund

- Refund เริ่มจาก quote ที่ Server คำนวณจาก Sale item, VAT, discount และ Payment เดิม
- Client ส่งยอดคืนเองไม่ได้ และ execution ต้องตรงกับ quote hash, Sale version และยอดที่ Server ให้
- รองรับ partial item, split tender, THB rounding และ remaining refundable balance
- เมื่อ operation เริ่ม ระบบ reserve ด้วย Sale row version ทันที ป้องกัน quote คู่แข่งทำ over-refund ระหว่างสถานะ
  `cash_due`, `processing` หรือ `unknown`
- endpoint refund เดิมที่คืนทันทีถูกปิดด้วย HTTP `410`

## 2. Approval และ state machine

- ทุก refund บังคับ maker-checker; requester และ approver ต้องเป็นคนละคน
- approval grant ผูก exact quote/order/version/total/reason/disposition/provider scenario และ idempotency key
- state หลัก: `requested`, `processing`, `cash_due`, `failed`, `unknown`, `needs_reconciliation`,
  `succeeded`, `tax_pending`, `completed`
- เงินสดต้องยืนยันว่าจ่ายคืนจริง; provider sandbox รองรับ success, failed/retry, processing/inquiry,
  unknown/inquiry และ persistent unknown
- operation/action/webhook ใช้ idempotency, row lock, optimistic version และ duplicate/out-of-order guard

## 3. Financial, stock และ loyalty integrity

- สร้าง negative Payment ledger หลัง payment legs สำเร็จครบเท่านั้น และผูก original payment + refund operation
- failed/unknown ไม่เปลี่ยน Sale, Payment, Stock, Loyalty หรือ Tax document
- stock default เป็น `none`; `sellable` ต้องเลือกชัดเจนและอนุญาตเฉพาะสินค้าที่คืนเข้าสต๊อกได้
- earned loyalty ถูกย้อนตามสัดส่วน exactly-once; Sale ที่ใช้ redeemed points ถูก fail closed รอ atomic
  reserve/restore contract
- ปิดกะไม่ได้เมื่อมี refund pending/processing/cash due/unknown/reconciliation/tax pending
- Void ใช้ได้เฉพาะ payment ที่ยัง `authorized/pending`; payment ที่ settled/unknown ต้องเข้า Refund workflow

## 4. Provider และ webhook evidence

- UAT ใช้ deterministic sandbox adapter เท่านั้น; live provider ถูก runtime validator ปฏิเสธ
- provider attempt และ webhook event เป็น append-only
- webhook ตรวจ HMAC, provider event id, payload hash และ sequence
- duplicate เดิมคืนผลเดิม; event id เดิมแต่ payload ต่างถูกปฏิเสธ; out-of-order เก็บหลักฐานแต่ไม่ย้อนสถานะ

## 5. Tax/Credit Note

- เมื่อ refund สำเร็จและมี original issued tax document ระบบสร้าง synthetic Credit Note
- เอกสารติด watermark `UAT NON-FISCAL`, `submission_status=not_submitted` และไม่มีการยื่นจริง
- Credit Note ผูก original document และ refund operation แบบ unique; เอกสาร refund ถูก DB ป้องกัน UPDATE/DELETE
- ถ้า feature ปิดหรือสร้างเอกสารไม่สำเร็จ Refund อยู่ `tax_pending`; ไม่มีการเรียก provider ซ้ำ
- Production validator ปฏิเสธ synthetic Credit Note และ sandbox provider

## 6. Touch UI และ reconciliation

- Recent Sale เปิด Refund Workspace แทน legacy action
- เลือกรายการ/จำนวน, reason, stock disposition, ดู Server quote/VAT/payment allocation และขอ Manager approval
- แสดง cash/provider/tax states, inquiry/retry/tax retry และคำเตือน unknown แบบไม่สื่อว่าสำเร็จก่อน reconcile
- Offline ปิด Refund พร้อมเหตุผล; touch target หลักอย่างน้อย 44 px สำหรับ Desktop/iPad
- reconciliation แยก gross sale, cash refund, provider refund, void, pending/unknown และ Credit Note status

## 7. Local verification

- migration isolated database `wp45cancel0021 → wp46refund0022 → downgrade → upgrade`: ผ่าน
- WP46/WP47 contract tests `10/10`: ผ่าน
- backend regression `432/432`: ผ่าน, skipped `1`
- API smoke ผ่าน:
  - Server quote, exact payload approval และ execute/action replay
  - concurrent stale quote ถูกปฏิเสธหลัง partial refund reservation
  - cash due/confirm และ close-shift blocker
  - provider unknown ไม่มี financial side effect แล้ว inquiry สำเร็จ
  - signed webhook, duplicate replay และ out-of-order event
  - negative ledger exactly-once, stock disposition `none`, reconciliation cash/provider
  - synthetic non-fiscal Credit Note และ append-only audit
- TypeScript type-check, production/PWA build, Python compile และ Git whitespace gate: ผ่าน
- final UAT API smoke และ public routes: ผ่าน
- Desktop/iPad landscape `1024×768`, refund quote/VAT, maker-checker และ accessibility console: ผ่าน
- application-first rollback ไป WP45 แล้วกลับ WP46: ผ่าน, RTO `9 seconds`
- non-blocking backlog เดิม: frontend bundle มี large-chunk warning

## 8. Runtime boundaries

- `REFUND_PROVIDER_MODE=disabled` เป็น default; UAT ใช้ได้เฉพาะ `sandbox`
- `REFUND_UAT_NON_FISCAL_CREDIT_NOTE_ENABLED=false` เป็น default
- `POS_OFFLINE_MODE_ENABLED=false` ทุก environment ในรอบนี้
- ไม่มี Production deploy, real provider call, real tax filing, Retail source change หรือ Takeaway/Central Kitchen
  Production transaction

## 9. Rollback design

1. backup 5 databases, Redis และ uploads พร้อม checksum ก่อน deploy
2. pin previous UAT release/image และบันทึก Production identity
3. apply additive migration แล้ว recreate เฉพาะ UAT backend/frontend
4. application-first rollback ไป WP45 บน additive WP46 schema
5. schema downgrade ไป `wp45cancel0021` ใช้เฉพาะเมื่อพิสูจน์ว่าไม่มี WP46 data ที่ต้องเก็บ
6. restore data ใช้เฉพาะเมื่อ reconciliation ยืนยัน corruption และต้องได้รับอนุมัติแยกต่างหาก

## 10. Production blockers

- real provider credential/webhook/inquiry/SLA และ security review
- Accountant/Tax Owner อนุมัติเลขเอกสาร, partial Credit Note, XML/submission และงวดบัญชี
- atomic loyalty redeem reserve/restore
- Physical UAT เครื่องพิมพ์ เงินสด PromptPay, paired Counter/iPad และ network loss
- WP47 Offline/Sync implementation, encrypted local storage, outbox reconciliation และ rollback evidence
