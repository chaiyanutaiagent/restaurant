# WP43 — Server-Authoritative Price and Price Override

วันที่จัดทำ: `2026-09-20`
สถานะ: **Closed for Local/UAT engineering — Production not approved**
Dependency: **WP42 UAT gate passed**
Target: **Restaurant/POS first; UAT only before a separate Production gate**

## 1. Outcome

ทำให้ราคาขาย ส่วนลด ภาษี และยอดรวมที่มีผลทางธุรกิจคำนวณและยืนยันโดย server เท่านั้น
client ใช้สำหรับนำเสนอและส่ง intent แต่ไม่สามารถกำหนดราคาสุดท้ายเองได้ พร้อมกระบวนการ Price Override
ที่มีสิทธิ์ เหตุผล approval threshold และ audit ครบถ้วน

## 2. Server-authoritative calculation

- Server โหลด price list ตาม Company/Brand/Branch/Channel/Customer/เวลาและ currency ที่มีผลจริง
- Server คำนวณ unit price, quantity, line/base discount, promotion, tax, rounding และ grand total ใหม่ทุกครั้ง
- ราคา/ภาษี/ส่วนลด/ยอดรวมที่ client ส่งมาต้องถูก ignore หรือเทียบเพื่อตรวจ stale/tamper เท่านั้น
- response ส่ง calculation breakdown และ snapshot ที่อธิบายได้กลับให้ client
- ห้ามเชื่อถือ hidden field, local storage, browser state หรือ offline cache เป็นราคา authority
- policy ต้อง fail closed เมื่อหา price/tax context ไม่ครบหรือ contract version ไม่รองรับ

## 3. Price snapshot and versioning

- ทุก order/quotation/sale draft บันทึก `price_list_id`, `price_version`, effective timestamp และ context snapshot
- บันทึก original price, applied price, discount/tax components, rounding rule และ calculation version ต่อ line
- submit/checkout ต้องตรวจ version อีกครั้ง; เมื่อ stale ให้ reject ด้วย machine-readable code และข้อมูลสำหรับ refresh
- ห้าม client silently replace cart price หลัง refresh โดยไม่แจ้งผู้ใช้

## 4. Price Override control

- Override ต้องมี dedicated permission แยกจากสิทธิ์ขายและสิทธิ์แก้ส่วนลดทั่วไป
- ต้องส่ง requested price/discount, reason code, note, requester identity และ context
- threshold ตามจำนวนเงิน/เปอร์เซ็นต์/กำไรขั้นต่ำกำหนดว่าทำได้ทันทีหรือต้อง approval
- ผู้อนุมัติต้องมี scope เดียวกันหรือสูงกว่าและห้าม self-approve เมื่อ policy กำหนด
- Server สร้าง immutable audit ที่เก็บ before/after, requester, approver, reason, policy/version และ timestamps
- การยกเลิก/คืนเงินภายหลังต้องอ้าง price snapshot และ override audit เดิม

## 5. Consistency and resilience

- ทุก calculate/submit/approve operation มี idempotency key และ replay-safe result
- ใช้ optimistic concurrency/version check ป้องกัน cart/order ถูกแก้พร้อมกัน
- stale price, duplicate request, expired approval และ context mismatch มี error code แยกกัน
- offline mode ดูราคา cache ได้เมื่อระบุ Stale ชัดเจน แต่ห้ามยืนยัน override/checkout จน server ตรวจใหม่
- telemetry ต้องจับ reject/override/approval/replay โดยไม่บันทึก token หรือข้อมูลการชำระเงินลับ

## 6. Product rollout boundary

- Implement และ validate Restaurant/POS ก่อน
- สร้าง shared calculation/override contract ให้ Retail และ Takeaway ใช้ต่อได้
- รอบ WP43 ห้ามเปลี่ยน Retail operational data source
- รอบ WP43 ห้ามเปิด Takeaway หรือ Central Kitchen real transactions
- integration ของผลิตภัณฑ์อื่นต้องผ่าน work package และ activation gate แยก

## 7. Proposed work breakdown

1. **WP43.1 Contract and threat model** — pricing inputs/outputs, authority boundary, error codes, abuse cases
2. **WP43.2 Pricing engine** — price list/context resolution, tax/discount/rounding calculation, snapshots
3. **WP43.3 Override policy** — permissions, reason catalog, thresholds, approval and self-approval rule
4. **WP43.4 Order integration** — Restaurant cart/calculate/submit/checkout server validation
5. **WP43.5 Idempotency and concurrency** — replay ledger, version conflict and stale-price refresh
6. **WP43.6 Audit and observability** — immutable before/after audit, metrics and safe logs
7. **WP43.7 UI integration** — discrepancy/stale/approval states without moving authority to client
8. **WP43.8 UAT and rollback** — security tests, tamper tests, reconciliation, immutable release and restore plan

## 8. Acceptance criteria

- การแก้ราคา/ส่วนลด/ภาษี/ยอดรวมใน request ไม่สามารถเปลี่ยนผลลัพธ์ server ได้
- calculation เดียวกันภายใต้ context/version เดียวกันให้ผล deterministic
- stale price ถูก reject และ refresh อย่างชัดเจนก่อน submit/checkout
- duplicate/replayed request ไม่สร้าง order, payment intent, journal หรือ stock effect ซ้ำ
- concurrent update ไม่ silently overwrite cart/order ล่าสุด
- override ที่ไม่มีสิทธิ์ เหตุผล หรือ approval ตาม threshold ถูกปฏิเสธ
- audit สามารถสืบจาก sale line ถึง requester/approver/policy/version ได้
- Restaurant/POS regression และ tax/discount/rounding matrix ผ่าน
- UAT tamper, permission, idempotency, concurrency, offline/stale และ rollback checks ผ่าน
- Production ยังคงปิดจนผ่าน approval gate แยก

## 9. UAT and rollback requirements

- ใช้ isolated fixtures ครอบคลุม VAT inclusive/exclusive, zero/exempt, promotion, rounding และ override thresholds
- ตรวจ browser/request tampering, cross-company/branch context, expired token และ privilege escalation
- ตรวจ reconciliation ระหว่าง cart, order, payment intent, tax snapshot และ accounting preview
- backup ก่อน deploy และระบุ previous immutable release/image
- schema change ต้อง additive และมี downgrade/compatibility plan; ห้าม destructive migration
- rollback application ก่อนและ restore data เฉพาะเมื่อ reconciliation ระบุว่าจำเป็น

## 10. Explicitly out of scope

- WP44 Server-backed Hold Draft
- WP45 Restaurant Cancellation Approval + Waste/Audit
- WP46 Provider Refund + Tax/Credit Note
- WP47 Physical UAT: printer, cash, PromptPay และ network loss
- Production deployment/activation
- Retail data-source migration
- Takeaway/Central Kitchen transaction activation
- การสร้างหรือยื่นเอกสารภาษีจริง

## 11. Start gate

Owner อนุมัติเริ่มงานแล้ว Implementation และผล Local Engineering Gate อยู่ที่
`docs/scopes/WP43-SERVER-AUTHORITATIVE-PRICE-OVERRIDE-02-IMPLEMENTATION.md` โดยยังคง UAT-only boundary
ผล UAT และคำตัดสินอยู่ที่ `docs/scopes/WP43-UAT-DEPLOYMENT-03.md` และ
`docs/scopes/WP43-PHASE-GATE-02.md` โดยยังคง Production block จนกว่าจะมี approval ใหม่
