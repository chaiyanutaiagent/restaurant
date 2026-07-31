# Scope ID: P1-BRANCH-CLEANUP-02

สถานะ: **Verified**
Phase: **Phase 1 — Tenant, Brand และ Branch Foundation**
วันที่เริ่ม: 31 กรกฎาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

`BKK-02` (`สาขาบางนา`) เป็น default development branch ที่ยังไม่มี active Brand และไม่มี operational data แต่ bootstrap seed สร้างสาขานี้ซ้ำบนฐานข้อมูลใหม่ ทำให้มี legacy unscoped assignment ค้างหลัง `P1-FOUNDATION-01`

การผูกสาขานี้เป็น `takeaway` ตอนนี้ไม่ถูกต้อง เพราะ Takeaway operational database/service อยู่ Phase 6 และยังไม่ได้รับอนุมัติให้เริ่ม implement

## Business Type / Target Database

- ข้อมูลที่แก้: `platform_core` บน legacy development database
- `BKK-02`: ไม่มี business type และไม่มี target operational database หลัง archive
- ไม่สร้าง `takeaway` Brand/assignment/database ใน Scope ID นี้

## In Scope

- archive `BKK-02` ด้วย `branches.is_active=false` โดยไม่ hard delete
- ปิด stock location ที่เป็นของ `BKK-02`
- ถอน active `admin` assignment ของ `BKK-02`
- เอา `BKK-02` ออกจาก default company seed เพื่อไม่ให้ฐานข้อมูลใหม่สร้างกลับ
- ปรับ stock access smoke test ให้สร้าง branch fixture ของตัวเอง
- ปรับ test beverage seed ไม่ให้เปิดสอง active Brand บน Branch เดียวกัน
- ปรับเอกสาร Android pilot ไม่ให้ถือ `BKK-02` เป็น default branch
- เพิ่ม migration ที่ downgrade กลับได้

## Out of Scope

- hard delete Branch, settings, stock location หรือ audit record
- สร้าง Takeaway Brand, route, permission หรือ database
- เปลี่ยน `BKK-01` หรือ Brand `ครัวป่า ปลาเขื่อน`
- ลบข้อมูล operational ของสาขาใด
- เปลี่ยน production environment หรือ deploy/push

## Acceptance Criteria

- [x] `BKK-02` ยังคงมี record แต่ `is_active=false`
- [x] ไม่มี active Staff assignment ที่ `BKK-02`
- [x] stock location ของ `BKK-02` ถูกปิดใช้งานโดยไม่ลบ
- [x] application restart ไม่สร้างหรือเปิด `BKK-02` กลับ
- [x] fresh default seed สร้างเฉพาะ `BKK-01`
- [x] smoke test ไม่อ้าง `BKK-02` เป็น default fixture
- [x] ไม่เกิด Takeaway Brand/assignment/database
- [x] migration upgrade/downgrade ผ่าน
- [x] backend regression และ Restaurant smoke ผ่าน

## Rollback

1. downgrade migration ของ Scope ID นี้เพื่อเปิด `BKK-02`, stock location และ admin assignment กลับ
2. revert source commit เพื่อคืน `BKK-02` เข้า default seed
3. หากพบ operational data ที่ไม่คาดไว้ migration ต้องหยุดโดยไม่เปลี่ยนข้อมูล

## Execution Record

- Starting migration head: `5a6b7c8d9e01`
- Pre-check: `BKK-02` มีเฉพาะ `branch_settings=1`, `stock_locations=1`, `user_branches=1`
- Operational rows: ไม่พบ
- Backup: `/private/tmp/restaurant-p1-branch-cleanup02-pre-migration-20260731-235553.dump`
- Backup SHA-256: `d1dab60f377125db71d58a72ba44511da7762fe0b8196792c3818e54507949b8`
- Migration verification: `upgrade 6b7c8d9e0f12 -> downgrade 5a6b7c8d9e01 -> upgrade 6b7c8d9e0f12` ผ่าน
- Final database state: `BKK-02 is_active=false`, active location `0`, active assignment `0`, Takeaway Brand `0`
- Restart verification: backend healthy และ `BKK-02` ยัง archive หลัง rebuild/restart
- Backend regression: `93 tests` ผ่าน
- Stock access API smoke: ผ่านด้วย dedicated test branches
- Restaurant functional smoke: ผ่าน
- Restaurant permission smoke: ผ่าน
- Frontend: `type-check` และ production build ผ่าน (มี existing chunk-size warning เท่านั้น)
