# Scope ID: P1-DATA-CUTOVER-04

สถานะ: **Verified — rehearsal complete; runtime cutover pending**
Phase: **Phase 1 — Tenant, Brand และ Branch Foundation**
วันที่เริ่ม: 1 สิงหาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

`P1-DATABASE-BOUNDARY-03` สร้าง physical `platform_core` และ `restaurant` databases, connection pools, Alembic histories และ backup/restore boundary แล้ว แต่ฐานข้อมูลใหม่ยังมีเพียง boundary metadata ขณะที่ข้อมูลจริง 101 tables ยังอยู่ใน legacy `restaurant_pos_db`

การตรวจ runtime พบว่า Brand/Branch administration บาง flow เขียน Control Plane ownership, Restaurant `BranchSettings`, stock-location references และ audit ผ่าน SQLAlchemy transaction เดียว หากสลับ router ทันทีจะเป็น distributed transaction หรือทำให้ reference projection ระหว่าง database ไม่ตรงกัน ซึ่งขัดกับ architecture baseline

Scope นี้จึงเป็น physical data-cutover rehearsal ที่หยุด writer ชั่วคราว, snapshot ข้อมูล, แยก Platform ownership subset, สร้าง Restaurant operational snapshot, ตรวจ row parity และทดสอบ rollback โดย legacy database ยังเป็น system of record จนกว่า outbox/reference projection จะพร้อมใน Scope ถัดไป

## Business Type / Target Database

- Source/rollback system of record: legacy `restaurant_pos_db`
- Control Plane rehearsal target: `restaurant_platform_core_db`
- Restaurant rehearsal target: `restaurant_ops_db`
- Business type: `restaurant`
- Runtime routing mode: `legacy` ตลอด Scope นี้

## In Scope

- เพิ่ม migration metadata สำหรับ snapshot rehearsal แยกใน Platform และ Restaurant Alembic histories
- สำรอง legacy, Platform-before และ Restaurant-before ก่อน recreate target databases
- restore legacy snapshot เข้า target databases จาก dump เดียวกันใน maintenance window
- prune Platform database ให้เหลือเฉพาะ Company/Brand/Branch/Identity/Assignment/Audit ownership tables
- เก็บ Platform reference columns ที่ชี้ operational UUID แต่ถอด SQL FK เมื่อ referenced table อยู่อีก database
- คง Restaurant operational tablesและ transitional ownership reference projections เพื่อให้ Scope runtime cutover ถัดไปทดสอบ ORM เดิมได้
- บันทึก legacy schema head แยกจาก domain Alembic head
- ตรวจ row-count parity ของ Control Plane และ Restaurant critical tables
- เพิ่ม rollback tooling เพื่อคืน target databases จาก pre-rehearsal dumps
- ทดสอบ rehearsal → rollback → rehearsal
- อัปเดต architecture/runbook และ regression tests ที่เกี่ยวข้อง

## Out of Scope

- เปลี่ยน `get_db`, API router หรือ production runtime ให้ใช้ target databases
- เปลี่ยน system of record จาก legacy database
- dual-write หรือ distributed SQL transaction
- outbox worker, reference projection processor และ live CDC
- drop/move/delete table หรือ row จาก legacy database
- prune Retail-compatible tables จาก Restaurant rehearsal target
- Takeaway/Retail operational cutover
- production deploy หรือ push

## Platform Ownership Tables

- `companies`
- `brands`
- `branches`
- `brand_branches`
- `users`
- `roles`
- `permissions`
- `role_permissions`
- `user_branches`
- `refresh_tokens`
- `user_access_requests`
- `user_invitations`
- `audit_logs`

## Acceptance Criteria

- [x] pre-rehearsal backup มี legacy, Platform-before และ Restaurant-before dumps
- [x] target ทั้งสองมาจาก legacy snapshot เดียวกันและบันทึก source head เดียวกัน
- [x] Platform ownership tables มี row parity กับ legacy ทุกตาราง
- [x] Platform database ไม่มี Restaurant operational tables
- [x] Restaurant critical operational tables มี row parity กับ legacy
- [x] Restaurant database มี ownership reference projections สำหรับ ORM compatibility แต่ metadata ระบุว่าไม่ใช่ system of record
- [x] Alembic histories ของ Platform และ Restaurant ยังแยกกัน
- [x] legacy database ยัง 101 tables, head เดิม และไม่ถูก drop/recreate
- [x] rollback คืน target databases เป็น boundary-only state ได้
- [x] rerun rehearsal หลัง rollback ผ่าน
- [x] backend regression, frontend type-check/build และ Restaurant smoke ผ่านบน legacy runtime

## Rollback

1. หยุด backend writer
2. restore `platform-before.dump` และ `restaurant-before.dump` เข้า target database ชื่อเดิม
3. restart backend และตรวจ `/health/ready`
4. legacy runtime/database ไม่ต้อง restore เพราะ Scope นี้ไม่เขียน schema/data ลง legacy

## Execution Record

- Starting legacy head: `6b7c8d9e0f12`
- Starting Platform head: `p1platform0001`
- Starting Restaurant head: `p1restaurant0001`
- Runtime mixed-write finding: Brand/Branch ownership, Branch settings, stock references and audit share legacy transactions
- First rehearsal backup: `/private/tmp/restaurant-cutover04/p1-data-cutover-04-20260731T173010Z`
- Rollback verification: target databases กลับเป็น boundary-only, 2 tables, heads `p1platform0001` / `p1restaurant0001`; readiness ผ่าน
- Final rehearsal: `/private/tmp/restaurant-cutover04-rerun/p1-data-cutover-04-20260731T173139Z`
- Final source dump SHA-256: `10e1a116eb93cf6f93fa608805bcba0ec6d2fb440a168bf5cffa8b2387519cb6`
- Final pre-rehearsal Platform dump SHA-256: `8fdd42a38ba75d6f2765589f84166148fde62ae142b71946bb9aa23b4c6a6efc`
- Final pre-rehearsal Restaurant dump SHA-256: `e0d086cc5254cb86428b171b0e8aa845c87c9ea5c808906320ed21798caff2b4`
- Platform parity: 13 ownership tables ตรงกับ legacy; final Platform มี 17 public tables รวม migration/metadata และไม่มี `dining_sessions`, `sale_orders`, `products`, `stock_balances`, `recipes`
- Restaurant parity: 21 critical ownership/operational tables ตรงกับ legacy ณ snapshot; final Restaurant มี 104 public tables รวม migration/metadata
- Final domain heads: `p1platform0002` และ `p1restaurant0002`; ทดสอบ downgrade/upgrade แยกกันผ่าน
- Final independent backup: `/private/tmp/restaurant-cutover04-final-backups/restaurant-boundaries-local-20260731T173452Z`
- Final Platform dump SHA-256: `ee43a9af8fd88f752cb9bf60e89842b43f07d79fdb26d91c56c73d130083ea17`
- Final Restaurant dump SHA-256: `acd3ed2acab73f17620c60857ffea348cccb894b438421f3b5de946f68c0f5ff`
- Final restore drill: restore เข้า database ชั่วคราวสองลูก, ตรวจ boundary metadata ผ่าน และลบ drill databases สำเร็จ
- Legacy writer proof หลัง UAT: legacy `refresh_tokens=60`, `audit_logs=87`, `dining_sessions=27`; snapshots คง `refresh_tokens=55`, `audit_logs=79`, `dining_sessions=24`
- Final metadata: target ทั้งสองระบุ `is_system_of_record=false`; legacy คง 101 tables และ head `6b7c8d9e0f12`
- Final readiness: legacy, Platform, Restaurant, Redis และ uploads เป็น `ok`
- Backend regression: `96 tests` ผ่าน
- Restaurant functional smoke: ผ่าน
- Restaurant permission smoke: ผ่าน
- Frontend: `type-check` และ production build ผ่าน (มี existing chunk-size warning เท่านั้น)
- Commit: บันทึกใน Git history ของ Scope ID นี้
