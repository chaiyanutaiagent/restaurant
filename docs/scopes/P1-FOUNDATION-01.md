# Scope ID: P1-FOUNDATION-01

สถานะ: **Verified**
Phase: **Phase 1 — Tenant, Brand และ Branch Foundation**
วันที่เริ่ม: 31 กรกฎาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

Baseline ปัจจุบันมี Company, Brand, Branch และ `user_branches` แล้ว แต่ยังมีช่องว่างสำคัญก่อนแยก operational database:

- Brand ไม่มี `business_type`
- Branch หนึ่งแห่งสามารถมี active Brand ได้มากกว่าหนึ่งรายการตามโครงสร้างฐานข้อมูลเดิม
- Staff assignment ยังไม่ระบุ Brand, `business_type` และ target database อย่างบังคับ
- access token ยังไม่มี canonical Brand/Business context ที่ backend resolve จาก assignment
- Restaurant API ยังไม่มี guard กลางเพื่อปฏิเสธ Brand ประเภท Retail/Takeaway

## Business Type / Target Database

- ข้อมูลที่แก้ใน Scope ID นี้: `platform_core`
- Business type ที่ backfill และเปิดใช้งาน: `restaurant`
- Target operational database: `restaurant`
- Migration ยังรันบน legacy development database เพื่อรักษาข้อมูลเดิมก่อน cutover

Scope ID นี้สร้าง canonical routing context แต่ **ยังไม่ย้าย operational table หรือ connection ไป physical database ใหม่** การแยก connection, migration history และ backup/restore จริงต้องทำใน Scope ID ถัดไปของ Phase 1 หลัง foundation นี้ผ่าน

## In Scope

- เพิ่ม `brands.business_type` พร้อมค่าที่อนุญาต `restaurant | retail_pos | takeaway`
- backfill Brand ปัจจุบันเป็น `restaurant`
- บังคับหนึ่ง Branch มี active Brand assignment ได้หนึ่งรายการใน MVP
- backfill `user_branches.brand_id` จาก active Brand ของ Branch เมื่อ resolve ได้แน่นอน
- เพิ่ม `business_type` และ `target_database` ใน Staff assignment
- ให้การสร้าง/คืน Staff assignment resolve Brand/Business/Database จาก server
- เพิ่ม Brand/Business/Database ใน canonical authentication context โดยไม่เชื่อค่าจาก frontend
- ป้องกัน Restaurant Brand API ใช้ Brand ที่ไม่ใช่ `restaurant`
- คง legacy API URL และ response field เดิม พร้อมเพิ่ม field ใหม่แบบ backward-compatible
- เพิ่ม migration, unit tests และเอกสาร Scope

## Out of Scope

- physical Control Plane/Restaurant database cutover
- แยก Alembic history และ backup/restore ของสอง database
- ย้าย Restaurant operational data
- Device registry, pairing, token, revoke และ last-seen
- Subscription billing และ custom domain
- Takeaway Phase 6 หรือ Retail Phase 7 operational API/UI
- เปลี่ยน public QR URL หรือ legacy application route
- เปลี่ยน permission presets และ approval flow ของ Phase 2

## Allowed Areas

- `backend/app/models/restaurant.py`
- `backend/app/models/user.py`
- `backend/app/business_context.py`
- `backend/app/schemas/restaurant.py`
- `backend/app/schemas/user_mgmt.py`
- `backend/app/dependencies.py`
- `backend/app/services/admin_service.py`
- `backend/app/services/auth_service.py`
- `backend/app/services/business_context_service.py`
- `backend/app/services/brand_navigation*.py`
- `backend/app/routers/restaurant.py`
- `backend/app/utils/security.py`
- migration และ tests ที่เกี่ยวข้อง
- frontend type definitions ที่ต้องเพิ่ม field แบบ backward-compatible
- เอกสาร Scope/architecture ที่ตรงกับการเปลี่ยนจริง

## Acceptance Criteria

- [x] Brand เดิม `ครัวป่า ปลาเขื่อน` เป็น `restaurant` และสาขา `BKK-01` ยังเห็นข้อมูลเดิม
- [x] สร้างหรือเปิด active Brand ซ้ำบน Branch เดียวกันไม่ได้
- [x] Staff assignment ใหม่ระบุ Brand, `business_type` และ target database จากข้อมูลฝั่ง server
- [x] access context ของ Branch มี Company, Brand, Branch, `business_type` และ target database ที่ตรวจจากฐานข้อมูล
- [x] Company/Brand/Branch ที่ไม่สัมพันธ์กันถูกปฏิเสธโดยไม่เปิดเผยข้อมูลข้าม tenant
- [x] Restaurant Brand API ปฏิเสธ Brand ที่ไม่ใช่ `restaurant`
- [x] legacy Restaurant URL และ payload เดิมยังทำงาน
- [x] migration upgrade/downgrade ตรวจได้
- [x] backend regression, frontend type-check และ production build ผ่าน

## Rollback

1. สำรอง legacy development database ก่อนรัน migration
2. downgrade migration ของ Scope ID นี้เพื่อลบ constraint/column ที่เพิ่ม โดยไม่ลบ Brand, Branch หรือ User เดิม
3. revert source ของ Scope ID นี้ด้วย commit ที่แยกขอบเขต
4. หาก downgrade ไม่ปลอดภัย ให้ restore backup หลังได้รับอนุมัติจาก Platform Owner

## Execution Record

- Baseline commit: `9f3a249`
- Baseline migration head: `4e5f6a7b8c93`
- Existing active mapping: `ครัวป่า ปลาเขื่อน` → `BKK-01`
- Existing active Staff assignments: `6`; ยังไม่มี `brand_id` ทั้ง `6` รายการก่อน migration
- Pre-migration backup: `/private/tmp/restaurant-p1-foundation01-pre-migration-20260731-233530.dump`
- Backup SHA-256: `e68437d24ec5f21c19b2137aef2efb47bcbec2d3a5bdb7c8fb773fd3ad732467`
- Migration: `5a6b7c8d9e01 (head)`; ทดสอบ `upgrade → downgrade → upgrade` ผ่าน
- Backfill: active assignment `5/6` รายการ resolve เป็น `restaurant`; assignment ของ `admin` ที่ `BKK-02` คงเป็น legacy unscoped เพราะ Branch นี้ยังไม่มี active Brand และจะใช้ Restaurant operational context ไม่ได้จนกว่าจะผูก Brand
- Canonical auth verification: `/api/v1/auth/me` คืน Company, Brand `2f967ac7-69fb-4f35-b87a-dfce479177bf`, Branch `368b04a8-990b-4de1-86c6-c61cd83272d0`, `business_type=restaurant`, `target_database=restaurant`
- Legacy Brand API verification: `/api/v1/restaurant/brands` คืน `kruapa-pla-khuean` พร้อม active branch `สาขากรุงเทพ`
- Backend tests: Passed — `92 tests`
- Frontend type-check: Passed — `npm --prefix frontend run type-check`
- Frontend build: Passed — `npm --prefix frontend run build` (มี chunk-size warning เดิม แต่ build สำเร็จ)
- Restaurant smoke: Passed — `scripts/fnb-smoke.sh`
- Permission smoke: Passed — `scripts/fnb-permission-smoke.sh`
- Alembic drift check: P1 column/index/constraint ตรงกับ model; `alembic check` ยังรายงาน comment/index drift เดิมใน dining, goods receipt, recipe และ transfer ซึ่งอยู่นอก Scope ID นี้
- Commit: บันทึกใน Git history ของ Scope ID นี้
