# Scope ID: P1-PHASE-GATE-08

สถานะ: **Verified — Phase 1 gate complete; production activation remains separate**
Phase: **Phase 1 — Tenant, Brand และ Branch Foundation**
วันที่เริ่ม: 1 สิงหาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

Scope `P1-FOUNDATION-01` ถึง `P1-RESTAURANT-RUNTIME-CANARY-07` วาง canonical context,
physical boundaries, data rehearsal, reference projector และ runtime canary แล้ว แต่ roadmap ห้ามเริ่ม
Phase 2 ก่อนปิด Phase 1 gate ด้วยหลักฐานรวมว่า tenant, assignment และ business type ไม่รั่วข้ามกัน,
ข้อมูลเดิมของ `ครัวป่า ปลาเขื่อน` ที่ `BKK-01` ยังอยู่, legacy routes ยังทำงาน และ backup/restore ของ
Platform/Restaurant ยังแยกกันได้

การทดสอบ isolation ห้ามเพิ่ม Tenant B ลงฐานใช้งานจริง Scope นี้จึง clone legacy snapshot ไป temporary
database ที่ตรวจชื่อด้วย prefix, รัน API UAT ในฐานชั่วคราว และ drop ฐานนั้นอัตโนมัติ

## In Scope

- สร้าง Phase 1 gate matrix บน temporary PostgreSQL database
- สร้าง Tenant B แบบ `retail_pos` เฉพาะในฐานชั่วคราว
- พิสูจน์ Company A/B login, branch, settings, Restaurant table และ Brand list isolation
- พิสูจน์ผู้ใช้สลับไป Branch ที่ไม่มี assignment ไม่ได้
- พิสูจน์ Retail context เปิด Restaurant settings/Brand APIs ไม่ได้
- ยืนยัน standalone Retail/Takeaway operational routers ยังไม่ถูกเปิดใน Phase 1; legacy `/pos`
  ยังคงเป็น shared compatibility route จนกว่าจะมี Scope Change ของ Phase 7
- พิสูจน์ canonical context ของ `BKK-01` เป็น Restaurant/Restaurant database จาก server
- ตรวจ retained data ของ Brand `kruapa-pla-khuean` และ `BKK-01`
- ตรวจ legacy System/Restaurant routes ด้วย request จริง
- ตรวจ live source fingerprint ก่อน/หลัง isolated test ว่าไม่เปลี่ยน
- backup/restore drill แยก Platform และ Restaurant targets
- backend regression, frontend type-check/build และเอกสาร closeout

## Representative API Matrix

| Actor | API | Expected |
|---|---|---|
| Tenant A Restaurant | own branch/settings/tables/brands | `200` |
| Tenant A Restaurant | Tenant B branch/settings/table | `404` |
| Tenant A Restaurant | switch to Tenant B branch | `403` |
| Tenant B credentials + Tenant A company | login | `401` |
| Tenant B Retail | own System branch | `200` |
| Tenant B Retail | Tenant A System branch | `404` |
| Tenant B Retail | Restaurant settings/brands | `403` |

## Database / Ownership

- Live rollback source: legacy `DATABASE_URL`, read-only during gate
- Test writes: temporary clone `restaurant_p1_gate_<timestamp>` เท่านั้น
- Physical boundary backup: Platform และ Restaurant แยก dump
- ไม่มี client-controlled database selector
- Final runtime flags ไม่เปลี่ยนจาก `identity=legacy`, `restaurant_service=legacy`, projector disabled

## Out of Scope

- production activation หรือ deploy
- เปลี่ยน system of record จาก legacy เป็น Platform/Restaurant แบบถาวร
- Platform Brand/User administration write cutover
- Phase 2 role preset, manager PIN หรือ approval threshold
- Device pairing Phase 3
- Takeaway Phase 6 หรือ Retail Phase 7
- แก้ข้อมูล Tenant/Brand/Branch จริง

## Acceptance Criteria

- [x] Tenant A/B อ่าน Branch, Settings, Table หรือ Brand ข้ามกันไม่ได้ใน API matrix
- [x] User สลับไป Branch นอก assignment ไม่ได้
- [x] Retail context เปิด Restaurant APIs ไม่ได้
- [x] `ครัวป่า ปลาเขื่อน` → `BKK-01` active mapping และ operational data เดิมยังอยู่
- [x] canonical token context คืน Company/Brand/Branch/Restaurant target จาก server
- [x] legacy System และ Restaurant routes ยังทำงาน
- [x] temporary database ถูก drop และ live source fingerprint ไม่เปลี่ยน
- [x] Platform/Restaurant backup และ restore drill ผ่าน
- [x] backend regression และ frontend type-check/build ผ่าน
- [x] final readiness เป็น legacy/legacy/projector disabled และทุก dependency `ok`
- [x] Phase 1 roadmap/architecture อัปเดตตามหลักฐานจริง
- [x] worktree commit แล้วโดยไม่ push

## Rollback

1. Gate ไม่เปลี่ยน live schema/data; EXIT/signal trap terminate connection และ drop เฉพาะ database ที่ชื่อ
   ขึ้นต้น `restaurant_p1_gate_`
2. หาก restore drill หยุดกลางทาง ให้ลบเฉพาะ drill databases ที่มี suffix ของ Scope นี้หลังตรวจชื่อ
3. Source change ของ Scope นี้เป็น test/script/docs จึง revert ได้ด้วย commit เดียว
4. Runtime flags คง default legacy; ไม่ต้องสลับ backend เพื่อ rollback

## Execution Record

- Starting commit: `2fcac76`
- Starting heads: legacy `6b7c8d9e0f12`, Platform `p1platform0003`, Restaurant `p1restaurant0003`
- Starting/final runtime target: identity `legacy`, Restaurant service `legacy`, projector disabled
- Final rehearsal: `/private/tmp/restaurant-phase1-gate08-complete/p1-phase-gate-08-20260801T001914Z`
- Temporary database: `restaurant_p1_gate_20260801001914`; EXIT cleanup ผ่าน และ final query พบ
  gate/drill databases ค้าง `0`
- Live source fingerprint: `1:3:4:7:26:36:21` ก่อนและหลัง UAT ตรงกัน
- API isolation matrix:
  - Tenant A → Tenant B Branch/Settings/Table: `404`
  - Tenant A → Tenant B branch switch: `403`
  - Tenant B credentials ภายใต้ Company A: `401`
  - Tenant B Retail → Tenant A Branch: `404`
  - Tenant B Retail → Restaurant Settings/Brand APIs: `403`
  - Tenant A/B own System routes และ Tenant A legacy Restaurant routes: `200`
- Canonical context: Tenant A token คืน Company/Brand/BKK-01 พร้อม
  `business_type=restaurant`, `target_database=restaurant`; Tenant B คืน `retail_pos/retail_pos`
- Retained BKK-01 data ใน snapshot: Products 43, Dining Tables 13, Dining Sessions 18,
  Sale Orders 9
- Final heads: legacy `6b7c8d9e0f12`, Platform `p1platform0003`, Restaurant `p1restaurant0003`
- Boundary backup:
  `/private/tmp/restaurant-phase1-gate08-complete/p1-phase-gate-08-20260801T001914Z/boundary/restaurant-boundaries-local-20260801T001921Z`
- Platform dump SHA-256: `0a91c1279230328f183b260f309a1d3ffeef44909c65b7703e2bbc64ecff1773`
- Restaurant dump SHA-256: `d25fd0b081129bd70b41b98a59f5098a96da447f9295507339a42fbfa14c9e23`
- Restore drill: restore Platform/Restaurant เข้า temporary databases, ตรวจ boundary metadata ผ่าน และ
  cleanup สำเร็จ
- Final readiness: legacy, Platform, Restaurant, Redis และ uploads เป็น `ok`; runtime เป็น
  `identity=legacy`, `restaurant_service=legacy`, projector disabled และ projector errors เป็น 0
- Backend regression: 120 tests ผ่าน
- Frontend type-check: ผ่าน
- Frontend production build: ผ่าน; มี chunk-size warning เดิม
- Source impact: เพิ่มเฉพาะ isolated smoke, rehearsal script และเอกสาร; ไม่เปลี่ยน runtime route/schema
- Commit: บันทึกใน Git history ของ Scope ID นี้โดยไม่ push
