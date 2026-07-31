# Scope ID: P0-BASELINE-01

สถานะ: **Approved**
Phase: **Phase 0 — Baseline และ Freeze**
วันที่อนุมัติ: 31 กรกฎาคม 2026
อนุมัติโดย: Platform Owner

## Problem

ระบบมีงาน Restaurant ordering, kitchen, takeaway flow, PromptPay, receipt logo และ Brand UI ที่พัฒนาและทดสอบระหว่างการออกแบบ แต่ยังไม่มี baseline commit และ backup ที่ใช้ย้อนกลับก่อนเริ่มสถาปัตยกรรม multi-business database

## Business Type / Target Database

- `platform_core`: เอกสารขอบเขตและ Brand configuration ปัจจุบันเท่านั้น
- `restaurant`: ตรวจและเก็บ baseline ของ Restaurant flow ปัจจุบัน
- `retail_pos`: regression verification เท่านั้น
- Target database: legacy development database ปัจจุบัน
- ห้ามเปลี่ยน connection routing หรือแยก physical database ใน Scope ID นี้

## In Scope

- ตรวจ diff ที่ยังไม่ commit และระบุว่าเป็นงานใด
- ตรวจ migration head และ migration files ปัจจุบัน
- รัน backend unit tests
- รัน frontend type-check และ production build
- รัน Restaurant smoke flow ที่มีอยู่
- รัน Retail POS regression/smoke ที่มีอยู่ โดยไม่เปลี่ยน feature
- สำรอง development PostgreSQL database
- commit source, migration, tests, asset และเอกสารที่เป็น baseline
- บันทึก commit hash, backup path และผลทดสอบในเอกสารนี้

## Out of Scope

- แยก Control Plane, Restaurant, Retail หรือ Takeaway database
- เพิ่ม `business_type` ในฐานข้อมูล
- refactor URL หรือ route
- เปลี่ยน permission, role หรือ user assignment
- สร้าง Device pairing
- พัฒนา Takeaway Phase 6
- เปลี่ยน Retail POS feature หรือ UX
- deploy หรือ push ไป GitHub/production

## Allowed Areas

- Source/tests/migrations ที่มี diff อยู่ก่อนเริ่ม Scope ID
- `RESTAURANT-ERP-SCOPE-PLAN.md`
- `docs/scopes/P0-BASELINE-01.md`
- Test output และ database backup ในตำแหน่งที่ไม่เข้า Git

หากต้องแก้ source เพื่อให้ test ผ่าน ต้องหยุด ระบุ defect และขออนุมัติ Scope Change ก่อน ห้ามแก้รวมเข้า baseline โดยอัตโนมัติ

## Acceptance Criteria

- [x] Diff ทุกไฟล์ถูกจัดประเภทและไม่มีไฟล์ไม่ทราบที่มา
- [x] Frontend type-check ผ่าน
- [x] Frontend production build ผ่าน
- [x] Backend unit tests ผ่าน
- [x] Restaurant smoke flow ผ่าน
- [x] Retail POS regression/smoke ผ่าน หรือบันทึกข้อจำกัดที่ตรวจได้
- [x] Migration head ถูกบันทึก
- [x] Database backup สร้างสำเร็จและมี checksum
- [x] Baseline commit สำเร็จ
- [x] Working tree หลัง commit สะอาด หรือมีรายการที่ตั้งใจไม่ commit ระบุไว้

## Rollback

1. ใช้ baseline commit hash เพื่อย้อน source code
2. ใช้ database backup ของ Scope ID นี้เพื่อคืน development data
3. ไม่ใช้ destructive Git command และไม่ restore database จน Platform Owner อนุมัติ

## Execution Record

- Migration head: `4e5f6a7b8c93 (head)`
- Backend tests: Passed — `85 tests` ด้วย `scripts/run-backend-regression.sh`
- Frontend type-check: Passed — `npm --prefix frontend run type-check`
- Frontend build: Passed — `npm --prefix frontend run build`
- Restaurant smoke: Passed — `scripts/fnb-smoke.sh` และ `scripts/fnb-permission-smoke.sh`
- Retail regression: ไม่มี automated Retail POS smoke โดยเฉพาะใน repository; ยืนยัน regression guard ด้วย backend 85 tests, frontend type-check และ production build โดยไม่ได้เปลี่ยน Retail POS workflow เพิ่มใน Scope ID นี้
- Backup path: `/private/tmp/restaurant-p0-baseline-20260731-205944.dump`
- Backup SHA-256: `e068e0c0924f27ea883b21d35f4574abb2c33781a1608da24cd3e86c1ce4c704`
- Backup validation: PostgreSQL custom-format archive อ่านสารบัญได้ `1,034` รายการ
- Baseline commit: `2ab8df9` (`feat: baseline restaurant ERP workflows`)
- Notes: F&B smoke ทดสอบ takeaway, dine-in, kitchen, handoff และ checkout; permission smoke ทดสอบ cashier, kitchen, recipe/cost และ manager. ไม่มีการแก้ source ระหว่างการตรวจ Phase 0 และยังไม่ได้ push/deploy
