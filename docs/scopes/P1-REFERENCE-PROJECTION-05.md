# Scope ID: P1-REFERENCE-PROJECTION-05

สถานะ: **Verified — runtime cutover pending**
Phase: **Phase 1 — Tenant, Brand และ Branch Foundation**
วันที่เริ่ม: 1 สิงหาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

`P1-DATA-CUTOVER-04` สร้าง Platform control-plane snapshot และ Restaurant operational
snapshot ที่แยก physical database แล้ว แต่ runtime ยังเขียน legacy database เพราะ Brand/Branch
administration บาง flow เขียน ownership และ operational setup ใน transaction เดียวกัน

ก่อนย้าย Platform writer ต้องมีวิธีส่ง Company, Brand, Branch, BrandBranch และ User references
ไปยัง Restaurant แบบไม่เปิด distributed transaction, retry ได้หลัง process crash และ apply ซ้ำได้โดย
ไม่สร้างผลข้างเคียงซ้ำ

## Business Type / Target Database

- Event source: `restaurant_platform_core_db`
- Reference projection target: `restaurant_ops_db`
- Runtime source/rollback database: legacy `restaurant_pos_db`
- Business type: `restaurant`
- Runtime routing mode: `legacy` ตลอด Scope นี้

## In Scope

- เพิ่ม transactional outbox ใน Platform migration history
- เพิ่ม idempotency ledger ใน Restaurant migration history
- กำหนด versioned event envelope สำหรับ `company`, `brand`, `branch`, `brand_branch` และ `user`
- เพิ่ม enqueue helper ที่ใช้ Platform transaction เดียวกับ ownership write
- เพิ่ม projector ที่ claim event แบบ crash-safe, อ่าน current Platform state และ upsert Restaurant
  reference ใน Restaurant transaction
- mark event processed หลัง Restaurant commit เพื่อให้ crash ระหว่างสองขั้น retry ได้อย่างปลอดภัย
- seed snapshot events แบบ deterministic และ rerun ได้
- ตรวจ field parity เฉพาะ Platform-authoritative reference columns
- rehearsal replay เพื่อพิสูจน์ว่า event เดิมไม่ apply ซ้ำ
- migration downgrade/upgrade และ regression test

## Reference Ownership Contract

- `companies`: Platform เป็นเจ้าของทุก column
- `branches`: Platform เป็นเจ้าของทุก column
- `brands`: Platform เป็นเจ้าของ identity/config columns; Restaurant คง
  `central_location_id` และ `central_ready_location_id`
- `brand_branches`: Platform เป็นเจ้าของ assignment columns; Restaurant คง `store_location_id`
- `users`: Platform เป็นเจ้าของ identity columns; Restaurant copy current row ชั่วคราวเพื่อรักษา
  operational foreign keys แต่ห้ามใช้ Restaurant projection เพื่อ authentication
- Outbox payload มีเฉพาะ event metadata/IDs และห้ามมี password hash, token หรือ credential

## Failure Semantics

1. Worker claim pending rows ด้วย `FOR UPDATE SKIP LOCKED` และปล่อย claim ที่หมดอายุให้ retry
2. Worker อ่าน current aggregate state จาก Platform; event ไม่เก็บ entity snapshot หรือ secret
3. Restaurant transaction insert `event_id` ลง ledger ก่อน upsert reference
4. หาก `event_id` มีแล้ว จะ skip upsert และถือว่า replay สำเร็จ
5. หลัง Restaurant commit จึง mark Platform outbox ว่า processed
6. หาก crash ก่อน mark processed event จะถูก replay และ Restaurant ledger ป้องกัน duplicate apply
7. Failure บันทึกเฉพาะ exception class, ปล่อย claim และตั้ง bounded exponential backoff

## Out of Scope

- เปลี่ยน API dependency จาก `get_db` ไป Platform/Restaurant
- เปลี่ยน system of record หรือ runtime writer จาก legacy
- dual-write, distributed SQL transaction หรือ cross-database foreign key
- background deployment/scheduler และ production monitoring
- roles, permissions, user assignments, refresh tokens และ audit projection
- hard-delete propagation; ownership records ใช้ soft-delete/deactivation
- Retail/Takeaway reference projection
- production deploy หรือ push

## Acceptance Criteria

- [x] Platform และ Restaurant heads เป็น `p1platform0003` / `p1restaurant0003`
- [x] snapshot seed rerun แล้วไม่สร้าง event ซ้ำ
- [x] event envelope ไม่มี credential หรือ entity snapshot
- [x] initial reference projection มี field parity ทุก supported aggregate
- [x] replay event เดิมไม่เพิ่ม Restaurant ledger row และ projection ยังตรงกัน
- [x] failure ปล่อย claim, เพิ่ม attempt และไม่บันทึก sensitive parameters
- [x] projector ไม่เปิด transaction ค้างข้ามสอง database
- [x] Brand/BrandBranch projection ไม่ทับ Restaurant operational location columns
- [x] migrations downgrade/upgrade แยกกันผ่าน
- [x] legacy database/runtime ไม่ถูกแก้ schema และยังเป็น system of record
- [x] backend regression และ Restaurant smoke ผ่าน

## Rollback

1. หยุด projector/scheduler (ถ้ามี)
2. downgrade Restaurant จาก `p1restaurant0003` เป็น `p1restaurant0002`
3. downgrade Platform จาก `p1platform0003` เป็น `p1platform0002`
4. หากต้องคืน reference data ให้ restore target dumps ที่สร้างก่อน rehearsal
5. legacy runtime ไม่ต้องเปลี่ยน route หรือ restore เพราะ Scope นี้ไม่ย้าย writer

## Execution Record

- Starting Platform head: `p1platform0002`
- Starting Restaurant head: `p1restaurant0002`
- Starting runtime system of record: legacy `restaurant_pos_db`
- Rehearsal backup: `/private/tmp/restaurant-projection05/p1-reference-projection-05-20260731T175323Z`
- Snapshot seed: 22 events — Company 1, Branch 4, Brand 3, BrandBranch 7, User 7
- Initial drain: 22 claimed, 22 applied, 0 replayed, 0 failed
- Field parity: supported Platform-authoritative columns ตรงกันทั้ง 22 references
- Seed rerun: 0 new events
- Crash replay: 1 claimed, 0 applied, 1 replayed; ledger count ไม่เพิ่ม
- Failure rehearsal: missing source เพิ่ม attempt เป็น 1, ปล่อย claim, คง pending และบันทึกเพียง
  `app.services.platform_reference_projection.ProjectionSourceMissing`; synthetic event ถูกลบหลังตรวจ
- Restaurant operational location hash ก่อน/หลัง projection ตรงกัน
- Independent migration rehearsal: downgrade เป็น `p1platform0002` / `p1restaurant0002`, upgrade
  กลับ `p1platform0003` / `p1restaurant0003` และ reseed/drain 22 events ผ่าน
- Final outbox: 22 total, 22 processed, 0 pending; Restaurant ledger: 22
- Final backup: `/private/tmp/restaurant-projection05-final/restaurant-boundaries-local-20260731T175505Z`
- Final Platform dump SHA-256: `aaed431d250423990b334361e7384609dc880a3133e67c7477e390cf6834eb87`
- Final Restaurant dump SHA-256: `6def6f1b4f2d5f13c74a271ea60a4b672d7bcf619aea3fde3840e2b0b51a756c`
- Final restore drill: restore เข้า temporary Platform/Restaurant databases, ตรวจ boundary metadata ผ่าน
  และลบ drill databases สำเร็จ
- Final legacy head: `6b7c8d9e0f12`; legacy ยังเป็น runtime system of record
- Final readiness: legacy, Platform, Restaurant, Redis และ uploads เป็น `ok`
- Backend regression: 105 tests ผ่าน
- Restaurant functional smoke: ผ่าน
- Restaurant permission smoke: ผ่าน
- Commit: บันทึกใน Git history ของ Scope ID นี้
