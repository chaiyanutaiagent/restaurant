# Scope ID: P1-DATABASE-BOUNDARY-03

สถานะ: **Verified — boundary initialized; data cutover pending**
Phase: **Phase 1 — Tenant, Brand และ Branch Foundation**
วันที่เริ่ม: 1 สิงหาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

ระบบปัจจุบันใช้ `DATABASE_URL` และ Alembic history เดียวสำหรับ Control Plane, Restaurant และ legacy Retail operations แม้ canonical business context จะระบุ `target_database` แล้วก็ตาม ทำให้ยังพิสูจน์ไม่ได้ว่า connection, migration และ backup/restore ของ `platform_core` กับ `restaurant` แยกจากกันจริง

ฐานข้อมูลปัจจุบันมี 101 ตาราง และ 97 ตารางมี foreign key โดยหลาย transaction ใช้ identity/ownership และ operational model ผ่าน SQLAlchemy session เดียว การย้ายข้อมูลพร้อมสลับ runtime ในขั้นเดียวจึงเสี่ยงทำให้ข้อมูลเดิมเสียหรือเกิด distributed transaction ที่ขัดกับ architecture baseline

Scope นี้เป็น reversible boundary slice ก่อน data cutover: สร้าง physical databases และ operational tooling จริง แต่ยังไม่ประกาศว่าฐานข้อมูลใหม่เป็น system of record จนกว่า Scope cutover ถัดไปจะย้ายข้อมูลและสลับ router ผ่าน UAT

## Business Type / Target Database

- Control Plane target: `platform_core`
- Restaurant target: `restaurant`
- Legacy runtime database: คง `DATABASE_URL` เดิมระหว่าง Scope นี้
- Business type ที่เตรียม routing: `restaurant`

## In Scope

- เพิ่ม explicit `PLATFORM_DATABASE_URL` และ `RESTAURANT_DATABASE_URL` โดย fallback ไป `DATABASE_URL` เพื่อ backward compatibility
- เพิ่ม engine/session factory และ dependency แยกสำหรับ `platform_core` กับ `restaurant`
- เพิ่ม registry ที่ resolve session factory จาก server-owned target database เท่านั้น
- สร้าง PostgreSQL database แยกจริงบน local cluster
- เพิ่ม Alembic environment และ migration head แยกกันสำหรับ boundary metadata
- เพิ่ม local setup, backup และ restore-drill tooling ที่แยก dump ต่อ database
- เพิ่ม readiness check สำหรับ legacy, Platform และ Restaurant connections
- บันทึก table ownership/cross-database FK inventory สำหรับ Scope cutover ถัดไป
- เพิ่ม tests และเอกสาร environment/operations ที่เกี่ยวข้อง

## Out of Scope

- copy, move หรือ delete Company/Brand/Branch/User/Restaurant operational rows
- สลับ API router จาก legacy session ไปฐานข้อมูลใหม่
- เปลี่ยน system of record ของข้อมูลใด
- drop foreign key หรือตารางจาก legacy database
- Takeaway/Retail operational database implementation
- production database creation, deploy หรือ push
- Phase 2 role preset, approval หรือ device pairing

## Acceptance Criteria

- [x] local PostgreSQL มี database `platform_core` และ `restaurant` ที่ชื่อไม่ซ้ำกับ legacy database
- [x] แต่ละ database มี Alembic history/head ของตัวเองและ downgrade/upgrade ได้อิสระ
- [x] application readiness ตรวจ connection ทั้ง legacy, Platform และ Restaurant ได้
- [x] หากไม่กำหนด URL ใหม่ application ยังใช้ legacy URL ได้แบบ backward-compatible
- [x] server-side registry ปฏิเสธ target database ที่ไม่รองรับ
- [x] backup สร้าง dump ของ Platform และ Restaurant แยกไฟล์
- [x] restore drill กู้สอง dump เข้า database ทดสอบคนละลูกและตรวจ metadata ได้
- [x] ไม่มี operational row ถูกย้ายหรือลบจาก legacy database
- [x] backend regression, frontend type-check/build และ Restaurant smoke ผ่าน

## Rollback

1. revert source commit เพื่อคืน single-database configuration
2. downgrade boundary migrations แยกใน Platform และ Restaurant database
3. ฐานข้อมูล boundary เป็น additive และยังไม่ใช่ system of record จึงลบภายหลังได้เมื่อยืนยันชื่อเป้าหมายชัดเจน
4. legacy `DATABASE_URL` และข้อมูลเดิมไม่ถูกแก้โดย Scope นี้

## Execution Record

- Starting legacy migration head: `6b7c8d9e0f12`
- Legacy database inventory: 101 tables, 97 tables with foreign keys, size 16 MB
- Physical Platform database: `restaurant_platform_core_db`; head `p1platform0001`
- Physical Restaurant database: `restaurant_ops_db`; head `p1restaurant0001`
- Independent rollback: ทดสอบ Platform `head → base → head` โดย Restaurant คงอยู่ที่ head และทดสอบ Restaurant แบบกลับกันผ่าน
- Idempotency: `scripts/setup-local-database-boundary.sh` รันซ้ำผ่านโดยไม่สร้าง migration ซ้ำ
- Boundary backup: `/private/tmp/restaurant-boundary-backups/restaurant-boundaries-local-20260731T171602Z`
- Platform dump SHA-256: `a988b61c02f948e3a436926199312ab8cff258e550f0470f9b4d9ce25697526d`
- Restaurant dump SHA-256: `31869fcf7d8692c227d5bb6a8d40f7d2b43697f61fe1dd75d6b6de7353a20a54`
- Restore drill: กู้เข้า `restaurant_platform_core_p1db03verify` และ `restaurant_ops_p1db03verify`, ตรวจ metadata ผ่าน แล้วลบ drill databases สำเร็จ
- Final readiness: legacy database, Platform database, Restaurant database, Redis และ uploads เป็น `ok`
- Legacy data migration: ไม่ได้ย้ายหรือลบ; legacy database ยังคง 101 tables และ head `6b7c8d9e0f12`
- Boundary databases: มีเฉพาะ `alembic_version` และ `database_boundary_metadata` อย่างละ 2 tables; ยังไม่ใช่ system of record
- Backend regression: `96 tests` ผ่าน
- Restaurant functional smoke: ผ่าน
- Restaurant permission smoke: ผ่าน
- Frontend: `type-check` และ production build ผ่าน (มี existing chunk-size warning เท่านั้น)
- Commit: บันทึกใน Git history ของ Scope ID นี้
