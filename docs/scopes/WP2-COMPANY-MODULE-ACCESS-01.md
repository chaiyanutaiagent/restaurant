# WP2-COMPANY-MODULE-ACCESS-01 — Server-owned Company Module Access

วันที่วางแผน: 2026-09-13

สถานะ: **completed_local — implementation และ automated gate ผ่าน; ยังไม่ deploy**

Baseline: WP1 gate บน branch `codex/foodchainservice-platform`

## Problem

WP1 ทำ module registry ฝั่ง frontend ให้ชื่อและสถานะตรงกันแล้ว แต่ runtime access ของ Company
ยังไม่ได้อ่านรายการโมดูลจาก server โดยตรง ปัจจุบัน Platform มี `feature_flags` ใน plan และ tenant
profile อยู่แล้ว ขณะที่ Brand entitlement เดิมใช้เฉพาะความสามารถย่อยของ Restaurant จึงไม่ควรสร้าง
entitlement ซ้ำหรือให้ frontend เดาสถานะจาก permission เพียงอย่างเดียว

## User outcome

- Platform Owner เปิดหรือปิดโมดูลของแต่ละ Company ได้จากแหล่งข้อมูลกลางพร้อมเหตุผลและ audit
- Company Admin เห็นโมดูลที่ Company สมัครใช้และตัวเองมีสิทธิ์ทำงานเท่านั้น
- การปิดโมดูลหยุด entry/API ใหม่โดยไม่ลบประวัติหรือข้อมูล operational เดิม
- Customer Register ตั้งค่าโมดูลแรกให้ Company ใหม่อย่าง deterministic
- Takeaway ยังคง dark launch จนกว่าจะมี activation gate แยก

## Proposed contract

ใช้ stable module keys จาก WP1:

```text
erp
central_kitchen
restaurant_pos
takeaway_pos
retail_pos
hotel_pms
```

Company module response ต้องมีอย่างน้อย:

- `module_key`
- `lifecycle`: `active`, `dark_launch`, `planned`
- `company_enabled`
- `plan_included`
- `effective_access`
- `reason_code`
- `updated_at` และ actor/audit reference สำหรับ Platform view

กติกา effective access:

```text
catalog lifecycle อนุญาต
AND plan รวมโมดูล
AND Company เปิดโมดูล
AND user permission/scope ผ่าน
AND operational runtime พร้อม
```

frontend ไม่สามารถส่ง database หรือ business type มาเลือกเอง

## In scope

### WP2-A — Existing control audit และ canonical mapping

- ตรวจ semantics ของ `SaasPlan.feature_flags` และ `PlatformTenantProfile.feature_flags`
- กำหนด mapping เดิม `restaurant`, `retail_pos`, `takeaway` ไป stable WP1 keys
- กำหนด default ที่ fail closed สำหรับ key ที่ไม่รู้จัก
- เลือกวิธี compatibility ที่ไม่ทำให้ tenant เดิมเสีย

### WP2-B — Server-owned module API

- เพิ่ม Company-user read API สำหรับ effective module access
- เพิ่ม Platform Owner read/update API โดยต้องส่ง reason และบันทึก audit
- validate key/state ด้วย allowlist; ไม่รับ arbitrary feature key ใน module endpoint
- response ไม่เปิดเผย tenant อื่นหรือ operational record

### WP2-C — Signup และ Company Admin integration

- Restaurant signup เปิดเฉพาะ `restaurant_pos` ตาม plan/default ที่อนุมัติ
- workspace selector ใช้ server response ร่วมกับ user permission
- Company Admin แสดงสถานะ plan/company/runtime แยกกันอย่างเข้าใจง่าย
- network/API failure ต้อง fail closed สำหรับ dark-launch/planned modules

### WP2-D — Migration/compatibility gate

- หาก canonical key จำเป็นต้องเขียนข้อมูล ให้ใช้ Platform migration chain เท่านั้น
- migration ต้อง backfill แบบ idempotent และมี downgrade/rollback ชัดเจน
- ทดสอบ tenant isolation, concurrent update, audit, suspension และ legacy key compatibility
- backup/restore drill เฉพาะฐานที่ migration กระทบ

## Out of scope

- ไม่เปิด billing collection หรือเปลี่ยนราคา plan
- ไม่ activate Takeaway/Hotel/Retail ให้ลูกค้าจริง
- ไม่สร้าง Hotel operational tables
- ไม่ย้าย Central Kitchen ออกจาก Restaurant database
- ไม่เปลี่ยน Restaurant/Takeaway operational schema หรือ public URLs
- ไม่ rename repository, Docker, database หรือ Cloudflare resources
- ไม่ทำ production deployment

## Acceptance criteria

- [x] Company module access มี server-owned endpoint และ stable key allowlist
- [x] Platform Owner update ต้องมี reason, session guard และ audit record
- [x] Company A อ่าน module state ได้จาก Company ID ใน signed session เท่านั้น
- [x] plan, Company flag, lifecycle, permission และ runtime readiness ถูกประเมินแยกกัน
- [x] unknown/planned/dark-launch state fail closed
- [x] tenant เดิมที่ใช้ `restaurant`, `retail_pos`, `takeaway` ไม่เสีย compatibility
- [x] Customer Register สร้าง Company ด้วย module state ที่คาดเดาได้และยิงซ้ำไม่สร้างซ้ำ
- [x] frontend selector ใช้ server response แต่ backend guard เดิมยังเป็น enforcement
- [x] ไม่ต้อง migration เพราะใช้ JSON controls เดิม; migration heads จึงไม่เปลี่ยน
- [x] backend/frontend/browser regression ผ่าน
- [x] ไม่มี UAT/Production activation ระหว่าง WP2

## Rollback

- revert frontend server-state integration เพื่อกลับไป WP1 static registry ก่อน
- จากนั้น revert backend endpoint/service โดยไม่แก้ JSON controls เดิม
- ไม่มี Platform migration ใน WP2 จึงไม่ต้อง downgrade หรือ restore ฐานข้อมูลสำหรับ rollback ปกติ
- ใช้ tag `pre-foodchainservice-platform-20260913` และ WP0 backup เป็น disaster fallback

## WP2-A decision

existing JSON `SaasPlan.feature_flags` และ `PlatformTenantProfile.feature_flags` เพียงพอ โดยแยก
ความหมายเป็น plan inclusion กับ Company switch ใน service และ map legacy keys ขณะอ่าน/เขียน
จึงไม่เพิ่ม table, backfill หรือ migration ใน WP2

ผลตรวจรับอยู่ที่ `docs/scopes/WP2-PHASE-GATE-03.md`

งานถัดไปที่กำหนดไว้คือ `docs/scopes/WP3-COMPANY-WORKSPACE-PROVISIONING-01.md`
