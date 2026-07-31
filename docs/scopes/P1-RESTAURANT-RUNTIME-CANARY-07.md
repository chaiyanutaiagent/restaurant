# Scope ID: P1-RESTAURANT-RUNTIME-CANARY-07

สถานะ: **Verified — canary complete; final runtime rolled back to legacy**
Phase: **Phase 1 — Tenant, Brand และ Branch Foundation**
วันที่เริ่ม: 1 สิงหาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

`P1-RUNTIME-CUTOVER-06` พิสูจน์ Platform identity canary แล้ว แต่ Restaurant API ยังอ่าน/เขียน
legacy database ทั้งหมด การสลับ Branch Settings เพียง endpoint เดียวไม่ปลอดภัย เพราะ settings เดียวกัน
ถูกใช้ใน F&B setup, dining, public menu, kitchen, payment QR และ pickup workflow

ในทางกลับกัน Restaurant router เดียวกันยังมี Brand/BrandBranch administration ซึ่งเป็น Platform-owned
control plane จึงห้ามสลับทั้งไฟล์แบบเหมารวม Scope นี้เลือกเฉพาะ Restaurant service workflow ที่มี
transaction boundary ชัดเจน และคง Brand administration/central control endpoints ไว้ legacy

## Runtime Slice

- Server-owned switch: `RESTAURANT_SERVICE_DATABASE=legacy|restaurant`
- Default/rollback value: `legacy`
- Canary value: `restaurant`
- Canary authenticated routes:
  - `/api/v1/restaurant/settings` และ `/setup`
  - tables, sessions, orders, kitchen, payment QR และ pickup queue
- Canary public routes:
  - `/api/public/menu/{qr_token}` order/status/bill
  - `/api/public/qs/{qs_token}` menu/order/status
- System Branch Settings routes รวม JSON update และ image upload/delete
- Identity source ขณะ canary: `platform_core`

## In Scope

- เพิ่ม Restaurant service session factory/dependency และ server-owned config
- startup guard บังคับ Platform identity, projector และสาม physical databases เมื่อเปิด canary
- route เฉพาะ F&B service endpoints ไป Restaurant database
- route System Branch Settings access check ไป Identity DB และ settings/audit transaction ไป active
  Restaurant service DB
- แสดง active Restaurant source ใน API metadata และ readiness
- fresh maintenance rebaseline จาก legacy ไป Platform/Restaurant ก่อน canary
- seed/reconcile Platform reference events หลัง rebaseline
- live legacy → Platform identity + Restaurant service → legacy rehearsal
- พิสูจน์ settings/audit และ dining writes อยู่เฉพาะ Restaurant ระหว่าง canary
- rollback trap, backup, parity, restore drill และ regression/smoke

## Ownership Guard

- `/restaurant/brands` create/update/assignment ยังคง legacy ใน Scope นี้
- central Brand/BrandBranch transfer configuration ยังคง legacy
- Product/Stock/System routes นอก canary ยังคง legacy
- Restaurant target ใช้ Company/Brand/Branch/User projections เป็น scalar/FK compatibility references
- ห้าม client header/query/body เลือก database

## Consistency Contract

1. เปิด canary ได้หลังหยุด writer และสร้าง fresh consistent snapshot เท่านั้น
2. Auth/authorization อ่าน Platform; F&B service transaction เขียน Restaurant เพียงฐานเดียว
3. Branch Settings update และ operational audit commit ใน Restaurant transaction เดียวกัน
4. Public menu/order ใช้ Restaurant target เดียวกับ authenticated dining session
5. Rollback กลับ legacy ไม่ copy operational rows ย้อนอัตโนมัติ; canary ต้องเป็น bounded UAT window
6. ค่า settings ที่แก้เพื่อ UAT ต้องคืนค่าเดิมใน Restaurant ก่อนปิด canary

## Out of Scope

- Brand/BrandBranch administration cutover
- central production, credit, transfer และ WAP/store router cutover
- generic Product/Stock/POS/Accounting router cutover
- automatic ongoing CDC จาก legacy operational tables
- production activation, production deploy หรือ push
- Retail/Takeaway database cutover

## Acceptance Criteria

- [x] default Restaurant service source เป็น legacy
- [x] Restaurant mode start ไม่ได้หาก Identity ไม่ใช่ Platform
- [x] Restaurant mode start ไม่ได้หาก projector ปิดหรือ physical DB ไม่แยก
- [x] fresh rebaseline และ Platform→Restaurant reference parity ผ่านก่อน canary
- [x] system settings access ใช้ Identity DB แต่ settings/audit เขียน Restaurant
- [x] F&B setup/dining/public order workflow เขียน Restaurant โดย legacy count ไม่เปลี่ยน
- [x] Brand administration routes ไม่ถูกย้ายไป Restaurant
- [x] settings canary value คืนค่าเดิมก่อน rollback
- [x] final runtime กลับ `identity=legacy`, `restaurant_service=legacy`, projector ปิด
- [x] backend regression และ F&B functional/permission smoke ผ่าน
- [x] final backup/restore drill ผ่าน
- [x] worktree commit แล้วโดยไม่ push

## Rollback

1. ตั้ง `RESTAURANT_SERVICE_DATABASE=legacy`
2. ตั้ง `IDENTITY_DATABASE=legacy`
3. ตั้ง `REFERENCE_PROJECTOR_ENABLED=false`
4. restart backend และตรวจ `/health/ready`
5. access token เดิมใช้ต่อได้หาก User ยัง active ใน legacy; Platform refresh token ต้อง login ใหม่
6. operational rows ที่สร้างใน Restaurant ระหว่าง canaryไม่ถูก copy กลับ legacy; ใช้เฉพาะ UAT data
7. หากต้องคืน target ทั้งฐาน ให้ restore pre-canary Platform/Restaurant dumps

## Execution Record

- Starting commit: `e36de37`
- Starting runtime: identity `legacy`, Restaurant service `legacy`, projector disabled
- Starting heads: legacy `6b7c8d9e0f12`, Platform `p1platform0003`, Restaurant `p1restaurant0003`
- Final rehearsal:
  `/private/tmp/restaurant-canary07-final/p1-restaurant-runtime-canary-07-20260731T195757Z`
- Fresh rebaseline: recreate เฉพาะ Platform/Restaurant targets จาก legacy snapshot ผ่าน; critical row-count
  parity และ independent migrations ผ่าน
- Pre-canary dump SHA-256:
  - Legacy: `84b781b2f0112ae663c44a722d616a550a04676ec27014f8a8fe5f161437598b`
  - Platform: `9683484a45c012a52595b7a3000b652abc138c34ff09ee06900d724f0dc86426`
  - Restaurant: `8bb4bfccbea00a50a551aeb71e652af249b21ba9bbe085f448c9ab8cce38f34a`
- Startup guards: ปฏิเสธ Restaurant mode เมื่อ Identity ยังเป็น legacy, projector ปิด หรือ actual
  PostgreSQL database names ไม่แยกครบสามฐาน
- Pre-canary projection: 22 events applied, 0 failed; Company 1, Branch 4, Brand 3,
  BrandBranch 7 และ User 7 ตรงกัน
- Branch Settings proof: access/permission อ่าน Platform; settings update และ
  `system.branch.settings_updated` audit เขียนเฉพาะ Restaurant; canary value ไม่เปลี่ยน legacy และคืนค่า
  เดิมใน Restaurant ก่อน rollback
- F&B functional canary: setup, takeaway public QR, kitchen, pickup, dine-in public QR, bill และ
  checkout ผ่าน Restaurant database
- Operational isolation:
  - Legacy dining sessions `36 → 36`; Restaurant dining sessions `36 → 39`
  - Legacy sale orders `21 → 21`; Restaurant sale orders `21 → 23`
- Permission canary: cashier/kitchen/recipe/manager matrix ผ่าน โดย Identity อยู่ Platform,
  F&B workflow อยู่ Restaurant และ recipe/report routes ที่อยู่นอก Scope ยังคง legacy
- Ownership route tests: F&B/system settings dependencies ใช้ Restaurant service DB; Brand create/update
  และ ingredient report ยังคง `get_db` (legacy)
- Rollback proof: Platform-issued access token ยังผ่าน `/auth/me`; Branch Settings กลับไปอ่าน legacy;
  final runtime เป็น `identity=legacy`, `restaurant_service=legacy`, projector disabled
- Final projection: เพิ่ม 4 User events จาก permission UAT, 0 failed; final outbox 37 processed,
  0 pending และ Restaurant ledger 37; reference parity ตรงกันทั้งหมด
- Final heads: legacy `6b7c8d9e0f12`, Platform `p1platform0003`, Restaurant `p1restaurant0003`
- Final readiness: legacy, Platform, Restaurant, Redis และ uploads เป็น `ok`; projector error/loop error
  เป็น 0
- Backend regression: 120 tests ผ่าน
- Restaurant functional smoke: ผ่านด้วย `FNB_SMOKE_DATABASE=restaurant`
- Restaurant permission smoke: ผ่านด้วย Platform identity + Restaurant service topology
- Final boundary backup:
  `/private/tmp/restaurant-canary07-final/p1-restaurant-runtime-canary-07-20260731T195757Z/final-boundary/restaurant-boundaries-local-20260731T195910Z`
- Final Platform dump SHA-256: `26634c539f10138763b569d7c8a683b9bfbf6204d01954ba7985681b34aeba06`
- Final Restaurant dump SHA-256: `327ea25f26e26548d93dea788b41877bf84c38f5ccb55c755649f0d212b22620`
- Final restore drill: restore เข้า temporary Platform/Restaurant databases, ตรวจ boundary metadata ผ่าน
  และลบ drill databases สำเร็จ
- Commit: บันทึกใน Git history ของ Scope ID นี้โดยไม่ push
