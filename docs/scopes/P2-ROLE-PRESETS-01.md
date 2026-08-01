# Scope ID: P2-ROLE-PRESETS-01

สถานะ: **Verified — role preset foundation complete; scope assignment remains separate**
Phase: **Phase 2 — Staff Roles, Scope และ Approval**
วันที่เริ่ม: 1 สิงหาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

Phase 1 gate ผ่านแล้ว แต่ Role preset เดิมอยู่ใน `RolesPage` ฝั่ง frontend เท่านั้น ทำให้ API ไม่มี
policy contract กลาง, client อื่นอาจสร้างชุดสิทธิ์ไม่ตรงกัน และ preset `Kitchen Staff` เดิมมีสิทธิ์จัดการ
central production ซึ่งเกินหน้าที่ครัวตาม roadmap ขณะที่ Phase 2 acceptance ต้องจำลองอย่างน้อย
Company Owner, Brand Manager, Branch Manager, Cashier และ Kitchen Staff ด้วย policy เดียวกัน

Scope นี้วาง Role layer ก่อน โดยยังไม่รวมการ persist Scope assignment หรือ Limit ตามสมการ
`Role + Scope + Limit` และไม่แก้ Role ที่มีอยู่ในแต่ละ Company อัตโนมัติ

## In Scope

- สร้าง server-owned, versioned preset policy สำหรับ 5 Phase 2 gate personas
- ระบุ default/allowed scope metadata ระดับ Company, Brand, Branch และ Station
- คืน preset พร้อม permission IDs/codes, availability และ missing permission diagnostics ผ่าน API
- ใช้ branch-assignable guard เดิมกับ Branch Manager, Cashier และ Kitchen Staff
- ให้หน้า Roles โหลด preset จาก backend แทน hardcode ใน browser
- จำกัด Cashier ไม่ให้ void, refund, override discount, ปรับ stock หรือเปิด finance/settings
- จำกัด Kitchen Staff ให้เหลือ `fb.menu.view` และ `fb.kitchen.manage` ใน foundation revision;
  follow-up `P2-SCOPE-ASSIGNMENTS-02` แยก granular kitchen-ticket permission ออกจาก legacy code
- unit regression และ authenticated read-only API smoke
- อัปเดต architecture, roadmap และ Scope record

## Database / Ownership

- Role preset policy เป็น application policy ใน Control Plane source code
- Permission catalog และ Role เดิมยังอ่านจาก source เดียวกับ Role APIs ปัจจุบัน ซึ่งเป็น legacy
  identity database ใน default runtime; Scope นี้ไม่เปลี่ยน database selector
- ไม่มี schema migration และไม่มีการเขียน/เปลี่ยน Role ของ Company จริง
- `policy_version=2026-08-01` ทำให้ client และหลักฐาน UAT ระบุ policy revision ได้
- `is_branch_assignable` เป็น compatibility bridge ของ user-access flow เดิม; Station assignment enforcement
  จะทำใน Scope ถัดไป

## Out of Scope

- ย้ายหรือ rewrite Role เดิมให้ตรง preset โดยอัตโนมัติ
- persist assignment ระดับ Company/Brand/Station และการ enforce resource scope
- Manager PIN หรือ approval session
- approval threshold สำหรับ discount, void, refund และ stock adjustment
- before/after operational audit schema
- Role preset อื่นนอก 5 personas ที่ใช้เป็น Phase 2 acceptance gate
- production deploy หรือสลับ identity system of record

## Acceptance Criteria

- [x] API คืน preset ตามลำดับ Company Owner, Brand Manager, Branch Manager, Cashier, Kitchen Staff
- [x] preset ทุกตัวอ้างอิง permission catalog ที่มีจริงและไม่มี code ซ้ำ
- [x] Company Owner ใช้ explicit current permission catalog โดยไม่ใช้ wildcard
- [x] Branch Manager, Cashier และ Kitchen Staff ผ่าน central branch-role guard
- [x] Cashier ไม่มี manager override, refund, finance, settings หรือ stock-adjust permission
- [x] Kitchen Staff เป็น Station scope และมีเฉพาะ kitchen permissions
- [x] หน้า Roles ไม่มี hardcoded preset และใช้ permission IDs จาก backend response
- [x] permission catalog drift แสดง preset unavailable พร้อม missing codes โดยไม่สร้าง Role แบบสิทธิ์ขาดเงียบ ๆ
- [x] authenticated API smoke, backend regression และ frontend type-check/build ผ่าน
- [x] Role/data เดิมไม่ถูกเปลี่ยน และ runtime selector ยังคงค่าเดิม
- [x] worktree commit แล้วโดยไม่ push

## Rollback

1. Revert source commit ของ Scope นี้เพื่อเอา endpoint/policy/UI integration ออก
2. ไม่มี database migration หรือ data mutation จึงไม่ต้อง restore database
3. หน้า Roles ก่อนหน้าใช้ hardcoded preset; rollback กลับได้พร้อม source commit เดียว
4. identity/Restaurant runtime selectors ไม่เปลี่ยนจาก Phase 1 defaults

## Execution Record

- Starting commit: `f73e23b`
- Starting runtime target: identity `legacy`, Restaurant service `legacy`, projector disabled
- Backend regression: 127 tests ผ่าน
- Frontend type-check: ผ่าน
- Frontend production build: ผ่าน; มี chunk-size warning เดิม
- Authenticated API smoke: `role_presets_api_smoke=ok policy=2026-08-01 presets=5`
- Local data verification: ไม่พบ active Role ชื่อ Company Owner, Brand Manager, Branch Manager,
  Cashier หรือ Kitchen Staff หลัง smoke จึงยืนยันว่า endpoint ไม่ auto-create หรือ rewrite Role เดิม
- Final readiness: database, Platform database, Restaurant database, Redis และ uploads เป็น `ok`;
  runtime เป็น identity `legacy`, Restaurant service `legacy`, projector disabled และ projector errors เป็น 0
- Schema/data impact: ไม่มี migration; API smoke อ่าน permission catalog และไม่มี Role mutation
- Commit: บันทึกใน Git history ของ Scope ID นี้โดยไม่ push

## Follow-up

`P2-SCOPE-ASSIGNMENTS-02` เปลี่ยน policy เป็น `2026-08-01.2` และแทนสิทธิ์ Kitchen Staff เดิมด้วย
`fb.kitchen.ticket.manage` เพื่อไม่ให้ Station-scoped staff ได้สิทธิ์ central production ที่ reuse
`fb.kitchen.manage`
