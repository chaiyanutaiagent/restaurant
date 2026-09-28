# WP84 — Production Alignment, Master-Data Mapping and Stripe Test Mode

วันที่: 2026-09-28

สถานะ: **IMPLEMENTED LOCALLY — automated gate passed; UAT keys and Owner inputs pending; Production HOLD**

## เป้าหมาย

1. เตรียม Production ให้ใช้ Backend/Frontend จาก release commit เดียวกัน โดยไม่เปิด write ก่อน canary
2. ใช้ข้อมูล Restaurant/Retail ที่ผ่าน UAT เป็นแม่แบบ แต่ไม่ copy UUID หรือธุรกรรมที่ชนกับ Production
3. เพิ่ม Stripe PromptPay สำหรับ POS และค่าสมาชิก SaaS เฉพาะ Test Mode

## ขอบเขตที่ทำแล้ว

- เพิ่ม Stripe Test Mode client โดยใช้ Secret Key ฝั่ง Server เท่านั้น
- POS ใช้ allowlist แบบ exact Company + Branch; ค่า provider account/mode ถูก snapshot ต่อ payment session
- POS สร้าง SaleOrder สถานะ `pending_payment`, `paid_amount=0` และยังไม่ตัดสต๊อก/ลง Payment/เพิ่มยอดกะ/ออก accounting handoff
- POS สร้าง PromptPay PaymentIntent จาก SaleOrder ค้างชำระที่ Server ตรวจ Company, Branch และยอดแล้ว
- POS ต้องส่ง idempotency key และผูก PaymentIntent กับ SaleOrder เท่านั้น
- POS session และ SaleOrder อยู่ใน operational database เดียวกันตาม signed context (`legacy`, `restaurant`, `retail_pos`)
- Stripe webhook เลือก operational database จาก `target_database` metadata ที่ผ่านการตรวจลายเซ็น แล้วตรวจซ้ำกับ snapshot ใน payment session; ค่าอื่นถูกปฏิเสธ
- ปิดการจำลอง PromptPay สำเร็จอัตโนมัติหลัง 15 วินาที
- ห้าม endpoint ยืนยันด้วยมือปิด Stripe PromptPay session
- ปิดบิลจาก signed Stripe webhook เท่านั้น โดยตรวจ:
  - Test Mode (`livemode=false`)
  - webhook timestamp และ HMAC signature
  - connected account (เมื่อกำหนด)
  - Company, Branch, session reference, amount และ currency
  - event ซ้ำด้วย durable receipt (`provider account + Stripe event ID + payload digest`)
  - terminal-state regression และ exactly-once sale finalization
- แยก Stripe secret/webhook ของ POS ออกจาก SaaS อย่างชัดเจน
- SaaS owner หรือ Platform billing admin สร้าง PromptPay session สำหรับ invoice สถานะ `open`
- SaaS เก็บ collection attempt และ PaymentIntent ID ก่อนแสดง QR; attempt ที่หมดอายุจะสร้าง attempt ใหม่ด้วย idempotency key ใหม่
- SaaS webhook รับเฉพาะ PaymentIntent ที่มี collection attempt อยู่จริง และตรวจ account, Company, Subscription, Invoice, amount และ currency ก่อนทำ `invoice.paid` และ `subscription.activated`
- ขอบเขต SaaS คือ **internal SaaS invoice + Stripe PaymentIntent collection** ไม่ใช่ Stripe Billing, Stripe Invoice หรือ `send_invoice`
- Live charging ยังถูกปิดโดย config gate เดิม

## Endpoint Test Mode

| บริบท | Endpoint |
|---|---|
| สร้าง POS PromptPay | `POST /api/v1/payments/sessions/promptpay` |
| ตรวจ capability ต่อ Company/Branch | `GET /api/v1/payments/capabilities` |
| POS webhook | `POST /api/v1/payments/callback/stripe/promptpay` |
| เจ้าของ SaaS สร้าง QR invoice | `POST /api/v1/membership/billing/invoices/{invoice_id}/stripe-promptpay-session` |
| Platform admin สร้าง QR invoice | `POST /api/v1/platform/companies/{company_id}/billing/invoices/{invoice_id}/stripe-promptpay-session` |
| SaaS webhook | `POST /api/v1/platform/billing/webhooks/stripe` |

## UAT configuration gate

ค่าเริ่มต้นทั้งหมดเป็น `disabled` และห้ามใส่ secret ใน Git, Frontend, log, เอกสาร หรือแชต

```text
STRIPE_POS_MODE=test
STRIPE_POS_SECRET_KEY=<secret-store:sk_test_...>
STRIPE_POS_WEBHOOK_SECRET=<secret-store:whsec_...>
STRIPE_POS_ACCOUNT_ID=<acct_...>
STRIPE_POS_CONNECTED_ACCOUNT_ID=<optional; when used must equal STRIPE_POS_ACCOUNT_ID>
STRIPE_POS_COMPANY_ALLOWLIST=<Sketch Biz Company UUID>
STRIPE_POS_BRANCH_ALLOWLIST=<approved Restaurant/Retail Branch UUIDs>

SAAS_BILLING_PROVIDER=stripe_test
SAAS_BILLING_LIVE_CHARGING_ENABLED=false
SAAS_STRIPE_MODE=test
SAAS_STRIPE_SECRET_KEY=<separate secret-store:sk_test_...>
SAAS_STRIPE_WEBHOOK_SECRET=<separate secret-store:whsec_...>
SAAS_STRIPE_ACCOUNT_ID=<separate acct_...>
```

Config จะปฏิเสธ `sk_live_`, ปฏิเสธ Test Mode ใน Production และยังไม่อนุญาต Live charging

## Migration heads ที่เตรียมแล้ว

- Legacy/transaction boundary: `wp84stripe0027`
  - เพิ่ม provider account/mode snapshot ใน `payment_sessions`
  - เพิ่ม `payment_provider_events` สำหรับ durable webhook receipt
  - เพิ่ม `saas_collection_attempts` ให้รองรับช่วงที่ Identity/SaaS billing ยังชี้ Legacy
- Platform boundary: `p16platform0020`
  - เพิ่ม `saas_collection_attempts` สำหรับ PaymentIntent lifecycle และ retry/expiry
- Restaurant boundary: `wp84restaurant0008`
  - เพิ่ม provider snapshot และ durable Stripe event receipt ในฐาน Restaurant
- Retail boundary: `wp84retail0008`
  - เพิ่ม `payment_sessions` และ durable Stripe event receipt ในฐาน Retail

ยังไม่ได้รัน migration เหล่านี้บน UAT หรือ Production

## ข้อมูล UAT ที่ใช้ต่อได้

| ระบบ | Brand/Branch | สถานะ |
|---|---|---|
| Restaurant | ครัวป่าปลาเขื่อน / `KPP-01` | ใช้ทดสอบต่อได้ |
| Restaurant | The Loft Kitchen / `TLK-01` | ใช้ทดสอบต่อได้ |
| Retail | The Loft Mini Mart / `TLM-01` | ใช้ทดสอบต่อได้ |
| Takeaway | Chambo / `BKK-01` | ใช้เฉพาะ gate ที่อนุมัติแล้ว |

## Production master-data hold

- Production มี Company UUID เดียวกับ UAT แต่ข้อมูลเดิมเป็น `Test Company` และเลขผู้เสียภาษีไม่ใช่ข้อมูลจริง
- Chambo มี identity เดิมบางส่วนอยู่แล้ว
- Branch UUID บางรายการมีความหมายต่างกันระหว่าง UAT กับ Production
- ห้ามเรียก `prepare_sketch_biz_uat.py` ใน Production เพราะมี UAT-only guard
- ห้าม copy UAT order, transfer, payment, shift, session, test user หรือ password
- Production ต้องเลือกอย่างใดอย่างหนึ่งต่อ record:
  1. แปลง record เดิมด้วย reviewed migration และ audit trail หรือ
  2. สร้าง Production UUID ใหม่และเก็บ mapping ชัดเจน
- ใช้ natural key `company registration ID + brand slug + branch code` ป้องกันข้อมูลซ้ำ
- Mapping manifest: `WP84-SKETCH-BIZ-PRODUCTION-MAPPING.json`

## Production release gate

Production ยังเป็น **HOLD** จนกว่าจะผ่านครบ:

1. ระบุ immutable Backend/Frontend image จาก commit เดียวกัน
2. สำรองฐานข้อมูลทั้งห้า, Redis, uploads และ runtime configuration พร้อม checksum
3. restore และ migration rehearsal บน clone
4. migration ทุกฐานตรง approved head
5. เปิดด้วย `TAKEAWAY_TRANSACTION_WRITE_MODE=hold`
6. Stripe POS/SaaS/Refund/Distribution/Kitchen live flags ปิดทั้งหมด
7. read-only smoke และ canary allowlist ผ่าน
8. Physical UAT เครื่องพิมพ์ ลิ้นชัก เครื่องสแกน iPad และ network recovery ผ่าน
9. Owner อนุมัติ Production data mapping และ canary reference

## Automated evidence

- Stripe/POS/SaaS focused tests: `15/15` ผ่าน
- Backend regression: `597/597` ผ่าน (`1` skipped ตาม baseline)
- Frontend TypeScript type-check: ผ่าน
- Frontend production build: ผ่าน (มี baseline bundle-size warning)
- SaaS static boundary check: ผ่าน
- Alembic heads: Legacy `wp84stripe0027`, Platform `p16platform0020`, Restaurant `wp84restaurant0008`, Retail `wp84retail0008`
- Migration rehearsal: Legacy full chain บนฐานชั่วคราวผ่าน; Platform `p15platform0019 → p16platform0020` ผ่าน; Restaurant `p6restaurant0007 ↔ wp84restaurant0008` และ Retail `p13retail0007 ↔ wp84retail0008` ผ่านทั้ง upgrade/downgrade/re-upgrade บน clone local; ลบฐาน rehearsal แล้ว
- Docker Backend image build: ผ่าน
- Production database, container, flag และ secret: **ไม่เปลี่ยนแปลง**

## Owner inputs ที่ยังต้องมี

- นิติบุคคลเจ้าของ Stripe account ฝั่ง POS และ SaaS
- Test Secret Key และ Webhook Signing Secret ผ่าน secret manager
- direct account หรือ Stripe Connect ต่อบริษัท
- บัญชี settlement
- ราคาแพ็กเกจ, VAT, due date, grace period, suspend/cancel/refund/proration
- mapping Company/Brand/Branch และอีเมลผู้รับ invoice
- ข้อกำหนดใบเสร็จ/ใบกำกับภาษีไทย

## Rollback

1. ตั้ง `STRIPE_POS_MODE=disabled` และ `SAAS_STRIPE_MODE=disabled`
2. ตั้ง `SAAS_BILLING_PROVIDER=unconfigured`
3. คง `SAAS_BILLING_LIVE_CHARGING_ENABLED=false`
4. ถอน webhook Test Mode ที่ Stripe Dashboard
5. Stripe event ที่ผ่านแล้วคง audit/idempotency evidence; ห้ามลบเพื่อซ่อนประวัติ
