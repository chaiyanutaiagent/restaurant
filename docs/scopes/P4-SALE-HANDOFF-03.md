# Scope ID: P4-SALE-HANDOFF-03

สถานะ: **Verified — idempotent sale handoff complete**

Phase: **Phase 4 — Restaurant ERP Core**

Business type: **restaurant**

Target database: **Restaurant operational database; legacy migration receives the same additive contract for rollback-safe runtime**

## Problem

Sale, Payment และ StockMovement ถูกบันทึกใน transaction เดียวกันแล้ว แต่ accounting journal ถูก post หลัง sale commit
และ error ถูก log แล้วปล่อยผ่าน ขณะที่ journal ไม่มี uniqueness ตาม source reference การ retry จึงมีโอกาสได้ทั้ง
“sale สำเร็จแต่ไม่มี accounting” และ “journal ซ้ำ” นอกจากนี้ยังไม่มี durable contract สำหรับ consolidated
accounting/reporting consumer หลังแยก operational database

## In Scope

- เพิ่ม Restaurant operational outbox event แบบ versioned และ idempotent
- emit `restaurant.sale.completed.v1` ใน transaction เดียวกับ Sale/Payment/StockMovement
- ใช้ deterministic idempotency key ต่อ sale และ unique constraint ระดับ database
- ทำ accounting journal idempotent ด้วย source reference + entry type
- retry `client_order_id` เดิมต้อง repair handoff ที่ขาดโดยไม่สร้าง Sale/Payment/StockMovement/Journal/Event ซ้ำ
- เก็บ immutable `company_id`, `brand_id`, `branch_id`, aggregate id และ payload ที่ไม่บรรจุ credential/PII เกินจำเป็น
- เพิ่ม tests สำหรับ first write, duplicate retry, missing-handoff repair และ journal uniqueness

## Out of Scope

- เขียน Retail หรือ Takeaway database
- distributed transaction หรือ SQL join ข้าม database
- external accounting vendor adapter และ network delivery worker
- e-tax, payroll, advanced CRM และ Phase 5 production deployment

## Database / Ownership

- `operational_outbox_events` อยู่ Restaurant database และ legacy compatibility database เท่านั้น
- `journal_entries` ใน legacy compatibility runtime ได้ unique source contract; consumer ภายนอกใช้ outbox event
- ไม่มี foreign key จาก outbox ไป Platform/Retail/Takeaway; aggregate ids เป็น immutable references
- migrations เป็น additive และต้องผ่าน upgrade/downgrade/upgrade ทั้ง legacy และ Restaurant history

## Acceptance

- [x] sale transaction เดียวสร้าง Sale, Payment, StockMovement และ outbox event ครบหรือ rollback ทั้งหมด
- [x] `client_order_id` ซ้ำคืน sale เดิมและมี event เดียว
- [x] accounting retry คืน journal เดิมและมี journal เดียวต่อ SaleOrder
- [x] accounting failure ไม่ทำให้ durable handoff หาย
- [x] event payload เป็น version 1 และยอดรวม/ขอบเขตตรงกับ sale source
- [x] migration rehearsal และ duplicate concurrency regression ผ่าน

## Execution Record

- Sale handoff smoke จำลอง accounting failure หลัง sale commit แล้ว retry `client_order_id` เดิม
- ผลสุดท้ายมี Sale, Payment, StockMovement, outbox event และ Journal อย่างละหนึ่งชุด
- Legacy และ Restaurant migrations ผ่าน upgrade → downgrade → re-upgrade
- Outbox boundary test ยืนยันว่าไม่มี SQL foreign key ข้าม domain/database
- หลักฐานรวมอยู่ใน `P4-PHASE-GATE-06`

## Rollback

- ปิด consumer ได้โดยไม่กระทบการขาย; pending event ยังคงตรวจสอบได้
- downgrade ลบเฉพาะ additive outbox table/index และ journal source uniqueness
- ไม่ลบหรือแก้ Sale/Payment/StockMovement เดิม
- production cutover และ live database ไม่เปลี่ยนใน Scope นี้
