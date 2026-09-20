# WP44 — Server-backed Hold Draft Implementation

วันที่: `2026-09-20`
สถานะ: **Implemented and passed Local engineering gate**
ขอบเขต: **Restaurant/POS shared contract; Local/UAT only**

## 1. Data contract

- เพิ่ม `pos_hold_drafts` สำหรับ identity/context, safe cart intent, WP43 pricing snapshot, owner/assignee/device,
  expiry, claim, lifecycle และ optimistic version
- เพิ่ม `pos_hold_draft_audits` พร้อม append-only database trigger
- เพิ่ม Branch setting `pos_hold_draft_ttl_minutes` ค่าเริ่มต้น 120 และ database check 15–1,440
- Server content เก็บ product/variant/qty/discount intent และ display snapshot เท่าที่จำเป็น ไม่เก็บ payment state,
  credential, approval token, receipt หรือ tax number

## 2. API and lifecycle implementation

- `POST /api/v1/pos/drafts`
- `GET /api/v1/pos/drafts` และ `GET /api/v1/pos/drafts/{id}`
- `PATCH /api/v1/pos/drafts/{id}`
- `POST /claim`, `/resume`, `/release`, `/discard`, `/reopen`
- `GET /api/v1/pos/drafts/{id}/audit`

Create และ mutation ใช้ idempotency key + canonical request hash ส่วน claim ใช้ row lock และ claim TTL 120 วินาที
ร่วมกับ expected version ทำให้ concurrent Counter มีผู้ชนะหนึ่งราย

## 3. WP43 and Sale integration

- Create/claim/resume คำนวณราคาใหม่ผ่าน `PricingService`; client price ใช้ตรวจ discrepancy เท่านั้น
- Resume ตรวจ price/version/tax/discount/customer/product availability และ stock availability ใหม่
- Diff ถูกคืนเป็น machine-readable response; resume ที่มี diff ต้องส่ง `accept_revalidation=true`
- Checkout ต้องส่ง source draft id/version และเปลี่ยน `resumed → converted` ใน transaction เดียวกับ Sale
- Hold ไม่สร้างหรือ reserve Stock, Payment, Sale, KDS, Receipt หรือ Tax document
- Close shift คืน `hold_drafts_pending` เมื่อยังมี active/claimed draft ที่มอบหมายให้ผู้เปิดกะ; reassign พร้อมเหตุผลจึงส่งต่อได้

## 4. Scope and security

- ทุก query/mutation filter Company + Brand + Branch ที่ Server
- Shift validation ผูก User + Branch + Location + open status
- paired Counter token ถ้ามีต้องตรง Company/Branch; filter `Counter นี้` fail closed เมื่อไม่มี paired device
- Reassign ตรวจ user ที่ active และมี UserBranch ใน Brand/Branch เดียวกัน พร้อม permission/reason
- Operation replay ผูก actor user; key ของผู้ใช้อื่นหรือ payload อื่นคืน `duplicate_request`
- Permission presets เพิ่มสิทธิ์ Hold Draft ตาม Owner/Manager/Service/Cashier policy

## 5. Offline and Touch UI

- Online ใช้ Server list เป็น source of truth และ refresh ทุก 15 วินาทีขณะเปิด dialog
- Offline สร้าง Local-only safe draft; ไม่อ้างว่าเห็นทุก Counter
- Reconnect ซิงก์ shadow ด้วย key `offline-hold:{local-id}`; conflict เปลี่ยนเป็น `needs_review`
- Server save สำเร็จก่อนล้าง cart; error แล้ว cart ไม่เปลี่ยน
- Safe resume ไม่มี auto-merge และ server acknowledge สำเร็จก่อน restore cart
- History รองรับ expired/resumed/cancelled และสร้าง revision ใหม่ผ่าน reopen
- Loading, empty, error, offline, claimed/conflict และ permission denied มีสถานะแยกบน UI

## 6. Local verification

- migration isolated database: blank → `wp43price0019` → `wp44hold0020` → downgrade → upgrade ผ่าน
- WP44 unit + focused regression: `24/24` ผ่าน
- backend full regression: `412/412` ผ่าน, skipped 1
- WP44 API smoke ผ่าน:
  - server price และ payment-field stripping
  - no Sale/Payment/Stock side effect on hold
  - create/claim/resume idempotency
  - real concurrent claim one-winner
  - optimistic conflict, price revalidation/explicit acceptance
  - cross-staff Branch visibility และ Brand/Branch isolation
  - expiry/reopen, discard reason, reassign/close-shift
  - atomic sale conversion และ immutable audit
- TypeScript type-check ผ่าน
- production frontend build ผ่าน; มีเพียง existing chunk-size advisory
- Python compile และ `git diff --check` ผ่าน
- ไม่มี frontend `lint` script ใน package; จึงใช้ type-check + production build เป็น frontend static gate

## 7. Rollback design

1. เก็บ backup UAT databases, Redis และ uploads พร้อม checksum ก่อน deploy
2. บันทึก previous immutable images/release และ Production identity ก่อนเปลี่ยน UAT
3. หาก smoke ล้มเหลว สลับ UAT กลับ immutable release เดิมก่อน
4. Migration เป็น additive และ downgrade กลับ `wp43price0019` ผ่าน isolated rehearsal
5. Restore data เฉพาะเมื่อ reconciliation พบ data effect ผิดพลาด; ห้าม restore โดยอัตโนมัติ
6. ตรวจ Production identity หลัง deploy เพื่อยืนยันว่าไม่ถูกเปลี่ยน

## 8. Explicit limitations and blockers

- Local shadow เป็น offline recovery; การ sync conflict ต้องให้ผู้ใช้ตรวจ ไม่ให้ Local ชนะ Server อัตโนมัติ
- Branch list ใช้ polling 15 วินาที ยังไม่ใช่ websocket push
- Loyalty reserve → commit/release ยังไม่ atomic กับ Sale และยังเป็น Production blocker ต่อจาก WP43
- Physical iPad/Counter, printer, cash, PromptPay และ network-loss UAT ยังไม่เสร็จ
- Production, Retail cutover, Takeaway/Central Kitchen transaction flags และ real tax documents ไม่ถูกเปลี่ยน
