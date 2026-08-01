# Scope ID: P2-APPROVAL-SESSIONS-03

สถานะ: **Verified — automated gates complete; visual browser click-through deferred**
Phase: **Phase 2 — Staff Roles, Scope และ Approval**
วันที่เริ่ม: 1 สิงหาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

ระบบมี direct permissions สำหรับ discount override, void, refund และ stock adjustment แต่ Cashier
ไม่สามารถขออนุมัติจาก Manager ภายในรายการเดียวกันได้, backend ยังไม่ enforce discount/stock limits และ
audit ยังไม่มี requester/approver evidence ตาม Phase 2 roadmap

## In Scope

- Manager PIN 6 หลักที่ hash ใน Identity DB พร้อม failed-attempt lockout
- approval session อายุสั้น 2 นาที, ผูก Company/Branch/requester/action/request fingerprint
- single-use consumption ใน transaction เดียวกับ operation ที่ Operational DB
- cashier discount ceiling และ hard maximum จาก Branch settings ทั้ง POS และ Restaurant checkout
- request permission + approval สำหรับ void/refund และ stock adjustment เกิน threshold
- refund อ้างอิง original payment และ audit actor/approver/branch/time/reason
- migrations สำหรับ legacy, Platform และ Restaurant boundaries
- Manager PIN/approval UI, focused UAT, regression และ migration rehearsal

## Database / Ownership

- `manager_pin_credentials` เป็น Identity-owned table ใน legacy และ Platform เท่านั้น
- `approval_grant_usages` และ policy limits เป็น Operational-owned data ใน legacy และ Restaurant
- Operational records เก็บ scalar requester/approver IDs โดยไม่มี FK ข้ามฐานข้อมูล
- default runtime ยังคง identity `legacy`, Restaurant service `legacy`, projector disabled

## Out of Scope

- shared password หรือการเก็บ PIN แบบ plaintext
- device pairing / Counter device scope
- approval ผ่าน notification ระยะไกล
- production activation หรือเปลี่ยน database selector

## Acceptance Criteria

- [x] Manager ที่มี direct approval permission ตั้ง/rotate PIN ด้วย current password ได้
- [x] PIN เดาง่ายถูกปฏิเสธ และผิดครบ limit ถูก lock ชั่วคราว
- [x] requester ใช้ PIN ตัวเองอนุมัติไม่ได้ และ approver ต้องมี permission ใน Branch เดียวกัน
- [x] approval token หมดอายุ, ใช้ซ้ำ, ข้าม Branch/user/action หรือแก้ payload ไม่ได้
- [x] discount เกิน Cashier ceiling ต้องอนุมัติและเกิน hard max ถูกปฏิเสธเสมอ
- [x] void/refund request และ stock adjust เกิน threshold ต้องมี direct permission หรือ approval
- [x] refund ผูก original payment และ audit มี actor/approver/reason/request hash
- [x] legacy/Platform/Restaurant migration rehearsal ผ่านโดย live data/runtime ไม่เปลี่ยน
- [x] backend regression, frontend type-check/build และ focused API UAT ผ่าน
- [x] visual browser click-through ถูกบันทึกเป็น deferred เพราะไม่มี in-app Browser instance
- [x] worktree commit แล้วโดยไม่ push

## Rollback

1. ปิด UI request path และ revert source commits ของ Scope นี้
2. downgrade Restaurant, Platform และ legacy migrations หลังตรวจว่าไม่มี approval usage ที่ต้องเก็บ
3. direct permissions เดิมยังทำงานได้และ runtime selectors ไม่ถูกเปลี่ยน

## Execution Record

- Starting commit: `1931ef4`
- Starting heads: legacy `6b7c8d9e0f12`, Platform `p1platform0003`, Restaurant `p1restaurant0003`
- Starting runtime: identity `legacy`, Restaurant service `legacy`, projector disabled
- Permission preset policy: `2026-08-01.3`; Cashier ขออนุมัติ void/refund ได้แต่ไม่มี direct permission
- Backend regression: 140 tests ผ่าน
- Frontend regression: type-check และ production build ผ่าน; มี chunk-size warning เดิม
- API matrix: PIN hash/rotation/lockout, self-approval deny, request fingerprint, single use/replay,
  POS/Restaurant checkout discount, void, refund, stock threshold, original payment link และ approval audit ผ่าน
- UI verification: component contract ผ่าน type-check/build; automated visual click-through ไม่ได้รันเพราะ
  session นี้ไม่มี in-app Browser instance และไม่ใช้ browser automation fallback
- Migration rehearsal: legacy `p2approval0002`, Platform `p2platform0005` และ Restaurant
  `p2restaurant0004` ผ่าน upgrade → downgrade → re-upgrade; schema contracts เป็น Platform `3`
  และ Restaurant `2`
- Migration normalize ค่า `pos_max_discount_pct` ประวัติที่อยู่นอกช่วงให้กลับเข้า 0–100 ก่อนเพิ่ม
  database constraints; live clone ปัจจุบันไม่ต้องเปลี่ยนค่า
- Final runtime/data verification: identity `legacy`, Restaurant service `legacy`, projector disabled;
  live fingerprints ของ legacy, Platform และ Restaurant ไม่เปลี่ยนก่อน/หลัง rehearsal
- Rehearsal artifact:
  `/private/tmp/restaurant-p2-artifacts/p2-approval-sessions-03-20260801T022119Z/manifest.txt`
- Commit: บันทึกใน Git history ของ Scope ID นี้โดยไม่ push
