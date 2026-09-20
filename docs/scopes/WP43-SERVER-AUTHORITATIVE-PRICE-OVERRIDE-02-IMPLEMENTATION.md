# WP43 — Server-Authoritative Price and Price Override Implementation

วันที่: `2026-09-20`
สถานะ: **Implemented locally — pending UAT deployment gate**
ขอบเขต: **Restaurant/POS only; UAT only**

## 1. Authority contract

- Client ส่งเฉพาะเจตนา ได้แก่สินค้า/ตัวเลือก/จำนวน/ส่วนลด/Price Override และค่าราคาที่เห็นเพื่อใช้ตรวจ discrepancy
- Server โหลด Company, Brand, Branch, Channel, Customer, currency, effective date/time, price list, product tax และ branch policy ใหม่ทุกครั้ง
- Server คำนวณ unit price, promotion, line discount, order discount, VAT, rounding และยอดรวมสุดท้าย
- ราคาหรือ VAT ที่ client ส่งมาไม่ถูกใช้เป็น authority; เมื่อไม่ตรง server จะคืน `stale_price` และให้คำนวณใหม่
- Quote มีอายุ 300 วินาที ผูกกับ user/context/cart version และถูก consume ได้ครั้งเดียว
- Calculation ใช้ version `wp43.1` และ rounding rule `THB_HALF_UP_0.01`

## 2. Resolution and calculation order

1. ตรวจ Company/Branch/Brand/Customer scope และ currency
2. เลือก price list ที่ active และมีผลตาม Branch, Brand, Channel, Customer และเวลา โดยใช้ priority/version
3. เลือกราคาของ variant หรือ product ตามจำนวนขั้นต่ำ; THB fallback เป็น catalog price ได้ แต่ currency อื่นต้องมี price list
4. ตรวจ expected price/version เพื่อจับ stale หรือ request tampering
5. ใช้ Price Override เมื่อมี permission, reason และ policy ผ่าน
6. ใช้ line discount แล้วปันส่วน order discount ลงแต่ละ line
7. คำนวณ VAT แบบ included, excluded, zero หรือ exempt
8. ปัดเศษและสร้าง calculation hash, price snapshot และ line price version
9. ก่อน checkout คำนวณใหม่ภายใต้ lock และเทียบ quote/context/version อีกครั้ง
10. บันทึก order/payment/stock/accounting handoff และ consume quote ใน transaction เดียวกัน

## 3. Error contract

| Code | ความหมาย |
| --- | --- |
| `stale_price` | ราคา ภาษี หรือ quote หมดอายุ/เปลี่ยนแล้ว ต้อง refresh |
| `duplicate_request` | idempotency key ถูกใช้ต่าง payload หรือ quote ถูก consume แล้ว |
| `version_conflict` | cart version ไม่ตรงกับ quote |
| `context_mismatch` | Company/Brand/Branch/Channel/Customer/currency/user ไม่ตรง |
| `tax_context_invalid` | tax type/rate ไม่อยู่ใน contract ที่รองรับ |
| `approval_required` | Price Override เกิน threshold และยังไม่มี approval |
| `expired_approval` | approval token หมดอายุ ถูกใช้แล้ว หรือใช้ผิด context |
| `price_override_not_allowed` | override เกินเพดานหรือต่ำกว่า margin policy |

ทุกกรณี fail closed: ไม่สร้าง sale, payment, stock movement หรือ accounting handoff บางส่วน

## 4. Price Override policy and audit

- สิทธิ์แยกเป็น `pos.price.override` และ `pos.price.override.request`
- Branch กำหนด auto limit เป็นเปอร์เซ็นต์/จำนวนเงิน, max deviation, minimum margin และ self-approval ได้
- Request ต้องมี requested price, reason code และ note
- Approval ผูก Company/Branch/user/action และใช้ได้ครั้งเดียว
- เมื่อ policy ห้าม self-approval ผู้ขอกับผู้อนุมัติต้องเป็นคนละคน
- ทุก override บันทึก before/after, requester, approver, approval grant, reason, policy และ price snapshot
- Database trigger ปฏิเสธ UPDATE/DELETE ที่ `price_override_audits` เพื่อให้ audit append-only

## 5. Idempotency, concurrency and offline behavior

- Calculate และ checkout มี request hash และ idempotency key
- replay payload เดิมคืนผลเดิม; replay คนละ payload ถูก reject
- product/price rows ถูกอ่านใหม่และ lock ตอน checkout
- order uniqueness ป้องกัน payment, stock และ handoff ซ้ำ
- POS และ Restaurant quick-service แสดงราคา cached ได้เมื่อ offline แต่ระบุ `Stale` และปิดการรับชำระ
- offline checkout ใหม่ถูก server ปฏิเสธ; outbox เก่าจะถูกส่งไป `needs_review` ไม่ auto-post เป็น sale

## 6. Loyalty dependency — explicit Production blocker

ส่วนลดจาก line, order, loyalty และ exchange ถูกนำมารวมใน order discount ก่อนเข้า server pricing
จึงถูกนับใน threshold/ยอดรวมเดียวกันแล้ว แต่ flow เดิมของ `RedeemPointsDialog` ยังตัดแต้มก่อน sale commit
และยังไม่ได้เป็น transaction เดียวกับ order

มาตรการใน WP43:

- เมื่อ checkout ล้มเหลว UI แจ้งชัดว่าแต้มอาจต้องตรวจสอบ/คืน
- Server ไม่เชื่อยอดส่วนลดจาก client และไม่สร้าง sale effects เมื่อ pricing validation ล้มเหลว

งานที่ยังต้องทำก่อน Production:

- เปลี่ยน loyalty เป็น reserve → commit เมื่อ sale สำเร็จ → release เมื่อ sale ล้มเหลว
- ผูก reservation กับ `client_order_id` และทำ idempotent reconciliation
- เพิ่ม recovery job/audit สำหรับ reservation ที่หมดอายุ

ดังนั้น WP43 สามารถผ่าน Local/UAT engineering gate ได้ แต่ **ห้ามอนุมัติ Production** จน loyalty atomicity ผ่าน gate แยก

## 7. Data and compatibility

- migration เป็น additive; เพิ่ม price context/version/snapshot, quote ledger, override policy และ audit table
- legacy Product/PriceList และ Restaurant/POS routes ยังคงใช้งานได้ โดย server เป็นผู้คำนวณผลสุดท้าย
- downgrade กลับ revision `p16taxops0018` ผ่านการทดสอบบน isolated database
- Retail data source, Takeaway/Central Kitchen transaction flags และ real tax documents ไม่ถูกเปลี่ยน

## 8. Local verification

- backend full regression: `408/408` ผ่าน
- WP43 pricing unit matrix: ผ่าน authority/tamper, VAT, promotion, rounding, combined discount, override limits, stale/version
- WP43 API smoke: ผ่าน authority, approval/separation-of-duties, idempotency, context mismatch, immutable audit และ reconciliation
- migration blank → head → downgrade → head: ผ่าน
- TypeScript type-check: ผ่าน
- Python compile และ whitespace/diff gate: ผ่าน

## 9. Rollback plan

1. เก็บ backup UAT databases, Redis และ uploads พร้อม checksum ก่อน deploy
2. บันทึก previous immutable release/images และ Production identity ก่อนเปลี่ยน UAT
3. หาก application smoke ล้มเหลว ให้สลับ UAT compose กลับ previous immutable images ก่อน
4. migration เป็น additive จึงไม่ต้อง restore data โดยอัตโนมัติ; downgrade schema เฉพาะเมื่อ application rollback ต้องการ
5. restore data จาก backup เฉพาะเมื่อ reconciliation พิสูจน์ว่ามี data effect ผิดพลาด
6. ตรวจ Production identity หลัง deploy เพื่อยืนยันว่าไม่ถูกเปลี่ยน

## 10. Deliberate non-actions

- ไม่ deploy หรือเปิด Production flags
- ไม่เริ่ม WP44
- ไม่เปลี่ยน Retail operational data source
- ไม่เปิด Takeaway/Central Kitchen real transactions
- ไม่สร้างหรือยื่นเอกสารภาษีจริง
