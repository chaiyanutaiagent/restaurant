# Scope ID: P2-PHASE-GATE-04

สถานะ: **Verified — Phase 2 gate complete; visual browser click-through deferred**
Phase: **Phase 2 — Staff Roles, Scope และ Approval**
วันที่เริ่ม: 1 สิงหาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

Phase 2 มี implementation scope ครบ Role preset, scoped assignment และ Manager approval แล้ว แต่ master
roadmap ยังมี acceptance ค้างสำหรับ Cashier limit กับ approval audit และยังไม่มี gate เดียวที่รวม persona,
scope, limit, database boundary, rollback rehearsal และ regression ไว้เป็นหลักฐานก่อนเริ่ม Phase 3

## In Scope

- รวม role preset policy `2026-08-01.3` และ 5 gate personas
- rerun Company/Brand/Branch/Station assignment และ Kitchen Station isolation matrix
- rerun Manager PIN, discount, void, refund, Restaurant checkout และ stock approval matrix
- ตรวจ single use, request fingerprint, lockout และ original payment link
- ตรวจ approval audit actor/approver/Branch/time/reason evidence
- rerun legacy/Platform/Restaurant upgrade → downgrade → re-upgrade บนฐานชั่วคราว
- backend regression, frontend type-check/build และ master roadmap closeout

## Database / Ownership

- Scope นี้ไม่เพิ่ม schema และไม่เปลี่ยน runtime selector
- ใช้ latest Phase 2 clone ที่รวม migration จาก `P2-SCOPE-ASSIGNMENTS-02` และ
  `P2-APPROVAL-SESSIONS-03`; downgrade ย้อนถึง pre-Phase-2 heads ก่อน re-upgrade
- temporary databases ใช้ prefix ที่แต่ละ child rehearsal ตรวจและลบอัตโนมัติ
- live legacy, Platform และ Restaurant ใช้ read-only fingerprint ก่อน/หลังเพื่อยืนยันว่าไม่ถูกเปลี่ยน

## Out of Scope

- Device registration, pairing PIN/QR, dedicated Counter/Kitchen/Pickup URL ของ Phase 3
- production activation, deploy, push หรือเปลี่ยน database system of record
- HR/payroll engine ใหม่
- visual browser automation เมื่อ session ไม่มี in-app Browser instance

## Acceptance Criteria

- [x] preset Company Owner, Brand Manager, Branch Manager, Cashier และ Kitchen Staff พร้อมใช้จาก policy เดียว
- [x] assignment Company/Brand/Branch/Station และ multi-role union ไม่ข้าม context
- [x] Kitchen Staff เข้าได้เฉพาะ Station kitchen ticket และไม่มี finance/settings permission
- [x] Cashier ทำรายการเกิน limit ไม่ได้โดยไม่มี direct permission หรือ Manager approval
- [x] approval หมดอายุ, mismatch, replay, self-approval และ PIN lockout ถูกปฏิเสธ
- [x] audit ระบุ actor, approver, Branch, เวลา, reason และ request hash ได้
- [x] refund ผูก original payment และ operation/approval usage commit แบบ atomic
- [x] legacy/Platform/Restaurant migration rehearsals ผ่านและ live fingerprints ไม่เปลี่ยน
- [x] backend regression และ frontend type-check/build ผ่าน
- [x] visual browser limitation ถูกบันทึกโดยไม่ใช้ automation fallback
- [x] master roadmap ปิด Phase 2 acceptance และบันทึก gate artifact
- [x] worktree commit แล้วโดยไม่ push

## Rollback

1. Gate นี้ไม่มี schema/data mutation บน live database จึง rollback ด้วยการ revert closeout commit ได้
2. ถ้า child rehearsal ใดไม่ผ่าน ให้คง Phase 2 gate เปิดและแก้เฉพาะ Scope ต้นทางก่อน rerun
3. runtime คง identity `legacy`, Restaurant service `legacy`, projector disabled ตลอด gate

## Execution Record

- Starting commit: `5ebbec9`
- Starting heads: legacy `6b7c8d9e0f12`, Platform `p1platform0003`, Restaurant `p1restaurant0003`
- Starting runtime: identity `legacy`, Restaurant service `legacy`, projector disabled
- Role preset policy: `2026-08-01.3`; persona matrix ผ่านครบ Company Owner, Brand Manager,
  Branch Manager, Cashier และ Kitchen Staff
- Assignment/API matrix: Company/Brand/Branch/Station isolation, multi-role context union,
  assignment create/revoke audit และ Kitchen privilege boundary ผ่าน
- Approval/API matrix: PIN hash/lockout, self-approval deny, expiry/mismatch/replay, request fingerprint,
  single-use, POS/Restaurant discount, void, refund, stock threshold และ original payment link ผ่าน
- Approval audit: actor, approver, Branch, เวลา, reason และ request hash ถูกตรวจครบ
- Migration rehearsal: legacy `p2approval0002`, Platform `p2platform0005` และ Restaurant
  `p2restaurant0004` ผ่าน upgrade → downgrade → re-upgrade; schema contracts เป็น Platform `3`
  และ Restaurant `2`
- Live fingerprints ก่อน/หลัง rehearsal ไม่เปลี่ยน: legacy `6b7c8d9e0f12:1:4:7:21:21`,
  Platform `p1platform0003:1:1:7:9`, Restaurant `p1restaurant0003:1:4:23:23`
- Backend regression: 140 tests ผ่าน
- Frontend regression: type-check และ production build ผ่าน; มี chunk-size warning เดิม
- Visual verification: component contract ผ่าน type-check/build; automated click-through ไม่ได้รันเพราะ
  session ไม่มี in-app Browser instance และไม่ใช้ browser automation fallback
- Gate artifact:
  `/private/tmp/restaurant-p2-artifacts/p2-phase-gate-04-20260801T022957Z/manifest.txt`
- Combined boundary artifact:
  `/private/tmp/restaurant-p2-artifacts/p2-approval-sessions-03-20260801T022958Z/manifest.txt`
- Temporary database cleanup: final query พบฐาน prefix `restaurant_p2_approval_` ค้าง `0`
- Final runtime: identity `legacy`, Restaurant service `legacy`, projector disabled
- Commit: บันทึกใน Git history ของ Scope ID นี้โดยไม่ push
