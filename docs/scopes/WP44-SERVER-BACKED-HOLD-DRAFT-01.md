# WP44 — Server-backed Hold Draft

วันที่จัดทำ: `2026-09-20`
สถานะ: **Implemented for Local/UAT engineering — Production not approved**
Dependency: **WP43 Phase Gate closed**
Target: **Restaurant/POS shared contract; UAT only**

## 1. Outcome

ย้าย `บิลที่พักไว้` จาก Browser-only IndexedDB ไปเป็น Server source of truth เมื่อออนไลน์ เพื่อให้พนักงานที่มีสิทธิ์
ใน Brand/Branch เดียวกันเห็นและเรียกบิลต่อจาก Counter อื่นได้ โดย Draft ยังไม่ใช่ Sale, Payment, Stock movement,
Dining Order, KDS ticket, Receipt หรือเอกสารภาษี

เมื่อ Offline ระบบเก็บ Local-only shadow ในเครื่องเดิม พร้อมป้ายสถานะและซิงก์ด้วย idempotency key เดิมเมื่อกลับมาออนไลน์

## 2. Authority and scope

- Server ตรวจ Company, Brand, Branch, Location, Shift, User และ Counter device จาก authenticated context
- Client ส่ง cart intent และ display snapshot แต่ราคา/ภาษี/ยอดรวมถูกคำนวณใหม่ด้วย WP43
- Server draft ไม่รับหรือเก็บเงินรับ เงินทอน payment reference, provider credential, approval token หรือเลขเอกสารภาษี
- Branch เป็นขอบเขตรายการร่วม ส่วน Brand เป็น context บังคับ; ข้าม Company/Brand/Branch คืน `404`
- `Counter นี้` ใช้ได้เมื่อมี paired device ที่ตรง Company/Branch เท่านั้น

## 3. Lifecycle

```text
active
  → claimed     atomic claim อายุ 120 วินาที
  → active      release หรือ claim หมดอายุ
  → resumed     restore/acknowledge สำเร็จครั้งเดียว
  → converted   checkout สร้าง Sale สำเร็จใน transaction เดียวกัน

active/claimed → expired
active/claimed → cancelled พร้อมเหตุผล
resumed/expired/cancelled → active revision ใหม่ผ่าน reopen
```

- Draft มี optimistic `version`; ทุก mutation ที่สำคัญต้องส่ง `expected_version`
- Create/claim/resume/release/update/discard ใช้ idempotency key และ request hash
- Reopen สร้าง record ใหม่พร้อม `parent_draft_id`; ไม่แก้ประวัติเดิมกลับเป็น active
- TTL เริ่มต้น 120 นาที ปรับได้ระดับ Branch ระหว่าง 15–1,440 นาที
- ก่อนปิดกะต้อง Resume, Reassign หรือ Discard Draft ที่ยังมอบหมายให้ผู้เปิดกะนั้น

## 4. Revalidation

ตอน claim และ resume Server ตรวจใหม่:

- Product/Variant ยังเปิดขายและอยู่ใน Brand context
- Price list, promotion, VAT, discount และ price version ตาม WP43
- Customer ยังอยู่ใน Company context
- Stock availability ของสินค้าที่ติดตามสต๊อก โดยไม่สร้าง reservation
- Shift/User/Location ยังเปิดและตรงกับ authenticated Branch

Price หรือ availability ที่เปลี่ยนถูกส่งเป็น diff และต้องยอมรับโดยชัดแจ้ง ห้ามปรับเงียบ Checkout ยังคำนวณและตรวจ
stock ซ้ำอีกครั้งก่อนสร้างผลทางธุรกิจ

## 5. Permissions and audit

- `pos.draft.view`
- `pos.draft.create`
- `pos.draft.update`
- `pos.draft.resume`
- `pos.draft.discard`
- `pos.draft.reassign`

Audit เก็บ Draft/version/status ก่อน–หลัง, actor, Branch, Shift, Device, action, reason, accepted diff และ idempotency
metadata โดยตาราง audit เป็น append-only ที่ Database ปฏิเสธ UPDATE/DELETE

## 6. Touch UI

- Search ด้วย draft number, label หรือลูกค้า
- Filter: ใช้งานได้, ของฉัน, Counter นี้, ประวัติ
- Badge แยก `Server-backed · ทุก Counter`, `ในเครื่อง · รอซิงก์`, `ต้องตรวจสอบ` และ `กำลังเปิดอีกเครื่อง`
- ปุ่มหลักอย่างน้อย 64px; filter/card action อย่างน้อย 56px
- บันทึก Server สำเร็จก่อนล้างตะกร้า; error แล้วตะกร้าต้องอยู่ครบ
- ตะกร้าไม่ว่างให้เลือกพักตะกร้าปัจจุบันก่อน, กลับ หรือแทนที่แบบยืนยัน destructive
- Server resume สำเร็จก่อนแทนที่ cart state และทุก checkout ตรวจราคาอีกครั้ง

## 7. Acceptance criteria

- ทุก Counter ที่มีสิทธิ์ใน Brand/Branch เดียวกันเห็น Server draft ชุดเดียวกัน
- Draft ไม่สร้าง Sale, Payment, Stock, KDS, Receipt หรือ Tax document
- Client price/payment fields ไม่เป็น authority และข้อมูลชำระเงินไม่ถูกเก็บใน Draft
- Retry เดิมไม่สร้าง Draft/claim/resume ซ้ำ; key เดิมคนละ payload/user ถูก reject
- สองเครื่อง claim พร้อมกันมีผู้ชนะเพียงหนึ่งราย
- stale version, context mismatch, expiry และ permission failure fail closed
- Resume แสดง price/availability diff และต้องยอมรับก่อนดำเนินการ
- Draft ที่ checkout แล้วเปลี่ยนเป็น converted พร้อม Sale transaction เดียวกัน
- Expiry, reopen, discard, reassign และ close-shift policy มี audit
- Migration upgrade/downgrade/upgrade, backend regression, frontend build, API smoke และ UAT rollback ผ่าน

## 8. Product boundary

- Local และ UAT เท่านั้น; Production deployment/flags ยังไม่อนุมัติ
- ไม่เปลี่ยน Retail operational data source
- ไม่เปิด Takeaway/Central Kitchen real transactions
- ไม่สร้างหรือยื่นเอกสารภาษีจริง
- Physical iPad/Counter UAT และ loyalty reserve/commit/release ยังเป็น Production blockers
- ห้ามเริ่ม WP45 จน WP44 Phase Gate ปิดและมีคำสั่งใหม่

## 9. UX reconciliation

Implementation ใช้ข้อกำหนดจาก:

- `docs/ux-ui/design-system/08-TOUCH-POS-HOLD-AND-ORDER-CENTER.md`
- `docs/ux-ui/retail-pos/07-RETAIL-POS-HOLD-RESUME-BILL.md`

จุดที่คงเป็นงาน Product/Physical UAT คือ realtime push แทน polling, iPad/Counter จริง, loyalty reservation atomicity และ
ข้อความ diff แบบเลือกแก้ทีละรายการ; ทั้งหมดไม่ถูกอ้างว่า Production-ready ใน WP44
