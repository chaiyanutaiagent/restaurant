# WP1-PLATFORM-SHELL-MODULE-MAP-01 — Foodchainservice Shell และ Module Map

วันที่วางแผน: 2026-09-13

สถานะ: **completed_local — implementation และ automated gate ผ่าน; ยังไม่ deploy**

Baseline: `pre-foodchainservice-platform-20260913`

## Problem

ระบบมี Restaurant, Retail, Takeaway, ERP Admin และ Platform Control Plane แล้วบางส่วน แต่ชื่อ
ผลิตภัณฑ์และรายการโมดูลยังกระจาย hard-code อยู่หลายหน้า เช่น `Restaurant POS`,
`Restaurant Platform` และ `ERP POS` ทำให้หน้าลงทะเบียน, Company Admin และ Platform Owner
อธิบายโครงสร้าง Foodchainservice ไม่ตรงกัน

หน้าเลือกโมดูลกับหน้าลงทะเบียนยังมีสถานะคนละชุด และการแสดงโมดูลอาศัย permission เฉพาะบางรายการ
จึงต้องสร้าง contract กลางสำหรับชื่อ, route, สถานะ และ access hint ก่อนแยก service หรือ rename
ส่วน infrastructure ใน work package ถัดไป

## User outcome

- ลูกค้าเห็นชื่อ `Foodchainservice` ตั้งแต่หน้าลงทะเบียนและหน้าเลือกพื้นที่ทำงาน
- Company Admin เห็น ERP และโมดูล POS ที่ตัวเองมีสิทธิ์ใช้จากรายการเดียวกัน
- Platform Owner เห็นชื่อ `Foodchainservice Platform` ชัดเจนและไม่ปะปนกับ Company Admin
- Restaurant POS และ Takeaway POS เดิมยังเปิดด้วย URL และ permission เดิม
- โมดูลที่ยังไม่พร้อม เช่น Hotel PMS แสดงเป็นแผนงานหรือไม่แสดง โดยไม่เปิด route โดยบังเอิญ

## In scope

### 1. Product identity contract

- เพิ่มค่ากลางสำหรับชื่อผลิตภัณฑ์ `Foodchainservice`, ชื่อ platform และชื่อ Company Admin
- เปลี่ยนเฉพาะข้อความระดับผลิตภัณฑ์ใน public selector, signup, shared admin shell และ platform shell
- คงชื่อ `Restaurant POS`, `Takeaway POS` และ `Retail POS` ในหน้าของโมดูลนั้น

### 2. Frontend module map

สร้าง typed module registry กลาง โดยแต่ละรายการมีอย่างน้อย:

- stable key
- ชื่อและคำอธิบาย
- module group: `control`, `shared_service` หรือ `pos`
- entry route
- availability: `active`, `dark_launch` หรือ `planned`
- permission hints
- business type ที่เกี่ยวข้อง

รายการเป้าหมายของ WP1:

| Module key | ชื่อ | สถานะเริ่มต้น |
| --- | --- | --- |
| `company_admin` | Company Admin | active |
| `erp` | ERP และรายงาน | active |
| `central_kitchen` | Central Kitchen / Supply Chain | active ผ่านหน้าปัจจุบัน |
| `restaurant_pos` | Restaurant POS | active |
| `takeaway_pos` | Takeaway POS | dark launch |
| `retail_pos` | Retail POS | existing/compatibility |
| `hotel_pms` | Hotel PMS | planned |

สถานะใน registry เป็น presentation/runtime map ไม่ใช่ entitlement system ใหม่ และห้ามใช้แทน
backend authorization

### 3. Shared entry surfaces

- ปรับ `/` ให้เป็น Foodchainservice workspace selector
- ปรับ `/signup` ให้เป็น Customer Register ที่ใช้ชื่อและสถานะจาก module map
- ปรับ `/admin` shell ให้สื่อว่าเป็น Company Admin/ERP ไม่ใช่ Restaurant Platform
- ปรับ `/platform/*` shell ให้ใช้ชื่อ Foodchainservice Platform สำหรับ Platform Owner
- ลดรายการชื่อและคำอธิบายที่ซ้ำกัน โดยให้ selector/signup/navigation อ่าน contract เดียวกัน

### 4. Compatibility และการทดสอบ

- เพิ่ม unit/component tests สำหรับ module registry และการกรองตาม permission/status
- เพิ่ม route smoke สำหรับ public, Company Admin, Platform Owner, Restaurant และ Takeaway
- รัน frontend type-check/build และ backend regression ทั้งชุด
- บันทึกหลักฐาน WP1 โดยแยก automated gate ออกจาก physical Safari/iPad UAT

## Out of scope

- ไม่ rename GitHub repository, local directory, Docker project, images หรือ database
- ไม่เปลี่ยน `/restaurant`, `/takeaway`, `/pos`, `/admin` หรือ `/platform` routes
- ไม่เพิ่ม/ย้ายตารางและไม่มี database migration
- ไม่ generalize `brand_module_entitlements` ใน WP1
- ไม่เปิด Takeaway ให้ลูกค้าจริงและไม่เปิด Retail/Hotel signup
- ไม่ย้าย Central Kitchen ออกจาก Restaurant database ใน WP1
- ไม่แก้ Cloudflare, UAT/Production environment หรือ authentication bypass
- ไม่นำเข้าข้อมูลจาก `/Users/user/Projects/erp-pos-run`

## Expected files

- `frontend/src/config/platformBrand.ts` — product identity constants
- `frontend/src/config/platformModules.ts` — typed module registry
- `frontend/src/pages/ModuleSelectorPage.tsx`
- `frontend/src/pages/auth/SignupProductSelectorPage.tsx`
- `frontend/src/components/layout/AppShell.tsx`
- `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/components/layout/PlatformShell.tsx`
- tests ที่เกี่ยวข้องและเอกสาร route/module map

รายชื่อไฟล์เป็นขอบเขตคาดการณ์ หาก implementation จำเป็นต้องแตะ backend model, migration,
deployment หรือ public route ต้องหยุดและขอ Scope Change ก่อน

## Delivery slices

1. **WP1-A — Contract:** เพิ่ม product identity และ module registry พร้อม unit tests
2. **WP1-B — Customer entry:** ปรับ workspace selector และ Customer Register ให้ใช้ contract กลาง
3. **WP1-C — Admin shells:** ปรับ Company Admin และ Platform Owner branding/navigation
4. **WP1-D — Compatibility gate:** route smoke, regression, build, secret scan และ evidence

แต่ละ slice ต้องเป็น commit แยกและย้อนกลับได้

## Acceptance criteria

- [x] ชื่อส่วนกลางทั้งหมดใช้ `Foodchainservice` จาก contract เดียว
- [x] ชื่อ Restaurant/Takeaway/Retail ยังอยู่เฉพาะบริบทโมดูลของตัวเอง
- [x] selector และ signup ใช้ module key/status จาก registry เดียวกัน
- [x] ผู้ไม่มี permission ไม่เห็นลิงก์เข้าโมดูลที่ห้ามใช้ และ backend guard เดิมยังทำงาน
- [x] Takeaway ยังเป็น dark launch และ Hotel ยังเป็น planned
- [x] URL/QR เดิมของ Restaurant และ Takeaway ไม่เปลี่ยน
- [x] ไม่มี migration และ migration heads ทั้งสี่ยังคงเดิม
- [x] frontend tests, type-check และ production build ผ่าน
- [x] backend regression `251` tests หรือมากกว่าผ่าน
- [x] tracked secret scan ไม่มี finding
- [x] ไม่มี UAT/Production deployment ระหว่าง WP1

## Rollback

- revert commit ของแต่ละ WP1 slice ย้อนลำดับ D → A
- หากสาขาเสียหาย ให้สร้างสาขาใหม่จาก tag `pre-foodchainservice-platform-20260913`
- WP1 ไม่มี data migration จึงไม่ต้อง restore database สำหรับการ rollback ปกติ
- หากมีผลกระทบข้อมูลนอกแผน ให้หยุดและใช้ backup ที่
  `/Users/user/Backups/Foodchainservice/WP0-20260913`

## งานที่ตามหลัง WP1

WP2 ควรออกแบบ Company-level module subscription/entitlement ใน `platform_core` และ onboarding
ให้ module registry รับสถานะจาก server อย่างแท้จริง งานนั้นต้องมี migration, API, audit และ rollback
plan แยกจาก WP1 และยังไม่ถือว่าอนุมัติจากเอกสารนี้

ผลตรวจรับ implementation อยู่ที่ `docs/scopes/WP1-PHASE-GATE-02.md`
