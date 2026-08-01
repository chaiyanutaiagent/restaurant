# Scope ID: P2-SCOPE-ASSIGNMENTS-02

สถานะ: **Verified — scoped assignment foundation complete; approval limits remain separate**
Phase: **Phase 2 — Staff Roles, Scope และ Approval**
วันที่เริ่ม: 1 สิงหาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

ระบบเดิมผูก `Role` กับ `user_branches` โดยตรง จึงอธิบายได้เฉพาะบทบาทต่อสาขาและไม่รองรับสมการ
`Role + Scope + Limit` ของ roadmap พนักงาน Company/Brand ยังต้องปลอมเป็น Branch assignment,
Kitchen Staff ไม่มี Station claim และ permission `fb.kitchen.manage` เดิมถูก reuse กับงาน central
production ซึ่งกว้างกว่างาน kitchen ticket

Scope นี้เพิ่ม assignment contract กลางและ runtime authorization สำหรับ Company, Brand, Branch และ
Station โดยเก็บ `user_branches` เป็น compatibility path ระหว่าง migration

## In Scope

- เพิ่ม allowed scope types ให้ Role โดย Role เดิม default เป็น Branch
- เพิ่ม `staff_role_assignments` พร้อม Company/Brand/Branch/Station target, actor, reason และ revoke history
- validate target ownership และ derive Brand จาก Branch ฝั่ง server
- validate Kitchen station จาก Branch settings และ normalize station key
- รวม permission จาก assignment ที่ใช้ได้กับ context ปัจจุบันตอนออก access token
- เพิ่ม Station claim ใน access/refresh token และบังคับ kitchen ticket ให้อยู่ Station เดียวกัน
- ให้ Company scope เข้า Branch ใน Company, Brand scope เข้า Branch ใน Brand และ Branch/Station
  เข้าได้เฉพาะ target ที่มอบหมาย
- รักษา login/switch และ permission จาก `user_branches` เดิม
- เพิ่ม assignment CRUD/options API และ UI ในหน้าจัดการผู้ใช้
- เพิ่ม granular `fb.kitchen.ticket.manage` เพื่อไม่ให้ Kitchen Staff ได้ central production access
- ทำ migration ทั้ง legacy identity snapshot และ Platform Control Plane boundary
- isolated migration/API UAT, backend/frontend regression และเอกสาร closeout

## Database / Ownership

- Target system of record: Platform Control Plane
- Default development runtime ยังเขียน legacy identity database ตาม `IDENTITY_DATABASE=legacy`
- Legacy และ Platform migrations ต้องมี schema contract เดียวกันก่อนเปิด identity cutover
- ไม่มี operational Restaurant record ชี้ FK มาที่ assignment table
- client ส่งได้เฉพาะ requested scope target; Company/Brand/Branch/business type/database ตรวจหรือ derive
  จาก server-owned canonical context

## Out of Scope

- Manager PIN และ approval session
- discount/void/refund/stock-adjust Limit และ threshold
- Device pairing หรือ Counter/Pickup device scope
- backfill หรือ rewrite `user_branches` เป็น assignment จริงโดยอัตโนมัติ
- ลบ compatibility authorization เดิม
- production activation หรือเปลี่ยน identity system of record

## Acceptance Criteria

- [x] Role ระบุ allowed Company/Brand/Branch/Station scopes และ existing Role ยังเป็น Branch-compatible
- [x] assignment target ข้าม Company/Brand หรือ Station ที่ไม่มีจริงถูกปฏิเสธ
- [x] Company assignment ใช้กับทุก Branch ใน Company เท่านั้น
- [x] Brand assignment ใช้กับทุก Branch ใน Brand เดียวกันเท่านั้น
- [x] Branch assignment ใช้กับ Branch เดียวเท่านั้น
- [x] Station assignment ออก token ที่ล็อก Station และอ่าน/แก้ kitchen ticket Station อื่นไม่ได้
- [x] พนักงานหนึ่งคนมีหลาย Role/scope assignment ได้โดย permission รวมเฉพาะ current context
- [x] Kitchen Staff ใช้ `fb.kitchen.ticket.manage` และเข้า central production/finance/settings ไม่ได้
- [x] create/revoke audit ระบุ actor, target, reason และ before/after value
- [x] legacy `user_branches` login/switch/API regression ยังผ่าน
- [x] Legacy/Platform migration upgrade/downgrade rehearsal ผ่านบน temporary databases
- [x] isolated API scope matrix, backend regression และ frontend type-check/build ผ่าน
- [x] runtime selectors และ live retained data ไม่เปลี่ยน
- [x] worktree commit แล้วโดยไม่ push

## Rollback

1. ปิดการใช้ assignment APIs/UI และ revert source commit ของ Scope นี้
2. downgrade Platform และ legacy migration เฉพาะเมื่อยืนยันว่าไม่มี active assignment ที่ต้องเก็บ
3. `user_branches` เดิมไม่ถูกลบหรือ backfill จึงกลับไปใช้ compatibility path ได้ทันที
4. runtime selectors คง legacy defaults ตลอด Scope นี้

## Execution Record

- Starting commit: `53d3446`
- Starting heads: legacy `6b7c8d9e0f12`, Platform `p1platform0003`
- Starting runtime: identity `legacy`, Restaurant service `legacy`, projector disabled
- Migration rehearsal: `scripts/rehearse-phase2-scope-assignments.sh --yes` ผ่าน upgrade →
  downgrade → re-upgrade ที่ legacy `p2scope0001` และ Platform `p2platform0004`; Platform contract `2`
- API scope matrix: Company/Brand/Branch/Station isolation, multi-role context union, invalid/cross-tenant
  targets, Station ticket read/write boundary, revoke และ audit ผ่านทั้งหมด
- Backend regression: 133 tests ผ่าน
- Frontend regression: type-check และ production build ผ่าน; มี chunk-size warning เดิม
- Final runtime/data verification: identity `legacy`, Restaurant service `legacy`, projector disabled;
  live legacy fingerprint `6b7c8d9e0f12:1:3:4:7:9:36:21` และ Platform fingerprint
  `p1platform0003:1:1:3:4:7:9` ไม่เปลี่ยนก่อน/หลัง rehearsal
- Rehearsal artifact: `/private/tmp/restaurant-p2-artifacts/p2-scope-assignments-02-20260801T011800Z/manifest.txt`
- Commit: บันทึกใน Git history ของ Scope ID นี้โดยไม่ push
